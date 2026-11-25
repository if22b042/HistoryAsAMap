"""Story mode: a collection or a tag played step by step on a map.

The story page embeds one JSON payload (``collection_story`` / ``tag_story``); the player script reads it.
"""

from __future__ import annotations

from flask import url_for

from haam import collections_service, seo, tag_tree
from haam.dates import format_year
from haam.events import public_id
from haam.models import make_excerpt

MIN_CHAPTER_STEPS = 20  # shorter stories get no chapter list
SEPARATOR = " › "


def _step(*, title, date, year, lat, lon, category, custom, note, text, link, link_label,
          country=None, part=None) -> dict:
    return {"title": title, "date": date, "year": year, "lat": round(lat, 5), "lon": round(lon, 5),
            "category": category, "custom": custom, "note": note, "text": text, "link": link,
            "link_label": link_label, "country": country, "part": part}


def _entry_link(entry) -> tuple[str | None, str | None]:
    """The page a collection entry points to: its event page, or a web link a person typed."""
    if entry.is_confirmed:
        return seo.event_path(entry.event), "Event page"
    if not entry.is_event and entry.link and entry.link.startswith(("http://", "https://")):
        return entry.link, "Read on Wikipedia" if entry.wiki_verified else "Source"
    return None, None  # also an event that is no longer approved


def collection_steps(collection) -> list[dict]:
    """The collection's entries, in their own order."""
    steps = []
    for entry in collection.entries:
        if entry.lat is None or entry.lon is None:
            continue
        link, link_label = _entry_link(entry)
        steps.append(_step(
            title=entry.title, date=entry.date_label or entry.display_year, year=entry.year,
            lat=entry.lat, lon=entry.lon, category=entry.category.value, custom=not entry.is_event,
            note=entry.note or "", text=make_excerpt(entry.summary), link=link, link_label=link_label))
    return steps


def _walk(node: dict, trail: tuple[str, ...] = ()):
    """Every node of the tree with the labels above it, root first."""
    yield node, trail
    for child in node.get("children", []):
        yield from _walk(child, (*trail, node["label"]))


def _tag_story_parts(tag, year_from, year_to, part_qid):
    """:func:`tag_steps` plus the labels above the part node (for the page's intro)."""
    tree = tag_tree.tag_tree(tag)
    part_node, part_trail, wanted = None, (), None
    if part_qid:
        for node, trail in _walk(tree):
            if node.get("qid") == part_qid:
                part_node, part_trail = node, trail
                wanted = {n["event"] for n, _ in _walk(node) if "event" in n}
                break

    # An event right under the root has no breadcrumb: the tag name says it all.
    crumbs = {node["event"]: SEPARATOR.join(trail) if len(trail) > 1 else None
              for node, trail in _walk(tree) if "event" in node}
    parts: list[str] = []
    steps = []
    for event in collections_service.tag_events(tag.id, year_from, year_to):
        pid = public_id(event)
        if wanted is not None and pid not in wanted:
            continue
        crumb = crumbs.get(pid)
        if crumb is not None and crumb not in parts:
            parts.append(crumb)
        steps.append(_step(
            title=event.title, date=event.date_label or event.display_year, year=event.year,
            lat=event.lat, lon=event.lon, category=event.category.value, custom=False, note="",
            text=event.excerpt, link=seo.event_path(event), link_label="Event page",
            country=event.country or None, part=parts.index(crumb) if crumb is not None else None))
    return steps, parts, part_node, part_trail


def tag_steps(tag, year_from: int | None, year_to: int | None,
              part_qid: str | None) -> tuple[list[dict], list[str], dict | None]:
    """A tag's approved events in date order, as ``(steps, parts, part_node)``.

    ``parts`` holds the breadcrumbs the steps point to; ``part_node`` is the tree node
    used for ``part_qid`` (None when no part was asked for or it was not found).
    """
    steps, parts, part_node, _ = _tag_story_parts(tag, year_from, year_to, part_qid)
    return steps, parts, part_node


def chapters(steps: list[dict]) -> list[dict]:
    """Jump points for a long story: one per year, decade or century, depending on the span."""
    if len(steps) < MIN_CHAPTER_STEPS:
        return []
    span = steps[-1]["year"] - steps[0]["year"]
    size = 1 if span <= 30 else 10 if span <= 300 else 100
    found: list[dict] = []
    seen: set[int] = set()
    for index, step in enumerate(steps):
        start = step["year"] // size * size  # floor division is right for negative years too
        if start in seen:
            continue
        seen.add(start)
        label = format_year(start) if size == 1 else f"{format_year(start)} – {format_year(start + size - 1)}"
        found.append({"label": label, "first": index})
    return found if len(found) > 1 else []


def _years(steps: list[dict]) -> str:
    if not steps:
        return ""
    first, last = format_year(steps[0]["year"]), format_year(steps[-1]["year"])
    return first if first == last else f"{first} – {last}"


def _payload(*, kind, title, intro, steps, parts, back_url, back_label, path_default,
             story_endpoint, embed_endpoint, **url_args) -> dict:
    return {
        "kind": kind, "title": title, "intro": intro, "years": _years(steps), "count": len(steps),
        "back_url": back_url, "back_label": back_label,
        "story_url": url_for(story_endpoint, _external=True, **url_args),
        "embed_url": url_for(embed_endpoint, _external=True, **url_args),
        "path_default": path_default, "steps": steps, "parts": parts, "chapters": chapters(steps),
    }


def collection_story(collection) -> dict:
    return _payload(
        kind="collection", title=collection.title, intro=collection.description or "",
        steps=collection_steps(collection), parts=[],
        back_url=url_for("collections.view", view_token=collection.view_token),
        back_label="Back to the collection", path_default=True,
        story_endpoint="collections.story", embed_endpoint="collections.embed",
        view_token=collection.view_token)


def tag_story(tag, year_from: int | None, year_to: int | None, part_qid: str | None) -> dict:
    steps, parts, part_node, part_trail = _tag_story_parts(tag, year_from, year_to, part_qid)
    title, intro = tag.name, tag.display_range
    if part_node is not None:
        title, intro = part_node["label"], "Part of " + SEPARATOR.join(part_trail)
    given = {"tag": tag.id, "part": part_qid, "from": year_from, "to": year_to}
    return _payload(
        kind="tag", title=title, intro=intro, steps=steps, parts=parts,
        back_url=url_for("public.index", **{k: v for k, v in given.items() if v is not None}),
        back_label="Back to the map", path_default=False,
        story_endpoint="public.tag_story", embed_endpoint="public.tag_story_embed", tag_id=tag.id)
