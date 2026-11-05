"""Best-effort reverse geocoding (coordinates → country) via OpenStreetMap Nominatim."""

import logging

import requests
from flask import current_app

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"


def country_for(lat: float, lon: float) -> str | None:
    """Return the English country name, or ``None`` if unknown/unavailable.

    Never raises: a missing country must not block saving an event.
    """
    if not current_app.config.get("GEOCODING_ENABLED"):
        return None
    try:
        response = requests.get(
            NOMINATIM_URL,
            params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 3, "accept-language": "en"},
            headers={"User-Agent": current_app.config["HAAM_USER_AGENT"]},
            timeout=5,
        )
        response.raise_for_status()
        return response.json().get("address", {}).get("country")
    except (requests.RequestException, ValueError) as exc:
        logger.info("Reverse geocoding failed for %s,%s: %s", lat, lon, exc)
        return None
