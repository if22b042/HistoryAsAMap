"""The map's event data, sent compactly in chunks that browsers and the CDN keep for good.

The map first needs every approved event's position, year, title, category and
tags ("core"); the short descriptions ("text") are by far the largest part and
only matter for the popups, the list and searching descriptions, so they come
separately, after the core data.

Both are split into ``CHUNKS``: an event belongs to a chunk by ``id % MODULUS``,
so every chunk is a thin, even sample of the whole map (the first one draws a
sparse version of the full picture) and an event's chunk is known from its id
alone. The first chunk is the smallest, so the first markers appear quickly.

Every URL carries a ``version``: a fingerprint of the events, their tags and the
tag list. Any change gives new URLs, so responses can be cached as immutable;
an unchanged map is never downloaded twice.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import func, select

from haam.dates import format_year
from haam.extensions import db
from haam.models import Category, Event, Status, Tag, event_tags, make_excerpt

MODULUS = 20
# Chunk n holds the events with BOUNDS[n] <= id % MODULUS < BOUNDS[n + 1]:
# 10 %, 25 %, 30 % and 35 % of the events.
BOUNDS = (0, 2, 7, 13, 20)
CHUNKS = len(BOUNDS) - 1

WIKI_PREFIX = "https://en.wikipedia.org/wiki/"
CATEGORIES = [c.value for c in Category]
# Bump when the shape of a chunk changes, so browsers never mix old and new formats.
FORMAT = 1


def state() -> dict:
    """The version fingerprint plus what the page needs before any chunk arrives."""
    approved = Event.status == Status.APPROVED
    row = db.session.execute(select(
        select(func.count(Event.id)).where(approved).scalar_subquery(),
        select(func.min(Event.year)).where(approved).scalar_subquery(),
        select(func.max(Event.year)).where(approved).scalar_subquery(),
        # Any edit, approval or rejection touches updated_at; deletions change the count.
        select(func.max(Event.updated_at)).scalar_subquery(),
        select(func.count(Event.id)).scalar_subquery(),
        # Tags changed on an event leave its row alone, so they are fingerprinted separately.
        select(func.count()).select_from(event_tags).scalar_subquery(),
        select(func.sum(event_tags.c.event_id * 7919 + event_tags.c.tag_id)).scalar_subquery(),
        select(func.count(Tag.id)).scalar_subquery(),
        select(func.sum(func.length(Tag.name) * 31 + func.coalesce(Tag.start_year, 0)
                        + func.coalesce(Tag.end_year, 1))).scalar_subquery(),
    )).one()
    total, min_year, max_year = row[0], row[1], row[2]
    # Bulk recategorisations (migrations, `flask haam recategorize`, sync-wikidata) leave
    # updated_at alone, so the events per category are fingerprinted too, with the list of
    # categories itself (the chunks store categories as indexes into it).
    per_category = sorted((c.value, n) for c, n in db.session.execute(
        select(Event.category, func.count(Event.id)).where(approved).group_by(Event.category)))
    digest = hashlib.sha1(repr((tuple(row), tuple(per_category), tuple(CATEGORIES), MODULUS, BOUNDS,
                                FORMAT)).encode()).hexdigest()
    return {"version": digest[:12], "total": total, "years": [min_year, max_year]}


def manifest(url_for) -> dict:
    """Everything the map needs to start loading: the version and every chunk's URL."""
    current = state()
    version = current["version"]
    return {
        **current,
        "modulus": MODULUS,
        "bounds": list(BOUNDS),
        "tags": url_for("api.feed_tags", version=version),
        "core": [url_for("api.feed_core", version=version, chunk=n) for n in range(CHUNKS)],
        "text": [url_for("api.feed_text", version=version, chunk=n) for n in range(CHUNKS)],
    }


def _in_chunk(chunk: int):
    residue = Event.id % MODULUS
    return (Event.status == Status.APPROVED) & (residue >= BOUNDS[chunk]) & (residue < BOUNDS[chunk + 1])


def _wiki_field(url: str, title: str) -> str:
    """"" = the title's own article; otherwise the article name; a full URL only if it is not en.wikipedia."""
    if not url.startswith(WIKI_PREFIX):
        return url
    name = url[len(WIKI_PREFIX):]
    return "" if name == title.replace(" ", "_") else name


def core_chunk(chunk: int, version: str) -> dict:
    """One chunk of the map's events, as columns (no repeated keys), ordered by year and title."""
    rows = db.session.execute(
        select(Event.id, Event.title, Event.year, Event.date_label, Event.wiki_url,
               Event.lat, Event.lon, Event.category)
        .where(_in_chunk(chunk))
        .order_by(Event.year, Event.title, Event.id)
    ).all()
    tags: dict[int, list[int]] = {}
    tag_rows = db.session.execute(
        select(event_tags.c.event_id, event_tags.c.tag_id)
        .join(Event, Event.id == event_tags.c.event_id)
        .join(Tag, Tag.id == event_tags.c.tag_id)
        .where(_in_chunk(chunk))
        .order_by(Tag.start_year, Tag.id)
    )
    for event_id, tag_id in tag_rows:
        tags.setdefault(event_id, []).append(tag_id)

    category_index = {value: i for i, value in enumerate(CATEGORIES)}
    return {
        "v": version,
        "chunk": chunk,
        "count": len(rows),
        "categories": CATEGORIES,
        "id": [r.id for r in rows],
        "title": [r.title for r in rows],
        "year": [r.year for r in rows],
        # "" = just the year (the client formats it the same way as format_year).
        "date": [("" if r.date_label == format_year(r.year) else r.date_label) for r in rows],
        "wiki": [_wiki_field(r.wiki_url, r.title) for r in rows],
        # 4 decimals: about 10 m, far finer than any marker.
        "lat": [round(r.lat, 4) for r in rows],
        "lon": [round(r.lon, 4) for r in rows],
        "cat": [category_index[r.category.value] for r in rows],
        "tags": [tags.get(r.id, []) for r in rows],
    }


def text_chunk(chunk: int, version: str) -> dict:
    """The short descriptions of one chunk's events."""
    # One character more than an excerpt, which is enough to tell whether it was cut.
    rows = db.session.execute(
        select(Event.id, func.substr(Event.summary, 1, Event.EXCERPT_LENGTH + 1))
        .where(_in_chunk(chunk))
        .order_by(Event.id)
    ).all()
    return {
        "v": version,
        "chunk": chunk,
        "id": [r[0] for r in rows],
        "excerpt": [make_excerpt(r[1]) for r in rows],
    }
