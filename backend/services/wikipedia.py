import logging
import re
import time
from urllib.parse import unquote, urlparse

import requests

logger = logging.getLogger(__name__)


def get_wikipedia_data(url: str) -> dict | None:
    path = urlparse(url).path
    title = unquote(path.split("/wiki/")[-1])
    logger.info("Fetching Wikipedia data for: %s", title)

    api_url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "titles": title,
        "prop": "coordinates|extracts",
        "explaintext": True,
        "exintro": True,
        "format": "json",
    }
    headers = {
        "User-Agent": "HistoryAsAMap/1.0 (https://github.com/history-as-a-map) Python-requests"
    }

    try:
        time.sleep(1)
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        page = next(iter(data["query"]["pages"].values()))
        if "missing" in page:
            return None

        title_clean = page.get("title", "")
        coords = page.get("coordinates", [{}])[0]
        lat, lon = coords.get("lat"), coords.get("lon")

        extract = page.get("extract", "")
        first_paragraph = extract.split("\n")[0].strip()

        # Try to find date ranges like "23 August – 2 February 1943" and extract first date
        date_range_match = re.search(r"\b(\d{1,2}\s+\w+)\s*(?:–|-|to)\s*\d{1,2}\s+\w+\s+\d{4}", extract)
        if date_range_match:
            # Extract the first date and add the year from the range
            year_match = re.search(r"\b(1[0-9]\d{2}|20\d{2})\b", extract)
            year = year_match.group(1) if year_match else None
            date = f"{date_range_match.group(1)} {year}" if year else date_range_match.group(1)
        else:
            # Try to find single dates like "23 August 1942"
            date_matches = re.findall(r"\b(\d{1,2}\s+\w+\s+\d{4})\b", extract)
            date = date_matches[0] if date_matches else None

        year_match = re.search(r"\b(1[0-9]\d{2}|20\d{2})\b", extract)
        year = int(year_match.group(1)) if year_match else None

        google_maps_link = f"https://www.google.com/maps?q={lat},{lon}" if lat and lon else ""
        
        return {
            "title": title_clean,
            "lat": lat,
            "lon": lon,
            "first_paragraph": first_paragraph,
            "date": date or "",
            "year": year,
            "link": url,
            "google_maps_link": google_maps_link,
        }
    except requests.RequestException as exc:
        logger.error("Wikipedia request failed: %s", exc)
        return None
