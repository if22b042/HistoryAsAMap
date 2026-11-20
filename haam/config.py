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
    # Forms stay valid as long as the session: a map or form left open for an hour still works.
    WTF_CSRF_TIME_LIMIT = None

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

    # Optional: email the collection links once after creation (see haam/mail.py).
    # Without SMTP_HOST the email field is hidden. Port 465 uses SSL, other ports STARTTLS.
    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT") or "587")
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    MAIL_FROM = os.environ.get("MAIL_FROM")
    # Abuse limits for the email: per recipient and per client per hour, all recipients per day.
    MAIL_PER_RECIPIENT_HOURLY = int(os.environ.get("MAIL_PER_RECIPIENT_HOURLY") or "2")
    MAIL_PER_CLIENT_HOURLY = int(os.environ.get("MAIL_PER_CLIENT_HOURLY") or "3")
    MAIL_DAILY_LIMIT = int(os.environ.get("MAIL_DAILY_LIMIT") or "200")

    # How many reverse proxies in front of the app append to X-Forwarded-For (see haam/ratelimit.py).
    # 0 ignores the header, so a visitor cannot pick their own address; Vercel is one proxy.
    TRUSTED_PROXIES = int(os.environ.get("TRUSTED_PROXIES") or ("1" if os.environ.get("VERCEL") else "0"))

    # Public address used in canonical links, share previews and the sitemap.
    # Empty means "the address of the current request".
    SITE_URL = os.environ.get("SITE_URL", "https://history-as-a-map.vercel.app").rstrip("/")


class DevelopmentConfig(Config):
    SECRET_KEY = Config.SECRET_KEY or "dev-only-secret-key"
    STATIC_IMMUTABLE = False  # static files are edited while the server runs
    SESSION_COOKIE_SECURE = False
    SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")


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
    SITE_URL = "https://haam.test"
    TRUSTED_PROXIES = 1  # tests pass a client address in X-Forwarded-For
    FEED_STATE_TTL = 0  # tests change data and read the map's version straight away


CONFIGS = {
    "development": DevelopmentConfig,
    "production": Config,
    "testing": TestingConfig,
}
