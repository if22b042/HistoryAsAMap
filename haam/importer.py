"""Bulk imports, run by hand through the ``flask haam ...`` commands.

Nothing here runs automatically: the website never creates events on its own.
"""

from __future__ import annotations

import csv
import json
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from sqlalchemy import inspect, select, text

from haam.data.tags import TAGS
from haam.dates import parse_year_input
from haam.events import EventData, create_event, find_existing
from haam.extensions import db
from haam.models import Category, Event, Status, Tag
from haam.wikipedia import WikipediaError, canonical_url, get_client, title_from_url

logger = logging.getLogger(__name__)


@dataclass
class ImportStats:
    added: int = 0
    skipped: int = 0  # already in the database
    rejected: int = 0  # not usable (no coordinates, no date, not an event)
    failed: int = 0  # network or data errors

    def __str__(self) -> str:
        return f"added={self.added} skipped={self.skipped} rejected={self.rejected} failed={self.failed}"


Reporter = Callable[[str], None]


def seed_tags() -> int:
    """Insert missing tags from :mod:`haam.data.tags`; returns how many were added."""
    existing = set(db.session.scalars(select(Tag.name)))
    new = [Tag(name=n, start_year=s, end_year=e) for n, s, e in TAGS if n not in existing]
    db.session.add_all(new)
    db.session.commit()
    return len(new)


def import_titles(
    titles: Iterable[str],
    *,
    category: Category = Category.OTHER,
    approve: bool = False,
    require_wikidata_date: bool = False,
    delay: float = 1.0,
    max_new: int | None = None,
    report: Reporter = print,
) -> ImportStats:
    """Import Wikipedia articles by title.

    ``require_wikidata_date`` keeps only articles that Wikidata dates with a
    point in time or start time, which filters out towns, buildings, etc.
    """
    stats = ImportStats()
    client = get_client()
    status = Status.APPROVED if approve else Status.PENDING

    for title in titles:
        if max_new is not None and stats.added >= max_new:
            break
        if find_existing(canonical_url(title)):
            stats.skipped += 1
            continue
        try:
            article = client.fetch_article(title)
        except WikipediaError:
            stats.failed += 1
            continue
        finally:
            time.sleep(delay)  # be polite to Wikipedia

        if article is None or article.lat is None or article.lon is None or article.year is None:
            stats.rejected += 1
            continue
        if require_wikidata_date and not article.dated_by_wikidata:
            stats.rejected += 1
            continue
        if find_existing(article.url, article.page_id):
            stats.skipped += 1
            continue

        data = EventData(
            title=article.title,
            year=article.year,
            date_label=article.date_label,
            summary=article.summary or article.title,
            lat=article.lat,
            lon=article.lon,
            category=category,
        )
        create_event(article, data, status=status)
        stats.added += 1
        report(f"+ {article.title} ({article.date_label or article.year})")
    return stats


def region_titles(lat_min: float, lat_max: float, lon_min: float, lon_max: float,
                  step: float, radius: int) -> Iterable[str]:
    """Titles found by Wikipedia geosearch on a grid of points (deduplicated)."""
    client = get_client()
    seen: set[str] = set()
    lat = lat_min
    while lat <= lat_max:
        lon = lon_min
        while lon <= lon_max:
            try:
                titles = client.geosearch(lat, lon, radius=radius)
            except WikipediaError:
                titles = []
            for title in titles:
                if title not in seen:
                    seen.add(title)
                    yield title
            lon += step
        lat += step


def _optional_float(value) -> float | None:
    try:
        return float(value) if str(value or "").strip() else None
    except ValueError:
        return None


FULL_COLUMNS = {"url", "title", "year", "lat", "lon", "summary"}


