"""History As A Map – an interactive map of historical events from Wikipedia."""

import hashlib
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
    # server.arcgisonline.com: the game's map tiles without place names.
    "img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org https://unpkg.com"
    " https://server.arcgisonline.com",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])


def _config_name() -> str:
    default = "production" if os.environ.get("VERCEL") else "development"
    return os.environ.get("HAAM_ENV", default)


STATIC_MAX_AGE = 365 * 24 * 3600


class HaamFlask(Flask):
    """``url_for('static', ...)`` gives versioned URLs: /static/v/<build>/js/map.js.

    The build id is a hash of every static file, so any change makes new URLs and
    the files can be cached as immutable (by browsers and by Vercel's CDN). It is
    part of the path, not a query string, so the relative imports between the
    JavaScript modules (``./timeline.js``) stay on the same version.
    """

    static_build = ""

    def url_for(self, endpoint, /, **values):
        if endpoint == "static" and self.static_build:
            endpoint = "versioned_static"
            values["build"] = self.static_build
        return super().url_for(endpoint, **values)


def _static_build(folder: str) -> str:
    digest = hashlib.sha1()
    for root, dirs, files in sorted(os.walk(folder)):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(root, name)
            digest.update(os.path.relpath(path, folder).replace(os.sep, "/").encode())
            with open(path, "rb") as file:
                digest.update(file.read())
    return digest.hexdigest()[:10]


def _register_versioned_static(app: Flask) -> None:
    from flask import send_from_directory

    app.static_build = _static_build(app.static_folder)

    # Any build id is accepted (an old page may still ask for its own): Vercel serves
    # only the current files anyway, and the CDN caches each URL on its own.
    @app.get("/static/v/<build>/<path:filename>", endpoint="versioned_static")
    def versioned_static(build: str, filename: str):
        response = send_from_directory(app.static_folder, filename, max_age=STATIC_MAX_AGE)
        # Not while developing: the build id is taken at start-up, and edited files must show.
        if build == app.static_build and app.config.get("STATIC_IMMUTABLE", True):
            response.cache_control.public = True
            response.cache_control.s_maxage = STATIC_MAX_AGE
            response.cache_control.immutable = True
        else:
            response.cache_control.max_age = 0
            response.cache_control.no_cache = True
        return response


def create_app(config_name: str | None = None) -> Flask:
    config = CONFIGS[config_name or _config_name()]
    app = HaamFlask(__name__, instance_path=str(INSTANCE_DIR))
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
    from haam.views import admin, api, collections, game, public, seo

    app.register_blueprint(public.bp)
    app.register_blueprint(collections.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(game.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(seo.bp)
    cli.register(app)

    _register_versioned_static(app)
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


SETUP_LOCK_KEY = 4_861_337  # arbitrary, identifies the setup lock


def _ensure_database(app: Flask) -> None:
    """Apply pending migrations and load the tags when the app starts.

    Without this a fresh or outdated database (local or on Vercel) lacks tables
    and pages fail. Cheap when up to date: one query for the current revision.
    """
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from flask_migrate import upgrade
    from sqlalchemy import select, text
    from sqlalchemy.exc import SQLAlchemyError

    from haam.extensions import db, migrate
    from haam.importer import seed_tags
    from haam.models import Tag

    with app.app_context():
        try:
            # Parallel cold starts would all migrate and seed at once; on PostgreSQL the
            # first one takes this lock and the others wait, then find nothing to do.
            # A transaction-level lock also works through Neon's pooled connections.
            with db.engine.connect() as lock, lock.begin():
                if lock.dialect.name == "postgresql":
                    lock.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SETUP_LOCK_KEY})
                config = migrate.get_config(str(MIGRATIONS_DIR))
                newest = set(ScriptDirectory.from_config(config).get_heads())
                with db.engine.connect() as connection:
                    current = set(MigrationContext.configure(connection).get_current_heads())
                if current != newest:
                    logger.info("Database schema is out of date; running migrations.")
                    upgrade(directory=str(MIGRATIONS_DIR))
                if db.session.scalar(select(Tag.id).limit(1)) is None:
                    logger.info("Loaded %d tags.", seed_tags())
                db.session.remove()
        except SQLAlchemyError:
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
    from haam import seo
    from haam.auth import is_admin
    from haam.dates import format_year
    from haam.models import Category

    app.jinja_env.filters["year"] = format_year
    app.jinja_env.filters["describe"] = seo.describe
    app.jinja_env.globals.update(
        absolute_url=seo.absolute,
        external_url=seo.external_url,
        event_path=seo.event_path,
        site_name=seo.SITE_NAME,
        default_description=seo.DEFAULT_DESCRIPTION,
    )

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
