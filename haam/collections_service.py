"""Map collections: personal maps shared through secret links, without accounts.

Creating a collection returns two links:

* the **share link** ``/collections/<view_token>`` – read-only, safe to pass around;
* the **edit link** ``/collections/<view_token>/edit/<edit_token>`` – whoever has
  it can change the collection. Only a SHA-256 hash of the edit token is stored,
  so a database leak does not give edit access.

Opening the edit link remembers edit access in the (signed) session cookie, so the
owner can keep editing from the same browser without the link. The cookie holds only
the collection id and a short proof derived from the token's hash, never the token:
it stays small, cannot be forged, and cannot be turned back into the edit link. The
edit link itself is shown once, right after creation or claiming (``remember``).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from flask import current_app, session
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from haam.events import PUBLIC_ID
from haam.extensions import db
from haam.models import (Category, Collection, CollectionEntry, CollectionReport, CollectionSuggestion, Event,
                         Status, Tag)
from haam.wikipedia import WikipediaError, get_client, title_from_url

MAX_ENTRIES = 500
MAX_PENDING_SUGGESTIONS = 50
SESSION_KEY = "collections"  # {collection id: proof} for collections this browser may edit
MAX_REMEMBERED = 40  # collections this browser can edit; the oldest is forgotten beyond this
FRESH_KEY = "fresh_edit_tokens"  # {collection id: edit token}, shown on the next manage page only
PROOF_PREFIX = "~"  # urlsafe tokens never contain it, so older cookies (a raw token) are recognised


class CollectionError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class DuplicateEntry(CollectionError):
    """The event is already in the collection."""


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


def _proof(collection: Collection) -> str:
    """A short value that only the server can compute from the stored token hash."""
    key = current_app.config["SECRET_KEY"].encode()
    digest = hmac.new(key, f"collection-edit:{collection.id}:{collection.edit_token_hash}".encode(),
                      hashlib.sha256).hexdigest()
    return PROOF_PREFIX + digest[:22]


def remember(collection: Collection, edit_token: str | None = None) -> None:
    """Let this browser edit the collection from now on.

    ``edit_token`` (when the owner just created or claimed it) is kept only until the
    manage page has shown the edit link once.
    """
    owned = dict(session.get(SESSION_KEY, {}))
    owned.pop(str(collection.id), None)  # re-adding moves it to the newest position
    owned[str(collection.id)] = _proof(collection)
    while len(owned) > MAX_REMEMBERED:  # keep the cookie far below the ~4 KB browser limit
        owned.pop(next(iter(owned)))
    session[SESSION_KEY] = owned
    session.permanent = True
    if edit_token:
        fresh = dict(session.get(FRESH_KEY, {}))
        fresh[str(collection.id)] = edit_token
        session[FRESH_KEY] = fresh


def forget(collection_id: int) -> None:
    owned = dict(session.get(SESSION_KEY, {}))
    if owned.pop(str(collection_id), None) is not None:
        session[SESSION_KEY] = owned


def can_edit(collection: Collection) -> bool:
    stored = session.get(SESSION_KEY, {}).get(str(collection.id))
    if not stored or not isinstance(stored, str):
        return False
    if stored.startswith(PROOF_PREFIX):
        return hmac.compare_digest(stored, _proof(collection))
    if check_edit_token(collection, stored):  # an older cookie holding the raw token: upgrade it
        remember(collection)
        return True
    return False


def pop_fresh_edit_token(collection: Collection) -> str | None:
    """The edit token if this browser just created or claimed the collection; it is shown once."""
    fresh = dict(session.get(FRESH_KEY, {}))
    token = fresh.pop(str(collection.id), None)
    if token is None:
        return None
    if fresh:
        session[FRESH_KEY] = fresh
    else:
        session.pop(FRESH_KEY, None)
    return token if check_edit_token(collection, token) else None


def my_collections() -> list[Collection]:
    ids = [int(i) for i in session.get(SESSION_KEY, {})]
    if not ids:
        return []
    found = db.session.scalars(
        select(Collection).options(*_LIST_LOAD).where(Collection.id.in_(ids))).all()
    return sorted((c for c in found if can_edit(c)), key=lambda c: c.updated_at, reverse=True)


def my_event_ids(collections: list[Collection]) -> dict[int, list[int]]:
    """{collection id: public ids of the main-map events in it}, in one query."""
    found: dict[int, list[int]] = {c.id: [] for c in collections}
    if found:
        rows = db.session.execute(
            select(CollectionEntry.collection_id, PUBLIC_ID)
            .join(Event, Event.id == CollectionEntry.event_id)
            .where(CollectionEntry.collection_id.in_(found)))
        for collection_id, public in rows:
            found[collection_id].append(public)
    return found


# ----------------------------------------------------------------- queries

# Entries with their events (what year_span, all_wikipedia and the badges read), so list pages
# cost a fixed number of queries instead of one per entry.
_LIST_LOAD = (selectinload(Collection.entries).joinedload(CollectionEntry.event),)


def get_by_view_token(view_token: str) -> Collection | None:
    """The collection with its entries, their events and the events' tags (3 queries in all)."""
    return db.session.scalar(
        select(Collection).where(Collection.view_token == view_token)
        .options(selectinload(Collection.entries).joinedload(CollectionEntry.event).selectinload(Event.tags)))


