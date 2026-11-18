"""Rate limits kept in the database, so they hold across serverless instances.

Requests are counted per (scope, client, window) in ``haam_rate_limits``; a client
is a SHA-256 hash of its address (the first hop of ``X-Forwarded-For`` behind a
proxy). Old windows are deleted now and then. The limits are off while testing
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
    forwarded = request.headers.get("X-Forwarded-For", "")
    address = forwarded.split(",")[0].strip() or request.remote_addr or "unknown"
    secret = current_app.config.get("SECRET_KEY") or ""
    return hashlib.sha256(f"{secret}|{address}".encode()).hexdigest()


def enabled() -> bool:
    return bool(current_app.config.get("RATELIMIT_ENABLED", not current_app.testing))


def hit(scope: str, seconds: int, now: float | None = None) -> int:
    """Count one request of this client in ``scope``; returns how many the current window has."""
    now = time.time() if now is None else now
    window = int(now // seconds) * seconds
    key = client_key()
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


def allow(scope: str, count: int, seconds: int) -> bool:
    """Count one use of ``scope`` by this client; False once it is over ``count`` in the window.

    For limits that depend on the request's content (e.g. one score per game and
    day), where the decorator's fixed scope does not fit. Fails open like ``limit``.
    """
    if not enabled():
        return True
    try:
        return hit(scope, seconds) <= count
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
