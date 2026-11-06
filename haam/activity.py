"""What changed recently: for the admin "Recent activity" page."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from haam.extensions import db
from haam.models import Collection, CollectionEntry, CollectionReport, Event

PERIODS = {1: "24 hours", 7: "7 days", 30: "30 days"}
LIST_LIMIT = 100  # rows shown per section; the counts are always complete


@dataclass
class Activity:
    since: datetime
    submitted: list[Event] = field(default_factory=list)
    submitted_count: int = 0
    imported_count: int = 0
    collections: list[Collection] = field(default_factory=list)
    collections_count: int = 0
    entries: list[CollectionEntry] = field(default_factory=list)
    entries_count: int = 0
    reports: list[CollectionReport] = field(default_factory=list)
    reports_count: int = 0

    @property
    def is_empty(self) -> bool:
        return not (self.submitted_count or self.imported_count or self.collections_count
                    or self.entries_count or self.reports_count)


def _count(model, *where) -> int:
    return db.session.scalar(select(func.count(model.id)).where(*where)) or 0


def recent_activity(days: int, now: datetime | None = None) -> Activity:
    """Everything created in the last ``days`` days, newest first."""
    # Timestamps are stored as naive UTC.
    now = (now or datetime.now(timezone.utc)).replace(tzinfo=None)
    since = now - timedelta(days=days)
    activity = Activity(since=since)

    new_event = Event.created_at >= since
    activity.submitted_count = _count(Event, new_event, Event.from_website.is_(True))
    activity.imported_count = _count(Event, new_event, Event.from_website.is_(False))
    activity.submitted = list(db.session.scalars(
        select(Event).where(new_event, Event.from_website.is_(True))
        .order_by(Event.created_at.desc()).limit(LIST_LIMIT)))

    new_collection = Collection.created_at >= since
    activity.collections_count = _count(Collection, new_collection)
    activity.collections = list(db.session.scalars(
        select(Collection).where(new_collection).order_by(Collection.created_at.desc()).limit(LIST_LIMIT)))

    new_entry = CollectionEntry.created_at >= since
    activity.entries_count = _count(CollectionEntry, new_entry)
    activity.entries = list(db.session.scalars(
        select(CollectionEntry).where(new_entry)
        .options(selectinload(CollectionEntry.collection), selectinload(CollectionEntry.event))
        .order_by(CollectionEntry.created_at.desc()).limit(LIST_LIMIT)))

    new_report = CollectionReport.created_at >= since
    activity.reports_count = _count(CollectionReport, new_report)
    activity.reports = list(db.session.scalars(
        select(CollectionReport).where(new_report)
        .options(selectinload(CollectionReport.collection))
        .order_by(CollectionReport.created_at.desc()).limit(LIST_LIMIT)))
    return activity