def public_collections(page: int = 1, per_page: int = 24) -> tuple[list[Collection], int]:
    """Public, non-hidden collections that have at least one entry, newest first."""
    has_entries = select(CollectionEntry.id).where(CollectionEntry.collection_id == Collection.id).exists()
    where = (Collection.is_public.is_(True), Collection.is_hidden.is_(False), has_entries)
    total = db.session.scalar(select(func.count(Collection.id)).where(*where))
    items = db.session.scalars(
        select(Collection).options(*_LIST_LOAD).where(*where).order_by(Collection.updated_at.desc())
        .offset((page - 1) * per_page).limit(per_page)
    ).all()
    return list(items), total


# ------------------------------------------------------------------ search

_QUERY_PART = re.compile(r'"([^"]+)"|(\S+)')
_FOLD_EXTRA = str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "đ": "d", "ł": "l", "ð": "d", "þ": "th"})
SEARCH_POOL = 1000  # newest public collections searched
SEARCH_TERMS = 8
HIT_ENTRIES = 6  # matching entries shown per collection


def fold(text: str) -> str:
    """Lower-case without accents, so 'Gödel', 'Godel' and 'goedel'-like spellings of one letter meet."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c))
    return plain.casefold().translate(_FOLD_EXTRA)


def parse_query(q: str) -> list[str]:
    """Words (or "quoted phrases") of a search, folded; every one has to be found."""
    parts = [(quoted or word) for quoted, word in _QUERY_PART.findall(q or "")]
    return [t for t in (fold(p).strip() for p in parts) if t][:SEARCH_TERMS]


@dataclass
class SearchHit:
    collection: Collection
    entries: list[CollectionEntry]  # the best matching entries (at most HIT_ENTRIES)
    more: int  # matching entries not shown
    score: int


def _entry_text(entry: CollectionEntry) -> str:
    return fold(f"{entry.title} {entry.summary} {entry.note} {entry.date_label} {entry.display_year} "
                f"{entry.year} {entry.category.label}")


def search_public(q: str = "", category: Category | None = None, year_from: int | None = None,
                  year_to: int | None = None, page: int = 1, per_page: int = 24) -> tuple[list[SearchHit], int]:
    """Search public collections *and what is inside them*.

    Every word has to appear somewhere in the collection: its title or description, or in the
    title, text, note, date or category of an entry (different words may sit in different entries).
    Category and year filters apply to entries; a collection needs at least one entry passing them.
    Results are ranked: title hits first, then collections with more, better matching entries.
    """
    terms = parse_query(q)
    filtered = category is not None or year_from is not None or year_to is not None
    pool = db.session.scalars(
        select(Collection).options(*_LIST_LOAD)
        .where(Collection.is_public.is_(True), Collection.is_hidden.is_(False))
        .order_by(Collection.updated_at.desc()).limit(SEARCH_POOL)).all()
    hits = []
    for collection in pool:
        entries = [e for e in collection.entries
                   if (category is None or e.category == category)
                   and (year_from is None or e.year >= year_from)
                   and (year_to is None or e.year <= year_to)]
        if not entries or (not terms and not filtered):
            continue
        title, description = fold(collection.title), fold(collection.description)
        found = {t for t in terms if t in title or t in description}
        score = sum(5 for t in terms if t in title) + sum(2 for t in terms if t in description)
        matched = []
        for entry in entries:
            text, name = _entry_text(entry), fold(entry.title)
            seen = {t for t in terms if t in text}
            if terms and not seen:
                continue
            found |= seen
            weight = sum(3 if t in name else 1 for t in seen)
            score += weight
            matched.append((weight, entry))
        if len(found) < len(terms):
            continue
        matched.sort(key=lambda m: (-m[0], m[1].year, m[1].id))
        shown = [e for _, e in matched[:HIT_ENTRIES]]
        hits.append(SearchHit(collection, shown, len(matched) - len(shown), score))
    hits.sort(key=lambda h: (-h.score, -h.collection.updated_at.timestamp()))
    start = (page - 1) * per_page
    return hits[start:start + per_page], len(hits)


def all_collections(page: int = 1, per_page: int = 20) -> tuple[list[Collection], int]:
    """One page of every collection (admin): reported first, then public, then most recently changed."""
    reported = select(CollectionReport.id).where(CollectionReport.collection_id == Collection.id).exists()
    total = db.session.scalar(select(func.count(Collection.id)))
    items = db.session.scalars(
        select(Collection).options(*_LIST_LOAD, selectinload(Collection.reports))
        .order_by(reported.desc(), Collection.is_public.desc(), Collection.updated_at.desc(), Collection.id)
        .offset((page - 1) * per_page).limit(per_page)).all()
    return list(items), total


def get_entry(collection: Collection, entry_id: int) -> CollectionEntry | None:
    entry = db.session.get(CollectionEntry, entry_id)
    return entry if entry is not None and entry.collection_id == collection.id else None


# ----------------------------------------------------------------- changes

def _touch(collection: Collection) -> None:
    collection.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)


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
        raise DuplicateEntry(f"“{event.title}” is already in this collection.")
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
            .order_by(Event.year, func.coalesce(Event.month * 100 + Event.day, 9999), Event.title))
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
    return add_events(collection, tag_events(tag_id, year_from, year_to))


def date_order(events: list[Event]) -> list[Event]:
    """Oldest first, by year, then by month and day (events without a day last), then title."""
    return sorted(events, key=lambda e: (e.year, e.month * 100 + e.day if e.month and e.day else 9999, e.title))


def add_events(collection: Collection, events: list[Event]) -> TagResult:
    """Add events (in the order given) that are not in the collection yet, up to ``MAX_ENTRIES`` entries."""
    result = TagResult()
    present = {entry.event_id for entry in collection.entries if entry.event_id}
    for event in events:
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
    if (entry.custom_lat, entry.custom_lon) != (data.lat, data.lon):
        entry.wiki_lat = entry.wiki_lon = None  # the reconfirmed note no longer describes this place
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


def copy_collection(source: Collection) -> tuple[Collection, str]:
    """A new, unlisted collection with the same entries, notes, custom entries and positions."""
    copy, edit_token = create_collection(f"{source.title} (copy)"[:200], source.description, False)
    for entry in source.entries:
        copy.entries.append(CollectionEntry(
            event_id=entry.event_id, position=entry.position, note=entry.note,
            custom_title=entry.custom_title, custom_year=entry.custom_year,
            custom_date_label=entry.custom_date_label, custom_summary=entry.custom_summary,
            custom_lat=entry.custom_lat, custom_lon=entry.custom_lon, custom_category=entry.custom_category,
            link=entry.link, wiki_verified=entry.wiki_verified,
            wiki_lat=entry.wiki_lat, wiki_lon=entry.wiki_lon))
    db.session.commit()
    return copy, edit_token


def suggest(collection: Collection, event_id: int | None, title: str, link: str,
            message: str) -> CollectionSuggestion:
    """Store a visitor's suggestion: a main-map event, or a free-text title with an optional link."""
    pending = db.session.scalar(select(func.count(CollectionSuggestion.id))
                                .where(CollectionSuggestion.collection_id == collection.id))
    if pending >= MAX_PENDING_SUGGESTIONS:
        raise CollectionError("This collection has too many suggestions waiting. Try again later.")
    suggestion = CollectionSuggestion(collection_id=collection.id, message=message.strip())
    if event_id:
        event = db.session.get(Event, event_id)
        if event is None or event.status != Status.APPROVED:
            raise CollectionError("Choose an event from the list.")
        if any(entry.event_id == event.id for entry in collection.entries):
            raise DuplicateEntry(f"\u201c{event.title}\u201d is already in this collection.")
        suggestion.event_id = event.id
    else:
        if not title.strip():
            raise CollectionError("Choose an event from the list or give a title.")
        suggestion.title, suggestion.link = title.strip(), link.strip() or None
    db.session.add(suggestion)
    db.session.commit()
    return suggestion


def get_suggestion(collection: Collection, suggestion_id: int) -> CollectionSuggestion | None:
    found = db.session.get(CollectionSuggestion, suggestion_id)
    return found if found is not None and found.collection_id == collection.id else None


def dismiss_suggestion(suggestion: CollectionSuggestion) -> None:
    db.session.delete(suggestion)
    db.session.commit()


def accept_suggestion(collection: Collection, suggestion: CollectionSuggestion) -> CollectionEntry | None:
    """Turn an event suggestion into an entry (its message becomes the note) and remove it.

    Returns None when the event is already in the collection (the suggestion is still removed).
    """
    try:
        entry = add_event(collection, suggestion.event_id, suggestion.message)
    except DuplicateEntry:
        entry = None
    db.session.delete(suggestion)
    db.session.commit()
    return entry


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
