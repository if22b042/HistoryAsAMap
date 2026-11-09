"""Application configuration, read from environment variables."""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"

DEFAULT_USER_AGENT = (
    "HistoryAsAMap/2.0 (+https://github.com/if22b042/HistoryAsAMap) python-requests"
)


def _database_url(env_var: str = "DATABASE_URL", default: str | None = None) -> str:
    url = os.environ.get(env_var)
    if not url:
        return default or f"sqlite:///{INSTANCE_DIR / 'haam.db'}"
    # Heroku/Vercel/Neon style URLs: make SQLAlchemy use psycopg 3.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Admin login: a Werkzeug password hash (create with `flask haam hash-password`).
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")

    # Identify ourselves to Wikipedia / Nominatim as their policies require.
    HAAM_USER_AGENT = os.environ.get("HAAM_USER_AGENT", DEFAULT_USER_AGENT)
    HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "10"))
    # Reverse geocoding (country lookup) is optional and best-effort.
    GEOCODING_ENABLED = os.environ.get("GEOCODING_ENABLED", "true").lower() == "true"

    # Create tables / load tags on startup if missing (see haam/__init__.py).
    AUTO_SETUP_DATABASE = os.environ.get("AUTO_SETUP_DATABASE", "true").lower() == "true"

    # Long-lived so browsers keep remembering the collections they can edit.
    PERMANENT_SESSION_LIFETIME = timedelta(days=365)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"


class DevelopmentConfig(Config):
    SECRET_KEY = Config.SECRET_KEY or "dev-only-secret-key"
    STATIC_IMMUTABLE = False  # static files are edited while the server runs
    SESSION_COOKIE_SECURE = False


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    # In-memory SQLite by default; CI also runs the suite on PostgreSQL.
    SQLALCHEMY_DATABASE_URI = _database_url("TEST_DATABASE_URL", default="sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    GEOCODING_ENABLED = False
    AUTO_SETUP_DATABASE = False  # tests build their own schema


CONFIGS = {
    "development": DevelopmentConfig,
    "production": Config,
    "testing": TestingConfig,
}
