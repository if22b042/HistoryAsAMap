"""Tag landing pages (/tag/<id>-<slug>): what a tag's page shows besides its events.

Everything is read from the database and ``part_of.json`` at request time with a fixed number
of queries, however many events the tag has.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from flask import url_for
from sqlalchemy import func, select

from haam import seo
from haam.collections_service import MAX_ENTRIES, tag_events
from haam.dates import format_year
from haam.extensions import db
from haam.models import Category, Event, Status, Tag, event_tags
from haam.tag_tree import narrower_tags, tag_tree
from haam.tagging import TAG_PARENTS

TIMELINE_BARS = 40  # at most this many bars in the timeline
BIN_SIZES = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000)
NEIGHBOUR_LIMIT = 6
# A tag shares this much of the smaller tag's events with it: it is broader or narrower.
CONTAINS = 0.8


@dataclass
class Stats:
    count: int
    first: int
    last: int
    countries: int
    categories: list[tuple[Category, int]]  # most common first


@dataclass
class Bar:
    label: str
    count: int
    height: int  # percent of the tallest bar
    anchor: int | None  # the year of the bar's first event, an anchor in the event list


@dataclass
class Neighbour:
    tag: Tag
    count: int  # approved events of that tag


def stats(events: list[Event]) -> Stats:
    """Key numbers of a tag's events (``events`` is not empty)."""
    years = [e.year for e in events]
    categories = Counter(e.category for e in events).most_common()
    return Stats(count=len(events), first=min(years), last=max(years),
                 countries=len({e.country for e in events if e.country}), categories=categories)


