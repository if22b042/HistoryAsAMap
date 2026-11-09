"""The map's welcome card: "On this day", today's game and featured collections."""

from __future__ import annotations

from datetime import date

from flask import url_for
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from haam import game
from haam.dates import MONTHS, valid_month_day
from haam.extensions import db
from haam.models import Collection, CollectionEntry, CollectionReport, Event, Status

ON_THIS_DAY = 5
FEATURED_COLLECTIONS = 3
MONTH_NAMES = MONTHS.split("|")


def on_this_day(month: int, day: int, limit: int = ON_THIS_DAY) -> list[Event]:
    """The best approved events that happened on this day and month, oldest first.

    "Best" prefers events with tags (they belong to a known war or era), then
    longer summaries. The picks are spread over different centuries, with at most
    ``limit // 2 + 1`` of one category, when the day has enough events.
    """
    candidates = db.session.scalars(
        select(Event).options(selectinload(Event.tags))
        .where(Event.status == Status.APPROVED, Event.month == month, Event.day == day)
    ).all()
    ranked = sorted(candidates, key=lambda e: (-min(len(e.tags), 2), -len(e.summary or ""), e.id))
    picked: list[Event] = []
    centuries: set[int] = set()
    per_category: dict = {}
    for event in ranked:
        if (len(picked) < limit and event.year // 100 not in centuries
                and per_category.get(event.category, 0) <= limit // 2):
            picked.append(event)
            centuries.add(event.year // 100)
            per_category[event.category] = per_category.get(event.category, 0) + 1
    for event in ranked:  # fewer centuries than places: fill with the next best
        if len(picked) < limit and event not in picked:
            picked.append(event)
    return sorted(picked, key=lambda e: e.year)


def days_without_events() -> list[tuple[int, int]]:
    """Calendar days (month, day), 29 February included, with no approved event."""
    covered = set(db.session.execute(
        select(Event.month, Event.day).where(Event.status == Status.APPROVED, Event.month.is_not(None))
        .group_by(Event.month, Event.day)).all())
    return [(m, d) for m in range(1, 13) for d in range(1, 32)
            if valid_month_day(m, d) and (m, d) not in covered]


def featured_collections(limit: int = FEATURED_COLLECTIONS) -> list[tuple[Collection, int]]:
    """Public collections that are neither hidden nor reported: most entries first, then newest."""
    entries = (select(CollectionEntry.collection_id, func.count(CollectionEntry.id).label("n"))
               .group_by(CollectionEntry.collection_id).subquery())
    reported = select(CollectionReport.id).where(CollectionReport.collection_id == Collection.id).exists()
    rows = db.session.execute(
        select(Collection, entries.c.n).join(entries, entries.c.collection_id == Collection.id)
        .where(Collection.is_public.is_(True), Collection.is_hidden.is_(False), ~reported)
        .order_by(entries.c.n.desc(), Collection.created_at.desc(), Collection.id.desc())
        .limit(limit)
    ).all()
    return [(collection, count) for collection, count in rows]


def payload(month: int, day: int) -> dict:
    today = game.today_utc()
    return {
        "day_label": f"{day} {MONTH_NAMES[month - 1]}",
        "on_this_day": [
            {"id": e.id, "title": e.title, "year": e.year, "display_year": e.display_year,
             "date": e.date_label, "excerpt": e.excerpt, "category": e.category.value}
            for e in on_this_day(month, day)
        ],
        "game": {"url": url_for("game.page"), "number": game.game_number(today)},
        "collections": [
            {"title": c.title, "url": url_for("collections.view", view_token=c.view_token),
             "entries": count, "years": c.year_span}
            for c, count in featured_collections()
        ],
    }


def requested_day(month: str | None, day: str | None, today: date | None = None) -> tuple[int, int]:
    """The visitor's local day from the query string, or today (UTC) if missing or invalid."""
    try:
        m, d = int(month or ""), int(day or "")
    except ValueError:
        m = d = 0
    if valid_month_day(m, d):
        return m, d
    today = today or game.today_utc()
    return today.month, today.day