def import_csv(path: str, *, approve: bool = False, report: Reporter = print) -> ImportStats:
    """Import rows with columns ``url`` and, all optional, ``category``, ``year``,
    ``tags`` (``;``-separated), ``status`` (approved/pending/rejected) and ``lat``/``lon``.

    Each row is looked up on Wikipedia. ``year`` and ``lat``/``lon`` override the
    extracted values (useful for articles without coordinates, e.g. treaties).
    Without a ``status`` column, rows are pending unless ``approve`` is set.

    Files that already contain every field (as written by ``export-wikidata``)
    are imported offline by :func:`import_full_csv` instead.
    """
    with open(path, newline="", encoding="utf-8") as handle:
        header = set(next(csv.reader(handle), []))
    if FULL_COLUMNS <= header:
        return import_full_csv(path, approve=approve, report=report)

    stats = ImportStats()
    tags_by_name = {t.name.lower(): t.id for t in db.session.scalars(select(Tag))}
    client = get_client()
    default_status = Status.APPROVED if approve else Status.PENDING
    with open(path, newline="", encoding="utf-8") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            title = title_from_url(row.get("url", ""))
            if title is None:
                report(f"line {line_no}: not an English Wikipedia link, skipped")
                stats.rejected += 1
                continue
            try:
                status = Status((row.get("status") or default_status.value).strip().lower())
            except ValueError:
                report(f"line {line_no}: unknown status {row.get('status')!r}, skipped")
                stats.rejected += 1
                continue
            if find_existing(canonical_url(title)):
                stats.skipped += 1
                continue
            try:
                article = client.fetch_article(title)
            except WikipediaError:
                stats.failed += 1
                continue
            if article is None:
                report(f"line {line_no}: article {title!r} does not exist")
                stats.rejected += 1
                continue
            lat = _optional_float(row.get("lat"))
            lon = _optional_float(row.get("lon"))
            if lat is None or lon is None:
                lat, lon = article.lat, article.lon
            if lat is None or lon is None:
                report(f"line {line_no}: {article.title} has no coordinates, add lat/lon columns")
                stats.rejected += 1
                continue
            if find_existing(article.url, article.page_id):
                stats.skipped += 1
                continue
            year = parse_year_input(row.get("year", "")) or article.year
            if year is None:
                report(f"line {line_no}: no year found, add a 'year' column")
                stats.rejected += 1
                continue
            try:
                category = Category((row.get("category") or "other").strip().lower())
            except ValueError:
                category = Category.OTHER
            tag_ids = [tags_by_name[n.strip().lower()] for n in (row.get("tags") or "").split(";")
                       if n.strip().lower() in tags_by_name]
            data = EventData(article.title, year, article.date_label, article.summary or article.title,
                             lat, lon, category, tag_ids)
            create_event(article, data, status=status)
            stats.added += 1
            report(f"+ {article.title} [{status.value}]")
    return stats


def import_full_csv(path: str, *, approve: bool = False, report: Reporter = print,
                    commit_every: int = 500) -> ImportStats:
    """Insert complete rows (url, title, year, lat, lon, summary, ...) without network access.

    Used for files written by ``flask haam export-wikidata``. Rows whose Wikipedia
    URL, page id or Wikidata id already exist are skipped; invalid rows are
    reported with their line number. Inserts are committed in batches.
    """
    stats = ImportStats()
    default_status = Status.APPROVED if approve else Status.PENDING
    tags_by_name = {t.name.lower(): t for t in db.session.scalars(select(Tag))}
    seen_urls = set(db.session.scalars(select(Event.wiki_url)))
    seen_pages = set(db.session.scalars(select(Event.wiki_page_id).where(Event.wiki_page_id.is_not(None))))
    seen_qids = set(db.session.scalars(select(Event.wikidata_id).where(Event.wikidata_id.is_not(None))))
    pending = 0

    with open(path, newline="", encoding="utf-8") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            problem, event = _event_from_row(row, default_status, tags_by_name)
            if problem:
                report(f"line {line_no}: {problem}")
                stats.rejected += 1
                continue
            if (event.wiki_url in seen_urls or (event.wiki_page_id and event.wiki_page_id in seen_pages)
                    or (event.wikidata_id and event.wikidata_id in seen_qids)):
                stats.skipped += 1
                continue
            seen_urls.add(event.wiki_url)
            if event.wiki_page_id:
                seen_pages.add(event.wiki_page_id)
            if event.wikidata_id:
                seen_qids.add(event.wikidata_id)
            db.session.add(event)
            stats.added += 1
            pending += 1
            if pending >= commit_every:
                db.session.commit()
                pending = 0
                report(f"  {stats.added} imported…")
    db.session.commit()
    return stats


def _event_from_row(row: dict, default_status: Status, tags_by_name: dict) -> tuple[str | None, Event | None]:
    title = title_from_url(row.get("url", ""))
    if title is None:
        return "not an English Wikipedia link", None
    year = parse_year_input(row.get("year", ""))
    lat, lon = _optional_float(row.get("lat")), _optional_float(row.get("lon"))
    if year is None:
        return f"bad year {row.get('year')!r}", None
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return "missing or invalid coordinates", None
    if not (row.get("title") or "").strip():
        return "missing title", None
    try:
        category = Category((row.get("category") or "other").strip().lower())
        status = Status((row.get("status") or default_status.value).strip().lower())
    except ValueError as exc:
        return str(exc), None
    page_id = row.get("wiki_page_id", "").strip()
    return None, Event(
        title=row["title"].strip()[:300],
        year=year,
        date_label=(row.get("date") or "").strip()[:120],
        summary=(row.get("summary") or "").strip() or row["title"].strip(),
        wiki_url=canonical_url(title),
        wiki_page_id=int(page_id) if page_id.isdigit() else None,
        wikidata_id=(row.get("wikidata_id") or "").strip() or None,
        lat=lat,
        lon=lon,
        country=(row.get("country") or "").strip()[:100] or None,
        category=category,
        status=status,
        tags=[tags_by_name[n.strip().lower()] for n in (row.get("tags") or "").split(";")
              if n.strip().lower() in tags_by_name],
    )


