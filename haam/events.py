"""Business logic for events: lookup, submission, moderation."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import case, delete, func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from haam.dates import format_year
from haam.extensions import db
from haam.geocoding import country_for
from haam.models import Category, Event, EventReport, ReportStatus, Status, Tag, event_tags
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


def status_counts() -> dict[Status, int]:
    """Number of events per status, counted in the database (one query)."""
    rows = db.session.execute(select(Event.status, func.count(Event.id)).group_by(Event.status))
    counts = {status: 0 for status in Status}
    counts.update({status: count for status, count in rows})
    return counts


def events_page(status: Status, page: int = 1, per_page: int = 50) -> list[Event]:
    """One page of events with ``status``: website submissions first, then newest first."""
    stmt = (
        select(Event)
        .where(Event.status == status)
        .order_by(Event.from_website.desc(), Event.created_at.desc(), Event.id.desc())
        .offset((max(page, 1) - 1) * per_page)
        .limit(per_page)
        .options(selectinload(Event.tags))
    )
    return list(db.session.scalars(stmt))


def all_tags() -> list[Tag]:
    return sorted(db.session.scalars(select(Tag)), key=lambda t: (t.sort_year, t.name))


def find_existing(url: str, page_id: int | None = None) -> Event | None:
    conditions = [Event.wiki_url == url]
    if page_id is not None:
        conditions.append(Event.wiki_page_id == page_id)
    return db.session.scalars(select(Event).where(or_(*conditions))).first()


def get_event_or_none(event_id: int) -> Event | None:
    """An event by its row id (the admin pages; visitors use public ids, below)."""
    return db.session.get(Event, event_id)


# ----------------------------------------------------------- public ids
#
# Public addresses (/event/<id>-slug, /?event=<id>, the map's data, collections' event
# pickers, the game's "show on the map" link) name an event by its Wikipedia page id, which
# survives a re-import; row ids do not. Events without a page id (the column is nullable:
# some imports and tests create them) fall back to their row id.

MAX_PUBLIC_ID = 2**31 - 1  # Wikipedia page ids are far smaller; anything larger cannot exist

# The same value as ``public_id`` in SQL (the map's chunks are chosen by it).
PUBLIC_ID = func.coalesce(Event.wiki_page_id, Event.id)


def public_id(event: Event) -> int:
    """The id that names ``event`` in public addresses and in the map's data."""
    return event.wiki_page_id if event.wiki_page_id is not None else event.id


def find_by_public_id(pid: int | None) -> Event | None:
    """The event (of any status) that ``pid`` names: its page id, else the row id of an event with no page id."""
    if pid is None or not 0 < pid <= MAX_PUBLIC_ID:
        return None
    event = db.session.scalar(select(Event).where(Event.wiki_page_id == pid))
    if event is not None:
        return event
    event = db.session.get(Event, pid)
    return event if event is not None and event.wiki_page_id is None else None


def find_approved(pid: int | None) -> Event | None:
    event = find_by_public_id(pid)
    return event if event is not None and event.status == Status.APPROVED else None


def moved_event(pid: int | None) -> Event | None:
    """For an old link made with a row id: the approved event that row holds, if ``pid`` names no event.

    The caller redirects (301) to the event's current address. Never used when ``pid`` is
    already somebody's page id (or the row id of an event without one): that is a live address.
    """
    if pid is None or not 0 < pid <= MAX_PUBLIC_ID or find_by_public_id(pid) is not None:
        return None
    event = db.session.get(Event, pid)
    return event if event is not None and event.status == Status.APPROVED else None


def public_ids_to_events(pids) -> list[Event]:
    """Approved events named by public ids (unknown ids and duplicates are dropped), in the order given."""
    wanted = [p for p in dict.fromkeys(pids) if isinstance(p, int) and not isinstance(p, bool)
              and 0 < p <= MAX_PUBLIC_ID]
    if not wanted:
        return []
    found: dict[int, Event] = {}
    for event in db.session.scalars(select(Event).where(Event.status == Status.APPROVED,
                                                        Event.wiki_page_id.in_(wanted))):
        found[event.wiki_page_id] = event
    rest = [p for p in wanted if p not in found]
    if rest:
        for event in db.session.scalars(select(Event).where(
                Event.status == Status.APPROVED, Event.id.in_(rest), Event.wiki_page_id.is_(None))):
            found[event.id] = event
    return [found[p] for p in wanted if p in found]


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
    if article.year is None:
        # Neither Wikidata nor the intro gives a date: a town, person or concept, not an event.
        # (An intro date that was parsed wrongly still gets through, with a warning, so it can be fixed.)
        raise EventError(
            "We could not find a date for this article, so it does not look like an event. "
            "Choose an article about something that happened on a particular date or period, "
            "such as a battle, a treaty or an eruption.")
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


def create_event(article: Article, data: EventData, status: Status = Status.PENDING,
                 from_website: bool = False) -> Event:
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
        from_website=from_website,
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
    return create_event(article, data, from_website=True)


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


def bulk_set_status(event_ids, status: Status) -> int:
    """Set ``status`` on the events with these row ids (unknown ids are skipped); returns how many changed.

    Goes through the ORM like :func:`set_status`, so ``updated_at`` moves and the feed version changes.
    """
    ids = {i for i in event_ids if isinstance(i, int)}
    if not ids:
        return 0
    changed = 0
    for event in db.session.scalars(select(Event).where(Event.id.in_(ids))):
        if event.status != status:
            event.status = status
            changed += 1
    db.session.commit()
    return changed


