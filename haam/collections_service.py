"""Map collections: personal maps shared through secret links, without accounts.

Creating a collection returns two links:

* the **share link** ``/collections/<view_token>`` – read-only, safe to pass around;
* the **edit link** ``/collections/<view_token>/edit/<edit_token>`` – whoever has
  it can change the collection. Only a SHA-256 hash of the edit token is stored,
  so a database leak does not give edit access.

Opening the edit link remembers it in the (signed) session cookie, so the owner
can keep editing from the same browser without the link.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from flask import session
from sqlalchemy import func, select

from haam.extensions import db
from haam.models import Category, Collection, CollectionEntry, CollectionReport, Event, Status, Tag
from haam.wikipedia import WikipediaError, get_client, title_from_url

MAX_ENTRIES = 500
SESSION_KEY = "collections"  # {collection id: edit token} for collections this browser may edit


class CollectionError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class CustomEntryData:
    title: str
    year: int
    date_label: str
    category: Category
    lat: float
    lon: float
    summary: str
    link: str
    note: str

    @classmethod
    def from_form(cls, form) -> "CustomEntryData":
        return cls(
            title=form.title.data.strip(),
            year=form.year.year,
            date_label=(form.date_label.data or "").strip(),
            category=Category(form.category.data),
            lat=form.lat.data,
            lon=form.lon.data,
            summary=(form.summary.data or "").strip(),
            link=(form.link.data or "").strip(),
            note=(form.note.data or "").strip(),
        )


# ------------------------------------------------------------------ tokens

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_edit_token(collection: Collection, token: str) -> bool:
    return hmac.compare_digest(collection.edit_token_hash, _hash(token or ""))


def remember(collection: Collection, edit_token: str) -> None:
    """Let this browser edit the collection from now on."""
    owned = dict(session.get(SESSION_KEY, {}))
    owned[str(collection.id)] = edit_token
    session[SESSION_KEY] = owned
    session.permanent = True


def forget(collection_id: int) -> None:
    owned = dict(session.get(SESSION_KEY, {}))
    if owned.pop(str(collection_id), None) is not None:
        session[SESSION_KEY] = owned


def can_edit(collection: Collection) -> bool:
    token = session.get(SESSION_KEY, {}).get(str(collection.id))
    return bool(token) and check_edit_token(collection, token)


def edit_token_for(collection: Collection) -> str | None:
    return session.get(SESSION_KEY, {}).get(str(collection.id)) if can_edit(collection) else None


def my_collections() -> list[Collection]:
    ids = [int(i) for i in session.get(SESSION_KEY, {})]
    if not ids:
        return []
    found = db.session.scalars(select(Collection).where(Collection.id.in_(ids))).all()
    return sorted((c for c in found if can_edit(c)), key=lambda c: c.updated_at, reverse=True)


# ----------------------------------------------------------------- queries

def get_by_view_token(view_token: str) -> Collection | None:
    return db.session.scalar(select(Collection).where(Collection.view_token == view_token))


def public_collections(page: int = 1, per_page: int = 24) -> tuple[list[Collection], int]:
    """Public, non-hidden collections that have at least one entry, newest first."""
    has_entries = select(CollectionEntry.id).where(CollectionEntry.collection_id == Collection.id).exists()
    where = (Collection.is_public.is_(True), Collection.is_hidden.is_(False), has_entries)
    total = db.session.scalar(select(func.count(Collection.id)).where(*where))
    items = db.session.scalars(
        select(Collection).where(*where).order_by(Collection.updated_at.desc())
        .offset((page - 1) * per_page).limit(per_page)
    ).all()
    return list(items), total


def all_collections() -> list[Collection]:
    return list(db.session.scalars(select(Collection).order_by(Collection.updated_at.desc())))


def get_entry(collection: Collection, entry_id: int) -> CollectionEntry | None:
    entry = db.session.get(CollectionEntry, entry_id)
    return entry if entry is not None and entry.collection_id == collection.id else None


# ----------------------------------------------------------------- changes

def _touch(collection: Collection) -> None:
    collection.updated_at = datetime.now(timezone.utc)


def create_collection(title: str, description: str, is_public: bool) -> tuple[Collection, str]:
    """Returns the collection and its edit token (shown once, never stored in clear)."""
    edit_token = secrets.token_urlsafe(24)
    collection = Collection(
        view_token=secrets.token_urlsafe(12),
        edit_token_hash=_hash(edit_token),
        title=title.strip(),
        description=description.strip(),
        is_public=is_public,
    )
    db.session.add(collection)
    db.session.commit()
    return collection, edit_token


def update_settings(collection: Collection, title: str, description: str, is_public: bool) -> None:
    collection.title = title.strip()
    collection.description = description.strip()
    collection.is_public = is_public
    db.session.commit()


def _ensure_room(collection: Collection) -> None:
    if len(collection.entries) >= MAX_ENTRIES:
        raise CollectionError(f"A collection can hold at most {MAX_ENTRIES} entries.")


def _verify_link(link: str) -> tuple[str | None, bool]:
    """Return ``(link to store, is it an existing English Wikipedia article?)``."""
    if not link:
        return None, False
    title = title_from_url(link)
    if title is None:
        return link, False
    try:
        article = get_client().fetch_article(title)
    except WikipediaError:
        return link, False  # can't check right now: keep the link, no star
    if article is None:
        return link, False
    return article.url, True


def add_event(collection: Collection, event_id: int, note: str) -> CollectionEntry:
    event = db.session.get(Event, event_id)
    if event is None or event.status != Status.APPROVED:
        raise CollectionError("Only events that are on the main map can be added.")
    if any(entry.event_id == event.id for entry in collection.entries):
        raise CollectionError(f"“{event.title}” is already in this collection.")
    _ensure_room(collection)
    entry = CollectionEntry(event=event, note=note.strip(), position=len(collection.entries))
    collection.entries.append(entry)
    _touch(collection)
    db.session.commit()
    return entry


@dataclass
class TagResult:
    added: int = 0
    already: int = 0  # already in the collection
    no_room: int = 0  # did not fit (MAX_ENTRIES)


def tag_events(tag_id: int, year_from: int | None = None, year_to: int | None = None) -> list[Event]:
    """Approved events with a tag, oldest first, optionally within some years."""
    stmt = (select(Event).join(Event.tags).where(Tag.id == tag_id, Event.status == Status.APPROVED)
            .order_by(Event.year, Event.title))
    if year_from is not None:
        stmt = stmt.where(Event.year >= year_from)
    if year_to is not None:
        stmt = stmt.where(Event.year <= year_to)
    return list(db.session.scalars(stmt))


def add_tag_events(collection: Collection, tag_id: int, year_from: int | None = None,
                   year_to: int | None = None) -> TagResult:
    """Add every approved event with a tag (oldest first) that is not in the collection yet."""
    if db.session.get(Tag, tag_id) is None:
        raise CollectionError("Choose a tag from the list.")
    result = TagResult()
    present = {entry.event_id for entry in collection.entries if entry.event_id}
    for event in tag_events(tag_id, year_from, year_to):
        if event.id in present:
            result.already += 1
        elif len(collection.entries) >= MAX_ENTRIES:
            result.no_room += 1
        else:
            collection.entries.append(CollectionEntry(event=event, note="", position=len(collection.entries)))
            present.add(event.id)
            result.added += 1
    if result.added:
        _touch(collection)
    db.session.commit()
    return result


def move_entry(entry: CollectionEntry, lat: float | None, lon: float | None) -> None:
    """Show a main-map event at other coordinates in this collection; ``None`` = its own place."""
    if not entry.is_event:
        raise CollectionError("Change a custom entry's place in its own form.")
    if lat is None or lon is None:
        entry.custom_lat = entry.custom_lon = None
    else:
        entry.custom_lat, entry.custom_lon = lat, lon
    _touch(entry.collection)
    db.session.commit()


def add_custom(collection: Collection, data: CustomEntryData) -> CollectionEntry:
    _ensure_room(collection)
    entry = CollectionEntry(position=len(collection.entries))
    _apply_custom(entry, data)
    collection.entries.append(entry)
    _touch(collection)
    db.session.commit()
    return entry


def _apply_custom(entry: CollectionEntry, data: CustomEntryData) -> None:
    entry.custom_title = data.title
    entry.custom_year = data.year
    entry.custom_date_label = data.date_label
    entry.custom_category = data.category
    entry.custom_lat, entry.custom_lon = data.lat, data.lon
    entry.custom_summary = data.summary
    entry.note = data.note
    if data.link != (entry.link or ""):  # only re-check Wikipedia when the link changed
        entry.link, entry.wiki_verified = _verify_link(data.link)


def update_custom(entry: CollectionEntry, data: CustomEntryData) -> None:
    if entry.is_event:
        raise CollectionError("Events from the main map can only get a note.")
    _apply_custom(entry, data)
    _touch(entry.collection)
    db.session.commit()


def update_note(entry: CollectionEntry, note: str) -> None:
    entry.note = note.strip()
    _touch(entry.collection)
    db.session.commit()


def _renumber(collection: Collection) -> None:
    for position, entry in enumerate(collection.entries):
        entry.position = position


def remove_entry(entry: CollectionEntry) -> None:
    remove_entries(entry.collection, [entry.id])


def remove_entries(collection: Collection, entry_ids) -> int:
    """Remove the given entries of this collection (other ids are ignored); returns how many."""
    wanted = set(entry_ids)
    removed = [entry for entry in collection.entries if entry.id in wanted]
    if not removed:
        return 0
    for entry in removed:
        collection.entries.remove(entry)
    _renumber(collection)
    _touch(collection)
    db.session.commit()
    return len(removed)


def reorder_entries(collection: Collection, entry_ids: list[int]) -> None:
    """Put the entries in the given order; ``entry_ids`` must list every entry exactly once."""
    by_id = {entry.id: entry for entry in collection.entries}
    if len(entry_ids) != len(by_id) or set(entry_ids) != set(by_id):
        raise CollectionError("The list of entries changed meanwhile – reload the page and try again.")
    collection.entries[:] = [by_id[i] for i in entry_ids]
    _renumber(collection)
    _touch(collection)
    db.session.commit()


def move_entry_by(entry: CollectionEntry, step: int) -> bool:
    """Move an entry ``step`` places up (negative) or down; False if it is already at that end."""
    entries = entry.collection.entries
    index = entries.index(entry)
    target = index + step
    if step == 0 or not 0 <= target < len(entries):
        return False
    entries.insert(target, entries.pop(index))
    _renumber(entry.collection)
    _touch(entry.collection)
    db.session.commit()
    return True


def delete_collection(collection: Collection) -> None:
    db.session.delete(collection)
    db.session.commit()


def report(collection: Collection, reason: str) -> None:
    collection.reports.append(CollectionReport(reason=reason.strip()))
    db.session.commit()


def set_hidden(collection: Collection, hidden: bool) -> None:
    collection.is_hidden = hidden
    if not hidden:
        collection.reports.clear()  # reviewed: start counting again
    db.session.commit()
