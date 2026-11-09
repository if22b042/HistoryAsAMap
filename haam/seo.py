"""Search engines and share previews: slugs, absolute URLs, the sitemap and robots.txt."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from xml.sax.saxutils import escape

from flask import current_app, request, url_for
from sqlalchemy import func, select

from haam.extensions import db
from haam.models import Event, Status

SITE_NAME = "History As A Map"
DEFAULT_DESCRIPTION = (
    "An interactive map of about 19,000 historical events from Wikipedia: battles, treaties, "
    "discoveries and disasters, filtered by year, category and era."
)
DESCRIPTION_LENGTH = 160
SLUG_LENGTH = 80
# A sitemap file may list at most 50,000 URLs; larger sets are split behind a sitemap index.
SITEMAP_LIMIT = 50_000


def slugify(text: str) -> str:
    """``"Battle of Zama"`` → ``"battle-of-zama"``; accents are folded, other scripts dropped."""
    # Punctuation (dashes, apostrophes) separates words before accents are folded away.
    spaced = re.sub(r"[\W_]+", " ", text)
    ascii_text = unicodedata.normalize("NFKD", spaced).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if len(slug) > SLUG_LENGTH:
        slug = slug[:SLUG_LENGTH].rsplit("-", 1)[0]
    return slug or "event"


def event_path(event: Event) -> str:
    return url_for("public.event_page", event_id=event.id, slug=slugify(event.title))


def site_url() -> str:
    """The site's public origin, without a trailing slash."""
    return current_app.config.get("SITE_URL") or request.host_url.rstrip("/")


def absolute(path: str) -> str:
    return site_url() + path


def external_url(endpoint: str, **values) -> str:
    return absolute(url_for(endpoint, **values))


def describe(text: str, length: int = DESCRIPTION_LENGTH) -> str:
    """Shorten ``text`` at a word boundary for a meta description."""
    text = " ".join((text or "").split())
    if len(text) <= length:
        return text
    return text[: length - 1].rsplit(" ", 1)[0].rstrip(",;:.") + "…"


# ---------------------------------------------------------------- tile map

TILE_SIZE = 256
TILE_ZOOM = 6


@dataclass(frozen=True)
class Tile:
    url: str
    left: int  # position inside the mosaic, in pixels
    top: int


@dataclass(frozen=True)
class TileMap:
    """A small static map: OpenStreetMap tiles around a point, no JavaScript needed."""

    tiles: list[Tile]
    point_x: int  # the event's position inside the mosaic, in pixels
    point_y: int
    width: int
    height: int


def tile_map(lat: float, lon: float, zoom: int = TILE_ZOOM, cols: int = 5, rows: int = 3) -> TileMap:
    n = 2 ** zoom
    lat = max(min(lat, 85.0), -85.0)
    x = (lon + 180.0) / 360.0 * n * TILE_SIZE
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * TILE_SIZE
    first_col = int(x // TILE_SIZE) - cols // 2
    first_row = min(max(int(y // TILE_SIZE) - rows // 2, 0), n - rows)
    tiles = [
        Tile(
            url=f"https://tile.openstreetmap.org/{zoom}/{(first_col + c) % n}/{first_row + r}.png",
            left=c * TILE_SIZE,
            top=r * TILE_SIZE,
        )
        for r in range(rows)
        for c in range(cols)
    ]
    return TileMap(
        tiles=tiles,
        point_x=round(x - first_col * TILE_SIZE),
        point_y=round(y - first_row * TILE_SIZE),
        width=cols * TILE_SIZE,
        height=rows * TILE_SIZE,
    )


# ---------------------------------------------------------------- sitemap

@dataclass(frozen=True)
class SitemapUrl:
    loc: str
    lastmod: datetime | None = None


def static_urls() -> list[SitemapUrl]:
    """The site's own pages. Collections are left out: their pages are ``noindex``."""
    return [SitemapUrl(external_url(endpoint)) for endpoint in ("public.index", "game.page", "public.about")]


def event_count() -> int:
    return db.session.scalar(select(func.count(Event.id)).where(Event.status == Status.APPROVED)) or 0


def event_urls(offset: int = 0, limit: int | None = None) -> list[SitemapUrl]:
    query = (select(Event.id, Event.title, Event.updated_at)
             .where(Event.status == Status.APPROVED).order_by(Event.id).offset(offset))
    if limit is not None:
        query = query.limit(limit)
    return [
        SitemapUrl(absolute(url_for("public.event_page", event_id=id_, slug=slugify(title))), updated)
        for id_, title, updated in db.session.execute(query)
    ]


def sitemap_page_count() -> int:
    """How many event sitemaps are needed when everything does not fit in one file."""
    return max(1, math.ceil(event_count() / SITEMAP_LIMIT))


def fits_one_sitemap() -> bool:
    return len(static_urls()) + event_count() <= SITEMAP_LIMIT


def urlset_xml(urls: list[SitemapUrl]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        lastmod = f"<lastmod>{url.lastmod.date().isoformat()}</lastmod>" if url.lastmod else ""
        lines.append(f"<url><loc>{escape(url.loc)}</loc>{lastmod}</url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def sitemap_index_xml(locations: list[str]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lines += [f"<sitemap><loc>{escape(loc)}</loc></sitemap>" for loc in locations]
    lines.append("</sitemapindex>")
    return "\n".join(lines) + "\n"


def robots_txt() -> str:
    return "\n".join([
        "User-agent: *",
        "Disallow: /admin",
        "Disallow: /api/",
        "Disallow: /submit",
        "",
        f"Sitemap: {external_url('seo.sitemap')}",
        "",
    ])
