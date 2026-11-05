"""Best-effort reverse geocoding (coordinates → country) via OpenStreetMap Nominatim.

Nominatim's usage policy allows at most one request per second, so calls are
spaced out, answers are cached, and after a "too many requests" reply we stop
asking for a while instead of hammering the service.
"""

import logging
import threading
import time

import requests
from flask import current_app

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
MIN_INTERVAL = 1.1  # seconds between requests (policy: max 1 per second)
BACKOFF = 300  # seconds to pause after HTTP 429

_lock = threading.Lock()
_last_request = 0.0
_paused_until = 0.0
_cache: dict[tuple[float, float], str | None] = {}


def country_for(lat: float, lon: float) -> str | None:
    """Return the English country name, or ``None`` if unknown/unavailable.

    Never raises: a missing country must not block saving an event.
    """
    global _last_request, _paused_until
    if not current_app.config.get("GEOCODING_ENABLED"):
        return None
    key = (round(lat, 3), round(lon, 3))  # ~100 m; country doesn't change below that
    if key in _cache:
        return _cache[key]

    with _lock:
        now = time.monotonic()
        if now < _paused_until:
            return None
        wait = _last_request + MIN_INTERVAL - now
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        try:
            response = requests.get(
                NOMINATIM_URL,
                params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 3, "accept-language": "en"},
                headers={"User-Agent": current_app.config["HAAM_USER_AGENT"]},
                timeout=5,
            )
            if response.status_code == 429:
                _paused_until = time.monotonic() + BACKOFF
                logger.warning("Nominatim rate limit hit; pausing country lookups for %d s.", BACKOFF)
                return None
            response.raise_for_status()
            country = response.json().get("address", {}).get("country")
        except (requests.RequestException, ValueError) as exc:
            logger.info("Reverse geocoding failed for %s,%s: %s", lat, lon, exc)
            return None
    _cache[key] = country
    return country
