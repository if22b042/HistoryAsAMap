"""Bulk imports, run by hand through the ``flask haam ...`` commands.

Nothing here runs automatically: the website never creates events on its own.
"""

from __future__ import annotations

import csv
import json
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

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


def import_csv(path: str, *, approve: bool = False, report: Reporter = print) -> ImportStats:
    """Import rows with columns: url, category (optional), year (optional), tags (optional, ``;``-separated).

    Each row is looked up on Wikipedia; ``year`` overrides the extracted year.
    """
    stats = ImportStats()
    tags_by_name = {t.name.lower(): t.id for t in db.session.scalars(select(Tag))}
    client = get_client()
    with open(path, newline="", encoding="utf-8") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            title = title_from_url(row.get("url", ""))
            if title is None:
                report(f"line {line_no}: not an English Wikipedia link, skipped")
                stats.rejected += 1
                continue
            try:
                article = client.fetch_article(title)
            except WikipediaError:
                stats.failed += 1
                continue
            if article is None or article.lat is None or article.lon is None:
                report(f"line {line_no}: article missing or without coordinates")
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
                             article.lat, article.lon, category, tag_ids)
            create_event(article, data, status=Status.APPROVED if approve else Status.PENDING)
            stats.added += 1
            report(f"+ {article.title}")
    return stats


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
