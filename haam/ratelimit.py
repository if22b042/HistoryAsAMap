"""Rate limits kept in the database, so they hold across serverless instances.

Requests are counted per (scope, client, window) in ``haam_rate_limits``; a client
is a SHA-256 hash of its address (behind a proxy: the hop our trusted
proxies added to ``X-Forwarded-For``, see ``client_address``). Old windows are deleted now and then. The limits are off while testing
unless ``RATELIMIT_ENABLED`` is set.

    @bp.post("/submit")
    @limit("submit", 10, 60)          # 10 requests per 60 seconds, then 429
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from functools import wraps

from flask import abort, current_app, request
from sqlalchemy import delete, update
from sqlalchemy.exc import SQLAlchemyError

from haam.extensions import db
from haam.models import RateLimitHit

logger = logging.getLogger(__name__)

PRUNE_CHANCE = 0.02  # share of counted requests that also delete old windows
KEEP_SECONDS = 24 * 3600


def client_key() -> str:
    """A hash of the visitor's address, never the address itself."""
    return hash_of(client_address())


def client_address() -> str:
    """The visitor's address: the hop our own trusted proxies appended, never one the visitor wrote.

    Each trusted proxy appends the address it saw to ``X-Forwarded-For``, so with ``TRUSTED_PROXIES``
    = n the n-th entry from the right is the client; everything left of it is client-supplied.
    With 0 (the default) the header is ignored and the socket address is used.
    """
    trusted = int(current_app.config.get("TRUSTED_PROXIES") or 0)
    if trusted > 0:
        hops = [h.strip() for h in request.headers.get("X-Forwarded-For", "").split(",") if h.strip()]
        if len(hops) >= trusted:
            return hops[-trusted]
    return request.remote_addr or "unknown"


def hash_of(value: str) -> str:
    """A keyed SHA-256 of ``value``, for scopes that must not store what they count."""
    secret = current_app.config.get("SECRET_KEY") or ""
    return hashlib.sha256(f"{secret}|{value}".encode()).hexdigest()


def enabled() -> bool:
    return bool(current_app.config.get("RATELIMIT_ENABLED", not current_app.testing))


def hit(scope: str, seconds: int, now: float | None = None, key: str | None = None) -> int:
    """Count one request of this client (or of ``key``, a hash) in ``scope``; returns the window's count."""
    now = time.time() if now is None else now
    window = int(now // seconds) * seconds
    key = key or client_key()
    where = (RateLimitHit.scope == scope, RateLimitHit.client_hash == key, RateLimitHit.window_start == window)
    result = db.session.execute(update(RateLimitHit).where(*where).values(count=RateLimitHit.count + 1))
    if result.rowcount == 0:
        db.session.add(RateLimitHit(scope=scope, client_hash=key, window_start=window, count=1))
        try:
            db.session.flush()
        except SQLAlchemyError:  # a parallel request created the row first
            db.session.rollback()
            db.session.execute(update(RateLimitHit).where(*where).values(count=RateLimitHit.count + 1))
    count = db.session.scalar(db.select(RateLimitHit.count).where(*where)) or 1
    if random.random() < PRUNE_CHANCE:
        db.session.execute(delete(RateLimitHit).where(RateLimitHit.window_start < now - KEEP_SECONDS))
    db.session.commit()
    return count


def allow(scope: str, count: int, seconds: int, key: str | None = None) -> bool:
    """Count one use of ``scope`` by this client; False once it is over ``count`` in the window.

    For limits that depend on the request's content (e.g. one score per game and
    day), where the decorator's fixed scope does not fit. Fails open like ``limit``.
    """
    if not enabled():
        return True
    try:
        return hit(scope, seconds, key=key) <= count
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Rate limit check failed; letting the request through.")
        return True


def limit(scope: str, count: int, seconds: int, methods: tuple[str, ...] | None = None):
    """Allow ``count`` requests per ``seconds`` per client; more get a 429 page.

    ``methods`` restricts counting to those HTTP methods (e.g. only the POST of a form).
    If the database fails, the request is let through: a limiter must not take the site down.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if enabled() and (methods is None or request.method in methods):
                try:
                    used = hit(scope, seconds)
                except SQLAlchemyError:
                    db.session.rollback()
                    logger.exception("Rate limit check failed; letting the request through.")
                    used = 0
                if used > count:
                    abort(429)
            return view(*args, **kwargs)

        return wrapped

    return decorator
