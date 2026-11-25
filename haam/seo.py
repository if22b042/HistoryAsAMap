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

from haam.events import PUBLIC_ID, public_id
from haam.extensions import db
from haam.models import Event, Status, Tag, event_tags

SITE_NAME = "History As A Map"
DEFAULT_DESCRIPTION = (
    "An interactive map of about 19,000 historical events from Wikipedia: battles, treaties, "
    "discoveries and disasters, filtered by year, category and era."
)
DESCRIPTION_LENGTH = 160
SLUG_LENGTH = 80
# A sitemap file may list at most 50,000 URLs; larger sets are split behind a sitemap index.
SITEMAP_LIMIT = 50_000
# Tags with fewer approved events still have a page, but it is ``noindex`` and not in the sitemap.
TAG_PAGE_MIN_EVENTS = 3


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
    """The event's address: /event/<Wikipedia page id>-<slug> (the row id when it has no page id)."""
    return url_for("public.event_page", event_id=public_id(event), slug=slugify(event.title))


def tag_path(tag: Tag) -> str:
    """The tag's address: /tag/<id>-<slug>. The id keeps links working when the tag is renamed."""
    return url_for("public.tag_page", tag_id=tag.id, slug=slugify(tag.name))


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
class Dot:
    x: int  # position inside the mosaic, in pixels
    y: int
    category: str


@dataclass(frozen=True)
class TileMap:
    """A small static map: OpenStreetMap tiles around a point, no JavaScript needed."""

    tiles: list[Tile]
    point_x: int  # the event's position (or the centre of the dots) inside the mosaic, in pixels
    point_y: int
    width: int
    height: int
    dots: tuple[Dot, ...] = ()


def _pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Web Mercator position of a point at ``zoom``, in pixels from the world's top left corner."""
    size = 2 ** zoom * TILE_SIZE
    lat = max(min(lat, 85.0), -85.0)
    return ((lon + 180.0) / 360.0 * size,
            (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * size)


def _mosaic(x: float, y: float, zoom: int, cols: int, rows: int) -> tuple[list[Tile], int, int]:
    """The tiles around pixel (x, y), and the mosaic's top left corner in world pixels."""
    n = 2 ** zoom
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
    return tiles, first_col * TILE_SIZE, first_row * TILE_SIZE


def tile_map(lat: float, lon: float, zoom: int = TILE_ZOOM, cols: int = 5, rows: int = 3) -> TileMap:
    x, y = _pixel(lat, lon, zoom)
    tiles, left, top = _mosaic(x, y, zoom, cols, rows)
    return TileMap(tiles=tiles, point_x=round(x - left), point_y=round(y - top),
                   width=cols * TILE_SIZE, height=rows * TILE_SIZE)


# Three rows of tiles need a world at least four tiles tall.
AREA_ZOOMS = range(7, 1, -1)
# The box the events should fit in, in pixels: small enough for the map on a phone (about 290 x 280).
AREA_FIT = (260, 200)


def area_map(points: list[tuple[float, float, str]], cols: int = 5, rows: int = 3) -> TileMap | None:
    """A static map of many points ``(lat, lon, category)``, zoomed to fit most of them.

    The outer 5% on each side are left out when choosing the zoom, so one far-off event does not
    zoom the map out to the whole world; dots closer than a few pixels are drawn once.
    """
    if not points:
        return None
    lats = sorted(p[0] for p in points)
    lons = sorted(p[1] for p in points)
    trim = len(points) // 20
    south, north, west, east = lats[trim], lats[-1 - trim], lons[trim], lons[-1 - trim]
    for zoom in AREA_ZOOMS:
        x0, y0 = _pixel(north, west, zoom)
        x1, y1 = _pixel(south, east, zoom)
        if x1 - x0 <= AREA_FIT[0] and y1 - y0 <= AREA_FIT[1]:
            break
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    tiles, left, top = _mosaic(cx, cy, zoom, cols, rows)
    width, height, world = cols * TILE_SIZE, rows * TILE_SIZE, 2 ** zoom * TILE_SIZE
    dots, seen = [], set()
    for lat, lon, category in points:
        x, y = _pixel(lat, lon, zoom)
        x, y = x - left, y - top
        if x < 0:
            x += world  # the mosaic wraps around the antimeridian
        elif x >= width:
            x -= world
        cell = (int(x) // 4, int(y) // 4)
        if 0 <= x < width and 0 <= y < height and cell not in seen:
            seen.add(cell)
            dots.append(Dot(round(x), round(y), category))
    return TileMap(tiles=tiles, point_x=round(cx - left), point_y=round(cy - top),
                   width=width, height=height, dots=tuple(dots))


# ---------------------------------------------------------------- sitemap

@dataclass(frozen=True)
class SitemapUrl:
    loc: str
    lastmod: datetime | None = None


def static_urls() -> list[SitemapUrl]:
    """The site's own pages. Collections are left out: their pages are ``noindex``."""
    return [SitemapUrl(external_url(endpoint)) for endpoint in ("public.index", "game.page", "public.about")]


def tag_urls() -> list[SitemapUrl]:
    """Pages of tags with at least ``TAG_PAGE_MIN_EVENTS`` approved events, dated by their newest change."""
    query = (select(Tag.id, Tag.name, func.max(Event.updated_at))
             .join(event_tags, event_tags.c.tag_id == Tag.id).join(Event, Event.id == event_tags.c.event_id)
             .where(Event.status == Status.APPROVED).group_by(Tag.id, Tag.name)
             .having(func.count(Event.id) >= TAG_PAGE_MIN_EVENTS).order_by(Tag.id))
    return [SitemapUrl(absolute(url_for("public.tag_page", tag_id=id_, slug=slugify(name))), updated)
            for id_, name, updated in db.session.execute(query)]


def page_urls() -> list[SitemapUrl]:
    """Everything but the events: the site's own pages and the tag pages."""
    return static_urls() + tag_urls()


def event_count() -> int:
    return db.session.scalar(select(func.count(Event.id)).where(Event.status == Status.APPROVED)) or 0


def event_urls(offset: int = 0, limit: int | None = None) -> list[SitemapUrl]:
    query = (select(PUBLIC_ID, Event.title, Event.updated_at)
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
    return len(page_urls()) + event_count() <= SITEMAP_LIMIT


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