# ------------------------------------------------------------------ legacy data

def import_legacy(report: Reporter = print) -> ImportStats:
    """Copy events from the old ``entries``/``locations`` tables into the new schema.

    The old tables are only read, never changed. Old entries had no moderation,
    so they are imported as approved unless they carry a status of their own.
    """
    stats = ImportStats()
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    if "entries" not in tables:
        report("No legacy 'entries' table found.")
        return stats

    entry_cols = {c["name"] for c in inspector.get_columns("entries")}
    loc_cols = {c["name"] for c in inspector.get_columns("locations")} if "locations" in tables else set()
    locations = _legacy_locations(loc_cols)
    tags_by_name = {t.name: t for t in db.session.scalars(select(Tag))}

    rows = db.session.execute(text("SELECT * FROM entries ORDER BY id")).mappings().all()
    for row in rows:
        title = title_from_url(row.get("wikiLink") or "")
        loc = locations.get(row["id"])
        year = parse_year_input(str(row.get("year") or ""))  # old rows may hold "None" or text
        if title is None or loc is None or year is None:
            report(f"skipped legacy entry {row['id']} ({row.get('title')}): missing link, location or year")
            stats.rejected += 1
            continue
        url = canonical_url(title)
        if find_existing(url):
            stats.skipped += 1
            continue
        status = Status.APPROVED
        if "status" in entry_cols and row.get("status"):
            status = Status(str(row["status"]).lower())
        try:
            category = Category(str(row.get("category") or "other").lower())
        except ValueError:
            category = Category.OTHER

        event = Event(
            title=row.get("title") or title,
            year=year,
            date_label=(row.get("dateString") or "")[:120],
            summary=row.get("firstParagraph") or "",
            wiki_url=url,
            lat=loc[0],
            lon=loc[1],
            country=loc[2],
            category=category,
            status=status,
            modified=bool(row.get("modified")),
            tags=[tags_by_name[n] for n in _legacy_tag_names(row.get("tags")) if n in tags_by_name],
        )
        db.session.add(event)
        stats.added += 1
    db.session.commit()
    return stats


def _legacy_locations(columns: set[str]) -> dict[int, tuple[float, float, str | None]]:
    """First location per legacy entry (the old app sometimes stored two)."""
    if not columns:
        return {}
    result: dict[int, tuple[float, float, str | None]] = {}
    for row in db.session.execute(text("SELECT * FROM locations ORDER BY id")).mappings():
        if row["entry_id"] in result:
            continue
        lat, lon = row.get("lat"), row.get("lon")
        if (lat is None or lon is None) and row.get("coordinates"):
            try:
                lat, lon = (float(part) for part in row["coordinates"].split(",")[:2])
            except ValueError:
                continue
        if lat is not None and lon is not None:
            result[row["entry_id"]] = (float(lat), float(lon), row.get("country"))
    return result


