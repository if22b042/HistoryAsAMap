import logging

import requests

logger = logging.getLogger(__name__)


def reverse_geocode(lat: float, lon: float) -> str | None:
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json"},
            headers={"User-Agent": "HistoryAsAMap/1.0"},
            timeout=10,
        )
        if response.status_code == 200:
            return response.json().get("address", {}).get("country")
    except requests.RequestException as exc:
        logger.warning("Reverse geocoding failed: %s", exc)
    return None


def check_on_water(lat: float, lon: float) -> bool:
    try:
        response = requests.get(
            f"https://api.onwater.io/api/v1/results/{lat},{lon}",
            timeout=10,
        )
        if response.status_code == 200:
            return response.json().get("water", False)
    except requests.RequestException as exc:
        logger.warning("Water check failed: %s", exc)
    return False
