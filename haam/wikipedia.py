"""Read event data from English Wikipedia and Wikidata."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote

import requests
from flask import current_app
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from haam.dates import extract_date, parse_wikidata_time

logger = logging.getLogger(__name__)

API_URL = "https://en.wikipedia.org/w/api.php"
WIKIDATA_URL = "https://www.wikidata.org/w/api.php"

_WIKI_URL_RE = re.compile(
    r"^https?://en\.(?:m\.)?wikipedia\.org/wiki/(?P<title>[^?#]+)", re.IGNORECASE
)

# Wikidata properties: point in time, start time, coordinate location.
P_POINT_IN_TIME, P_START_TIME, P_COORDINATES = "P585", "P580", "P625"


class WikipediaError(Exception):
    """Wikipedia could not be reached or returned an unexpected response."""


@dataclass
class Article:
    page_id: int
    title: str
    url: str
    summary: str
    lat: float | None
    lon: float | None
    year: int | None
    date_label: str
    # True when the date came from Wikidata (point in time / start time). Places
    # such as towns have no such date, so this is a good "is an event" signal.
    dated_by_wikidata: bool = False


def title_from_url(url: str) -> str | None:
    """Return the article title for an English Wikipedia URL, else ``None``.

    Accepts desktop and mobile URLs, http/https, percent-encoding, query strings
    and section anchors.
    """
    m = _WIKI_URL_RE.match((url or "").strip())
    if not m:
        return None
    title = unquote(m.group("title")).replace("_", " ").strip()
    return title or None


def canonical_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="()_,;:!'*-.~/@$&+=")


class WikipediaClient:
    def __init__(self, user_agent: str, timeout: float = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        retry = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
                      respect_retry_after_header=True)
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _get(self, url: str, params: dict) -> dict:
        params = {**params, "format": "json", "formatversion": 2}
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Request to %s failed: %s", url, exc)
            raise WikipediaError(str(exc)) from exc

    def fetch_article(self, title: str) -> Article | None:
        """Fetch an article; returns ``None`` if it does not exist."""
        data = self._get(API_URL, {
            "action": "query",
            "titles": title,
            "redirects": 1,
            "prop": "coordinates|extracts|pageprops",
            "exintro": 1,
            "explaintext": 1,
            "ppprop": "wikibase_item",
        })
        pages = data.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing") or pages[0].get("invalid"):
            return None
        page = pages[0]

        extract = page.get("extract", "") or ""
        summary = next((p.strip() for p in extract.split("\n") if p.strip()), "")
        coords = (page.get("coordinates") or [{}])[0]
        lat, lon = coords.get("lat"), coords.get("lon")

        parsed = None
        wikidata_id = page.get("pageprops", {}).get("wikibase_item")
        if wikidata_id:
            claims = self._wikidata_claims(wikidata_id)
            parsed = _wikidata_date(claims)
            if lat is None or lon is None:
                lat, lon = _wikidata_coordinates(claims)
        dated_by_wikidata = parsed is not None
        if parsed is None:
            parsed = extract_date(extract)

        return Article(
            page_id=page["pageid"],
            title=page["title"],
            url=canonical_url(page["title"]),
            summary=summary,
            lat=lat,
            lon=lon,
            year=parsed.year if parsed else None,
            date_label=parsed.label if parsed else "",
            dated_by_wikidata=dated_by_wikidata,
        )

    def _wikidata_claims(self, entity_id: str) -> dict:
        try:
            data = self._get(WIKIDATA_URL, {"action": "wbgetentities", "ids": entity_id, "props": "claims"})
        except WikipediaError:
            return {}  # Wikidata is a bonus; fall back to parsing the text.
        return data.get("entities", {}).get(entity_id, {}).get("claims", {})

    def geosearch(self, lat: float, lon: float, radius: int = 10000, limit: int = 500) -> list[str]:
        """Titles of articles with coordinates within ``radius`` metres of a point."""
        data = self._get(API_URL, {
            "action": "query",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": min(radius, 10000),
            "gslimit": min(limit, 500),
            "gsnamespace": 0,
        })
        return [item["title"] for item in data.get("query", {}).get("geosearch", [])]


def _claim_value(claims: dict, prop: str):
    for claim in claims.get(prop, []):
        snak = claim.get("mainsnak", {})
        if snak.get("snaktype") == "value":
            return snak.get("datavalue", {}).get("value")
    return None


def _wikidata_date(claims: dict):
    for prop in (P_POINT_IN_TIME, P_START_TIME):
        value = _claim_value(claims, prop)
        if value:
            parsed = parse_wikidata_time(value)
            if parsed:
                return parsed
    return None


def _wikidata_coordinates(claims: dict) -> tuple[float | None, float | None]:
    value = _claim_value(claims, P_COORDINATES)
    if value:
        return value.get("latitude"), value.get("longitude")
    return None, None


def get_client() -> WikipediaClient:
    """One shared client per app (keeps the HTTP connection pool alive)."""
    client = current_app.extensions.get("haam_wikipedia")
    if client is None:
        client = WikipediaClient(current_app.config["HAAM_USER_AGENT"], current_app.config["HTTP_TIMEOUT"])
        current_app.extensions["haam_wikipedia"] = client
    return client
