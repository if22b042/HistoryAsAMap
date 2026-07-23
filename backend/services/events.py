import logging

from backend.extensions import db
from backend.models.event import Entry, Location, EventCategory, EntryStatus, Tag
from backend.services.geocoding import check_on_water, reverse_geocode
from backend.services.wikipedia import get_wikipedia_data
from backend.utils.validators import is_valid_english_wikipedia_url

logger = logging.getLogger(__name__)


class EventServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def preview_event(wiki_link: str) -> dict:
    if not is_valid_english_wikipedia_url(wiki_link):
        raise EventServiceError(
            "Invalid Wikipedia link. Only English Wikipedia URLs are allowed "
            "(https://en.wikipedia.org/wiki/...)."
        )

    existing = Entry.query.filter_by(wikiLink=wiki_link).first()
    if existing:
        raise EventServiceError(
            "An entry with this Wikipedia link already exists.", status_code=409
        )

    data = get_wikipedia_data(wiki_link)
    if not data:
        raise EventServiceError(
            "Could not retrieve data from Wikipedia. The article may not exist "
            "or may lack coordinates."
        )

    if data.get("lat") is None or data.get("lon") is None:
        raise EventServiceError(
            "This Wikipedia article has no coordinates. Please choose an article "
            "with a mapped location."
        )

    if data.get("year") is None:
        raise EventServiceError(
            "This Wikipedia article has no extractable year. Please choose an article "
            "with a clear date in the first paragraph."
        )

    return data


def create_event(payload: dict) -> Entry:
    link = payload.get("link", "").strip()
    if not is_valid_english_wikipedia_url(link):
        raise EventServiceError(
            "Invalid Wikipedia link. Only English Wikipedia URLs are allowed."
        )

    existing = Entry.query.filter_by(wikiLink=link).first()
    if existing:
        raise EventServiceError(
            "An entry with this Wikipedia link already exists.", status_code=409
        )

    category_str = payload.get("category")
    if not category_str:
        raise EventServiceError("Event category is required.")

    try:
        category = EventCategory(category_str)
    except ValueError as exc:
        raise EventServiceError(f"Invalid category: {category_str}") from exc

    try:
        lat = float(payload["lat"])
        lon = float(payload["lon"])
        year = int(payload["year"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EventServiceError("Valid lat, lon, and year are required.") from exc

    title = payload.get("title", "").strip()
    if not title:
        raise EventServiceError("Title is required.")

    date_string = payload.get("date") or ""
    first_paragraph = payload.get("first_paragraph", "").strip()
    if not first_paragraph:
        raise EventServiceError("Description is required.")

    modified = bool(payload.get("modified", False))
    country = reverse_geocode(lat, lon)
    on_water = check_on_water(lat, lon)

    entry = Entry(
        title=title,
        year=year,
        dateString=date_string,
        firstParagraph=first_paragraph,
        wikiLink=link,
        category=category,
        modified=modified,
        status=EntryStatus.PENDING,
    )
    location = Location(
        lat=lat,
        lon=lon,
        country=country,
        on_water=on_water,
        entry=entry,
    )

    # Handle tags
    tag_ids = payload.get("tag_ids", [])
    if tag_ids:
        tags = Tag.query.filter(Tag.id.in_(tag_ids)).all()
        entry.tags = tags

    db.session.add(entry)
    db.session.add(location)
    db.session.commit()

    logger.info("Created pending entry id=%s title=%s", entry.id, entry.title)
    return entry


def list_events(
    status: EntryStatus | None = EntryStatus.APPROVED,
    year_from: int | None = None,
    year_to: int | None = None,
    category: str | None = None,
) -> list[Entry]:
    query = Entry.query

    if status is not None:
        query = query.filter_by(status=status)

    if year_from is not None:
        query = query.filter(Entry.year >= year_from)
    if year_to is not None:
        query = query.filter(Entry.year <= year_to)

    if category and category != "all":
        try:
            cat = EventCategory(category)
            query = query.filter_by(category=cat)
        except ValueError:
            pass

    return query.order_by(Entry.year.asc()).all()


def get_event(event_id: int, approved_only: bool = True) -> Entry:
    entry = Entry.query.get(event_id)
    if not entry:
        raise EventServiceError("Event not found.", status_code=404)
    if approved_only and entry.status != EntryStatus.APPROVED:
        raise EventServiceError("Event not found.", status_code=404)
    return entry


def list_pending_events() -> list[Entry]:
    return (
        Entry.query.filter_by(status=EntryStatus.PENDING)
        .order_by(Entry.id.desc())
        .all()
    )


def approve_event(event_id: int) -> Entry:
    entry = Entry.query.get(event_id)
    if not entry:
        raise EventServiceError("Event not found.", status_code=404)
    if entry.status != EntryStatus.PENDING:
        raise EventServiceError(
            f"Cannot approve event with status '{entry.status.value}'.", status_code=400
        )
    entry.status = EntryStatus.APPROVED
    db.session.commit()
    return entry


def reject_event(event_id: int) -> Entry:
    entry = Entry.query.get(event_id)
    if not entry:
        raise EventServiceError("Event not found.", status_code=404)
    if entry.status != EntryStatus.PENDING:
        raise EventServiceError(
            f"Cannot reject event with status '{entry.status.value}'.", status_code=400
        )
    entry.status = EntryStatus.REJECTED
    db.session.commit()
    return entry