def timeline(events: list[Event]) -> list[Bar]:
    """Events per year, or per 2, 5, 10 … years so there are at most ``TIMELINE_BARS`` bars.

    Empty when all events fall in one bar: a single bar says nothing.
    """
    years = sorted(e.year for e in events)
    first, last = years[0], years[-1]
    size = next(s for s in BIN_SIZES if (last // s) - (first // s) + 1 <= TIMELINE_BARS)
    start = first // size * size
    counts = Counter((y - start) // size for y in years)
    bins = (last - start) // size + 1
    if bins < 2:
        return []
    anchors: dict[int, int] = {}
    for y in years:
        anchors.setdefault((y - start) // size, y)
    tallest = max(counts.values())
    bars = []
    for i in range(bins):
        low = start + i * size
        label = format_year(low) if size == 1 else f"{format_year(low)} – {format_year(low + size - 1)}"
        count = counts.get(i, 0)
        bars.append(Bar(label, count, max(round(count / tallest * 100), 4) if count else 0, anchors.get(i)))
    return bars


def approved_counts() -> dict[int, int]:
    """Tag id → number of approved events."""
    return dict(db.session.execute(
        select(event_tags.c.tag_id, func.count(Event.id)).join(Event, Event.id == event_tags.c.event_id)
        .where(Event.status == Status.APPROVED).group_by(event_tags.c.tag_id)).all())


def _overlap(a: Tag, b: Tag) -> int:
    """Years two tags share (an ongoing tag runs to this year)."""
    now = date.today().year
    start = max(a.start_year if a.start_year is not None else -10**6, b.start_year if b.start_year is not None else -10**6)
    end = min(a.end_year if a.end_year is not None else now, b.end_year if b.end_year is not None else now)
    return max(end - start + 1, 0)


def neighbours(tag: Tag, count: int) -> dict[str, list[Neighbour]]:
    """Broader, narrower and related tags, and tags of the same years.

    Broader and narrower come from shared events (most of one tag's events also carry the other)
    and from TAG_PARENTS; related tags share some events; "same time" tags share at least half
    of the years of each (an empire is not "at the same time" as one of its wars).
    Only tags with approved events are listed.
    """
    counts = approved_counts()
    mine = (select(event_tags.c.event_id).join(Event, Event.id == event_tags.c.event_id)
            .where(event_tags.c.tag_id == tag.id, Event.status == Status.APPROVED))
    shared = dict(db.session.execute(
        select(event_tags.c.tag_id, func.count()).where(event_tags.c.event_id.in_(mine), event_tags.c.tag_id != tag.id)
        .group_by(event_tags.c.tag_id)).all())
    tags = {t.id: t for t in db.session.scalars(select(Tag)) if counts.get(t.id) and t.id != tag.id}
    broader_names = set(TAG_PARENTS.get(tag.name, []))
    narrower_names = narrower_tags(tag.name)

    groups: dict[str, list[Neighbour]] = {"broader": [], "narrower": [], "related": [], "same_time": []}
    for tag_id, both in sorted(shared.items(), key=lambda item: -item[1]):
        other = tags.get(tag_id)
        if other is None:
            continue
        total = counts[tag_id]
        item = Neighbour(other, total)
        if other.name in broader_names or (total > count and both >= CONTAINS * count):
            groups["broader"].append(item)
        elif other.name in narrower_names or (total < count and both >= CONTAINS * total):
            groups["narrower"].append(item)
        elif len(groups["related"]) < NEIGHBOUR_LIMIT and both >= 2:
            groups["related"].append(item)
    listed = {n.tag.id for group in groups.values() for n in group}
    span = _overlap(tag, tag)
    same_time = [t for t in tags.values() if t.id not in listed and counts[t.id] >= seo.TAG_PAGE_MIN_EVENTS
                 and _overlap(tag, t) * 2 >= max(span, _overlap(t, t))]
    same_time.sort(key=lambda t: (-counts[t.id], t.name))
    groups["same_time"] = [Neighbour(t, counts[t.id]) for t in same_time[:NEIGHBOUR_LIMIT]]
    return groups


def parts(tag: Tag) -> list[dict]:
    """The tag tree's branches (parts with parts or events of their own), largest first.

    Each branch, and each of its own branches, gets a ``path`` when it has a page of its own:
    a tag page when it is another tag, an event page when it is itself an event.
    """
    branches = [node for node in tag_tree(tag).get("children", []) if node.get("children")]
    for node in branches:
        node["children"] = [child for child in node["children"] if child.get("children")]
    nodes = branches + [child for node in branches for child in node["children"]]
    tag_ids = {node["tag"] for node in nodes if "tag" in node}
    tags = {t.id: t for t in db.session.scalars(select(Tag).where(Tag.id.in_(tag_ids)))} if tag_ids else {}
    for node in nodes:
        node["label"] = node["label"][:1].upper() + node["label"][1:]  # Wikidata labels can be lower case
        if node.get("tag") in tags:
            node["path"] = seo.tag_path(tags[node["tag"]])
        elif "event" in node:
            node["path"] = url_for("public.event_page", event_id=node["event"], slug=seo.slugify(node["label"]))
    return branches


# ------------------------------------------------------------ hooks for features still to come

def key_events(tag: Tag, events: list[Event]) -> list[Event]:
    """The tag's most important events. Empty until events have an importance score (sitelinks)."""
    return []


def story_url(tag: Tag) -> str | None:
    """Where "Play as a story" goes for this tag: its events one by one, oldest first (haam/story.py)."""
    return url_for("public.tag_story", tag_id=tag.id)


# ------------------------------------------------------------ the page

def page(tag: Tag) -> dict | None:
    """Everything the tag page template needs, or None when the tag has no approved events."""
    events = tag_events(tag.id)
    if not events:
        return None
    numbers = stats(events)
    return {
        "tag": tag,
        "events": events,
        "stats": numbers,
        "timeline": timeline(events),
        "area_map": seo.area_map([(e.lat, e.lon, e.category.value) for e in events]),
        "parts": parts(tag),
        "neighbours": neighbours(tag, numbers.count),
        "key_events": key_events(tag, events),
        "story_url": story_url(tag),
        "indexed": numbers.count >= seo.TAG_PAGE_MIN_EVENTS,
        "max_entries": MAX_ENTRIES,
    }