def _legacy_tag_names(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return [str(v) for v in value] if isinstance(value, list) else []


# ---------------------------------------------------------- sync with the CSV

@dataclass
class SyncStats:
    added: int = 0
    removed: int = 0
    retagged: int = 0
    unchanged: int = 0
    adopted: int = 0  # older rows of the same article that now carry the Wikidata id
    rejected: int = 0  # invalid rows in the file
    kept_in_collections: list[str] = field(default_factory=list)  # titles


def sync_wikidata(path: str, *, dry_run: bool = False, report: Reporter = print,
                  chunk: int = 500) -> SyncStats:
    """Make the imported Wikidata events match an exported CSV (no network access).

    * rows not in the database are added (with the file's status and tags);
    * imported events (with a Wikidata id, not submitted on the website) that are
      no longer in the file are deleted – unless a collection uses them;
    * every imported event in the file gets exactly the file's tags;
    * an event for the same article that was added without a Wikidata id (the
      demo data) is adopted: it gets the id and is then treated like the others.

    Website submissions are never changed. Safe to re-run: a second run changes nothing.
    """
    from haam.models import CollectionEntry, event_tags  # local: avoids a wider import cycle

    stats = SyncStats()
    tags_by_name = {t.name.lower(): t for t in db.session.scalars(select(Tag))}
    rows: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            qid = (row.get("wikidata_id") or "").strip()
            if not qid:
                report(f"line {line_no}: no wikidata_id, skipped")
                stats.rejected += 1
                continue
            rows[qid] = row

    imported = {qid: event_id for event_id, qid in db.session.execute(
        select(Event.id, Event.wikidata_id).where(Event.wikidata_id.is_not(None), Event.from_website.is_(False)))}
    taken_qids = set(db.session.scalars(select(Event.wikidata_id).where(Event.wikidata_id.is_not(None))))
    without_qid = {url: event_id for event_id, url in db.session.execute(
        select(Event.id, Event.wiki_url).where(Event.wikidata_id.is_(None), Event.from_website.is_(False)))}
    taken_urls = set(db.session.scalars(select(Event.wiki_url)))

    # 1. adopt older rows of the same article (the demo events)
    adopt = {}
    for qid, row in rows.items():
        if qid in taken_qids:
            continue
        title = title_from_url(row.get("url", ""))
        url = canonical_url(title) if title else None
        if url in without_qid:
            adopt[qid] = without_qid[url]
    stats.adopted = len(adopt)
    if not dry_run:
        for qid, event_id in adopt.items():
            db.session.execute(Event.__table__.update().where(Event.id == event_id).values(wikidata_id=qid))
        db.session.commit()
    imported.update(adopt)

    # 2. remove imported events that are no longer in the file
    gone = {qid: event_id for qid, event_id in imported.items() if qid not in rows}
    used = set()
    ids = list(gone.values())
    for start in range(0, len(ids), chunk):
        used |= set(db.session.scalars(
            select(CollectionEntry.event_id).where(CollectionEntry.event_id.in_(ids[start:start + chunk]))))
    if used:
        stats.kept_in_collections = sorted(db.session.scalars(select(Event.title).where(Event.id.in_(used))))
    doomed = [event_id for event_id in ids if event_id not in used]
    stats.removed = len(doomed)
    if not dry_run:
        for start in range(0, len(doomed), chunk):
            part = doomed[start:start + chunk]
            # Tag links first: SQLite does not enforce ON DELETE CASCADE by default.
            db.session.execute(event_tags.delete().where(event_tags.c.event_id.in_(part)))
            db.session.execute(Event.__table__.delete().where(Event.id.in_(part)))
            db.session.commit()
        if doomed:
            report(f"  removed {len(doomed)} events that are no longer in the file")

    # 3. set the tags of the imported events that stay
    links: dict[int, set[int]] = {}
    for event_id, tag_id in db.session.execute(select(event_tags.c.event_id, event_tags.c.tag_id)):
        links.setdefault(event_id, set()).add(tag_id)
    add_links, drop_links = [], []
    for qid, event_id in imported.items():
        if qid not in rows:
            continue
        target = {tags_by_name[n.strip().lower()].id for n in (rows[qid].get("tags") or "").split(";")
                  if n.strip().lower() in tags_by_name}
        have = links.get(event_id, set())
        if target == have:
            stats.unchanged += 1
            continue
        stats.retagged += 1
        add_links += [{"event_id": event_id, "tag_id": t} for t in target - have]
        drop_links += [(event_id, t) for t in have - target]
    if not dry_run:
        for start in range(0, len(drop_links), chunk):
            part = drop_links[start:start + chunk]
            db.session.execute(event_tags.delete().where(db.or_(*(
                (event_tags.c.event_id == e) & (event_tags.c.tag_id == t) for e, t in part))))
            db.session.commit()
        for start in range(0, len(add_links), 1000):
            db.session.execute(event_tags.insert(), add_links[start:start + 1000])
            db.session.commit()

    # 4. add the rows that are not in the database yet
    pending = 0
    for qid, row in rows.items():
        if qid in imported or qid in taken_qids:
            continue
        problem, event = _event_from_row(row, Status.APPROVED, tags_by_name)
        if problem:
            report(f"{qid}: {problem}, skipped")
            stats.rejected += 1
            continue
        if event.wiki_url in taken_urls:  # the same article, submitted on the website
            continue
        taken_urls.add(event.wiki_url)
        stats.added += 1
        if dry_run:
            continue
        db.session.add(event)
        pending += 1
        if pending >= chunk:
            db.session.commit()
            pending = 0
            report(f"  {stats.added} added…")
    if not dry_run:
        db.session.commit()
    return stats