def delete_event(event: Event) -> None:
    db.session.delete(event)
    db.session.commit()


def suggested_tag_ids(year: int | None) -> set[int]:
    """Tags whose time span contains ``year`` – shown first in the tag picker."""
    if year is None:
        return set()
    return {tag.id for tag in all_tags() if tag.covers(year)}


# ------------------------------------------------------------- reports

def create_report(event: Event, form) -> EventReport:
    """Store a visitor's report (from a validated ``EventReportForm``)."""
    report = EventReport(
        event=event,
        message=form.message.data.strip(),
        proposed_year=form.proposed_year.year,
        proposed_date_label=(form.proposed_date_label.data or "").strip() or None,
        proposed_lat=form.proposed_lat.data,
        proposed_lon=form.proposed_lon.data,
    )
    db.session.add(report)
    db.session.commit()
    return report


def open_report_count() -> int:
    return db.session.scalar(select(func.count(EventReport.id)).where(EventReport.status == ReportStatus.OPEN)) or 0


def open_reports() -> list[EventReport]:
    stmt = (
        select(EventReport)
        .where(EventReport.status == ReportStatus.OPEN)
        .order_by(EventReport.created_at, EventReport.id)
        .options(selectinload(EventReport.event))
    )
    return list(db.session.scalars(stmt))


def apply_report(report: EventReport) -> Event:
    """Write the report's proposed values to the event, like an editor's edit, and close the report."""
    event = report.event
    year = report.proposed_year if report.proposed_year is not None else event.year
    date_label = report.proposed_date_label
    if date_label is None:
        # A new year with no new date: keep the date text only if the year did not change.
        date_label = event.date_label if year == event.year else format_year(year)
    has_place = report.proposed_lat is not None and report.proposed_lon is not None
    update_event(event, EventData(
        title=event.title,
        year=year,
        date_label=date_label,
        summary=event.summary,
        lat=report.proposed_lat if has_place else event.lat,
        lon=report.proposed_lon if has_place else event.lon,
        category=event.category,
        tag_ids=[tag.id for tag in event.tags],
    ))
    report.status = ReportStatus.APPLIED
    db.session.commit()
    return event


def dismiss_report(report: EventReport) -> None:
    report.status = ReportStatus.DISMISSED
    db.session.commit()


# ----------------------------------------------------------------- tags

class TagError(Exception):
    """A user-facing problem with a tag change (empty or duplicate name, tag not empty...)."""


@dataclass
class TagRow:
    tag: Tag
    total: int  # events with the tag, any status
    approved: int  # of which approved (what visitors see)


def tag_rows() -> list[TagRow]:
    """Every tag with its event counts, the most used first (then by name)."""
    counts = {tag_id: (total, approved) for tag_id, total, approved in db.session.execute(
        select(event_tags.c.tag_id, func.count(Event.id),
               func.sum(case((Event.status == Status.APPROVED, 1), else_=0)))
        .join(Event, Event.id == event_tags.c.event_id).group_by(event_tags.c.tag_id))}
    rows = []
    for tag in db.session.scalars(select(Tag)):
        total, approved = counts.get(tag.id, (0, 0))
        rows.append(TagRow(tag, total, int(approved or 0)))
    rows.sort(key=lambda r: (-r.total, r.tag.name.lower()))
    return rows


def curated_tag_names() -> set[str]:
    """Names the tag tree, TAG_PARENTS and ``seed-tags`` know the tags by."""
    from haam.data.tags import TAGS
    return {name for name, _, _ in TAGS}


def _clean_name(name: str | None, exclude: Tag | None = None) -> str:
    name = " ".join((name or "").split())
    if not name:
        raise TagError("A tag needs a name.")
    if len(name) > 200:
        raise TagError("Tag names can have at most 200 characters.")
    other = db.session.scalar(select(Tag).where(func.lower(Tag.name) == name.lower()))
    if other is not None and other is not exclude:
        raise TagError(f"There is already a tag called “{other.name}”.")
    return name


def create_tag(name: str | None, start_year: int | None = None, end_year: int | None = None) -> Tag:
    tag = Tag(name=_clean_name(name), start_year=start_year, end_year=end_year)
    db.session.add(tag)
    db.session.commit()
    return tag


def rename_tag(tag: Tag, name: str | None) -> Tag:
    tag.name = _clean_name(name, exclude=tag)
    db.session.commit()
    return tag


def delete_empty_tag(tag: Tag) -> None:
    used = db.session.scalar(select(func.count()).select_from(event_tags).where(event_tags.c.tag_id == tag.id))
    if used:
        raise TagError(f"“{tag.name}” is still used by {used} event(s); merge it into another tag instead.")
    db.session.delete(tag)
    db.session.commit()


def merge_tags(source: Tag, target: Tag) -> int:
    """Move every event of ``source`` to ``target`` and delete ``source``; returns the events moved."""
    if source.id == target.id:
        raise TagError("Choose a different tag to merge into.")
    already = select(event_tags.c.event_id).where(event_tags.c.tag_id == target.id)
    moving = [e for e in db.session.scalars(select(event_tags.c.event_id).where(
        event_tags.c.tag_id == source.id, event_tags.c.event_id.not_in(already)))]
    if moving:
        db.session.execute(insert(event_tags), [{"event_id": e, "tag_id": target.id} for e in moving])
    db.session.execute(delete(event_tags).where(event_tags.c.tag_id == source.id))
    db.session.expire_all()
    db.session.delete(db.session.get(Tag, source.id))
    db.session.commit()
    return len(moving)
