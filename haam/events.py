"""Business logic for events: lookup, submission, moderation."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from haam.extensions import db
from haam.geocoding import country_for
from haam.models import Category, Event, Status, Tag
from haam.wikipedia import Article, WikipediaError, get_client, title_from_url


class EventError(Exception):
    """A user-facing problem (bad link, duplicate, Wikipedia unavailable...)."""

    def __init__(self, message: str, existing: Event | None = None):
        super().__init__(message)
        self.message = message
        self.existing = existing


@dataclass
class EventData:
    """Validated values for creating or updating an event."""

    title: str
    year: int
    date_label: str
    summary: str
    lat: float
    lon: float
    category: Category
    tag_ids: list[int] = field(default_factory=list)

    @classmethod
    def from_form(cls, form) -> "EventData":
        return cls(
            title=form.title.data.strip(),
            year=form.year.year,
            date_label=(form.date_label.data or "").strip(),
            summary=form.summary.data.strip(),
            lat=form.lat.data,
            lon=form.lon.data,
            category=Category(form.category.data),
            tag_ids=list(form.tags.data or []),
        )


# ---------------------------------------------------------------- queries

def approved_events() -> list[Event]:
    stmt = (
        select(Event)
        .where(Event.status == Status.APPROVED)
        .order_by(Event.year, Event.title)
        .options(selectinload(Event.tags))
    )
    return list(db.session.scalars(stmt))


def events_with_status(status: Status) -> list[Event]:
    stmt = select(Event).where(Event.status == status).order_by(Event.created_at.desc())
    return list(db.session.scalars(stmt))


def all_tags() -> list[Tag]:
    return sorted(db.session.scalars(select(Tag)), key=lambda t: (t.sort_year, t.name))


def find_existing(url: str, page_id: int | None = None) -> Event | None:
    conditions = [Event.wiki_url == url]
    if page_id is not None:
        conditions.append(Event.wiki_page_id == page_id)
    return db.session.scalars(select(Event).where(or_(*conditions))).first()


def get_event_or_none(event_id: int) -> Event | None:
    return db.session.get(Event, event_id)


# ------------------------------------------------------------ Wikipedia

def fetch_article(url: str) -> Article:
    """Look up the article behind ``url``; raises :class:`EventError` for anything unusable."""
    title = title_from_url(url)
    if title is None:
        raise EventError("Only English Wikipedia article links are supported (https://en.wikipedia.org/wiki/...).")
    try:
        article = get_client().fetch_article(title)
    except WikipediaError as exc:
        raise EventError("Wikipedia could not be reached. Please try again in a moment.") from exc
    if article is None:
        raise EventError("That Wikipedia article does not exist.")
    return article


def preview(url: str) -> Article:
    """Fetch an article for review, refusing ones that are already on the map."""
    article = fetch_article(url)
    existing = find_existing(article.url, article.page_id)
    if existing is not None:
        raise EventError("This article has already been added.", existing=existing)
    return article


# ------------------------------------------------------------- changes

def _tags_by_id(tag_ids: list[int]) -> list[Tag]:
    if not tag_ids:
        return []
    return list(db.session.scalars(select(Tag).where(Tag.id.in_(tag_ids))))


def _differs_from(article: Article, data: EventData) -> bool:
    def close(a, b):
        return a is not None and abs(a - b) < 1e-6

    return not (
        data.title == article.title
        and data.year == article.year
        and data.date_label == article.date_label
        and data.summary == article.summary
        and close(article.lat, data.lat)
        and close(article.lon, data.lon)
    )


def create_event(article: Article, data: EventData, status: Status = Status.PENDING) -> Event:
    """Store a new event. Submissions from the website start as ``pending``."""
    event = Event(
        title=data.title,
        year=data.year,
        date_label=data.date_label,
        summary=data.summary,
        wiki_url=article.url,
        wiki_page_id=article.page_id,
        lat=data.lat,
        lon=data.lon,
        country=country_for(data.lat, data.lon),
        category=data.category,
        status=status,
        modified=_differs_from(article, data),
        tags=_tags_by_id(data.tag_ids),
    )
    db.session.add(event)
    try:
        db.session.commit()
    except IntegrityError as exc:  # someone added the same article a moment ago
        db.session.rollback()
        raise EventError("This article has already been added.", existing=find_existing(article.url)) from exc
    return event


def submit(url: str, data: EventData) -> Event:
    """Handle a submission from the website (re-checks the article server-side)."""
    article = preview(url)
    return create_event(article, data)


def update_event(event: Event, data: EventData) -> Event:
    location_changed = (event.lat, event.lon) != (data.lat, data.lon)
    event.title = data.title
    event.year = data.year
    event.date_label = data.date_label
    event.summary = data.summary
    event.lat, event.lon = data.lat, data.lon
    event.category = data.category
    event.tags = _tags_by_id(data.tag_ids)
    event.modified = True
    if location_changed:
        event.country = country_for(data.lat, data.lon)
    db.session.commit()
    return event


def set_status(event: Event, status: Status) -> Event:
    event.status = status
    db.session.commit()
    return event


def delete_event(event: Event) -> None:
    db.session.delete(event)
    db.session.commit()


def suggested_tag_ids(year: int | None) -> set[int]:
    """Tags whose time span contains ``year`` – shown first in the tag picker."""
    if year is None:
        return set()
    return {tag.id for tag in all_tags() if tag.covers(year)}
