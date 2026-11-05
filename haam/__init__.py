"""History As A Map – an interactive map of historical events from Wikipedia."""

import logging
import os

from flask import Flask, render_template

from haam.config import BASE_DIR, CONFIGS, INSTANCE_DIR

logger = logging.getLogger(__name__)
MIGRATIONS_DIR = BASE_DIR / "migrations"

# Content-Security-Policy: only our own scripts plus the pinned CDN libraries.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://unpkg.com https://cdnjs.cloudflare.com",
    "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdnjs.cloudflare.com",
    "font-src 'self' https://cdnjs.cloudflare.com",
    "img-src 'self' data: https://*.tile.openstreetmap.org https://unpkg.com",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])


def _config_name() -> str:
    default = "production" if os.environ.get("VERCEL") else "development"
    return os.environ.get("HAAM_ENV", default)


def create_app(config_name: str | None = None) -> Flask:
    config = CONFIGS[config_name or _config_name()]
    app = Flask(__name__, instance_path=str(INSTANCE_DIR))
    app.config.from_object(config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be set (see .env.example).")
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///"):
        INSTANCE_DIR.mkdir(exist_ok=True)

    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)

    from haam.extensions import csrf, db, migrate

    db.init_app(app)
    # Only manage our own tables; legacy tables (entries, locations, ...) are left alone.
    migrate.init_app(app, db, directory=str(MIGRATIONS_DIR), include_object=_only_haam_tables)
    csrf.init_app(app)

    from haam import cli
    from haam.views import admin, api, public

    app.register_blueprint(public.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(admin.bp)
    cli.register(app)

    _register_template_helpers(app)
    _register_error_pages(app)
    if app.config.get("AUTO_SETUP_DATABASE"):
        _ensure_database(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    return app


def _ensure_database(app: Flask) -> None:
    """Create the schema and load the tags the first time the app starts.

    Without this a fresh database (local or on Vercel) has no tables and every
    page that reads events fails. Cheap when already set up: one inspection query.
    """
    from flask_migrate import upgrade
    from sqlalchemy import inspect, select
    from sqlalchemy.exc import SQLAlchemyError

    from haam.extensions import db
    from haam.importer import seed_tags
    from haam.models import Tag

    with app.app_context():
        try:
            if "haam_events" not in inspect(db.engine).get_table_names():
                logger.info("Database has no HAAM tables yet; running migrations.")
                upgrade(directory=str(MIGRATIONS_DIR))
            if db.session.scalar(select(Tag.id).limit(1)) is None:
                logger.info("Loaded %d tags.", seed_tags())
        except SQLAlchemyError:
            # Another instance may be doing the same right now (parallel cold starts).
            db.session.rollback()
            logger.exception("Automatic database setup failed; run `flask --app haam db upgrade`.")
        except Exception:
            # Alembic wraps DB errors in its own types; never block the app from starting.
            logger.exception("Automatic database setup failed; run `flask --app haam db upgrade`.")


def _only_haam_tables(obj, name, type_, reflected, compare_to) -> bool:
    if type_ == "table":
        return name.startswith("haam_")
    table = getattr(obj, "table", None)
    return table is None or table.name.startswith("haam_")


def _register_template_helpers(app: Flask) -> None:
    from haam.auth import is_admin
    from haam.dates import format_year
    from haam.models import Category

    app.jinja_env.filters["year"] = format_year

    @app.context_processor
    def inject_globals():
        return {"is_admin": is_admin(), "categories": list(Category)}


def _register_error_pages(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="This page does not exist."), 404

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("error.html", code=500, message="Something went wrong on our side."), 500
