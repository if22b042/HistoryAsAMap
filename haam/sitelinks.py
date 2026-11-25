"""Sitelink counts from Wikidata: a rough importance score per event (``flask haam fetch-sitelinks``).

An item's sitelinks are the wikis with a page on it, mostly Wikipedia language editions:
Waterloo has 95, a local fire 2. The counts are stored on ``Event.sitelinks`` and in the
``sitelinks`` column of ``seed/wikidata_events.csv``, so ``sync-wikidata`` can set them
offline (a fresh database, the production one) without asking Wikidata again.

Used only by the map's opt-in "Major events" filter for now (see ``haam.feed.importance_bucket``).
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass

from sqlalchemy import bindparam, select

from haam.extensions import db
from haam.models import Event
from haam.wikidata import Reporter


@dataclass
class SitelinkStats:
    asked: int = 0  # events with a Wikidata id that were looked up
    found: int = 0  # of those, items Wikidata returned a count for
    changed: int = 0  # database rows whose count changed
    csv_changed: int = 0  # CSV rows whose count changed


def fetch_sitelinks(client, *, csv_path: str | None = None, dry_run: bool = False, limit: int | None = None,
                    report: Reporter = print, chunk: int = 500) -> SitelinkStats:
    """Look up the sitelinks of every event with a Wikidata id; store them in the database and the CSV.

    The items are the database's events with a Wikidata id (by row id), then the CSV's rows
    the database lacks. Items Wikidata no longer returns keep their old count (never reset
    to 0). ``limit`` looks up only the first that many items, for a trial run.
    """
    stats = SitelinkStats()
    rows = db.session.execute(
        select(Event.id, Event.wikidata_id, Event.sitelinks).where(Event.wikidata_id.is_not(None)).order_by(Event.id)
    ).all()
    qids = [r.wikidata_id for r in rows]
    if csv_path:
        known = set(qids)
        qids += [q for q in _csv_qids(csv_path) if q not in known]
    if limit is not None:
        qids = qids[:limit]
    stats.asked = len(qids)
    counts = client.sitelinks(qids, report=report)
    stats.found = sum(1 for q in qids if q in counts)

    changed = [(r.id, counts[r.wikidata_id]) for r in rows
               if r.wikidata_id in counts and counts[r.wikidata_id] != r.sitelinks]
    stats.changed = len(changed)
    if not dry_run:
        # Not an edit: updated_at keeps its value (the feed fingerprints sitelinks itself).
        update = (Event.__table__.update().where(Event.id == bindparam("row_id"))
                  .values(sitelinks=bindparam("count"), updated_at=Event.updated_at))
        for start in range(0, len(changed), chunk):
            db.session.execute(update, [{"row_id": i, "count": n} for i, n in changed[start:start + chunk]])
            db.session.commit()

    if csv_path:
        stats.csv_changed = write_csv_counts(csv_path, counts, dry_run=dry_run)
    return stats


def _csv_qids(path: str) -> list[str]:
    with open(path, newline="", encoding="utf-8") as handle:
        return [q for q in ((row.get("wikidata_id") or "").strip() for row in csv.DictReader(handle)) if q]


def write_csv_counts(path: str, counts: dict[str, int], *, dry_run: bool = False) -> int:
    """Set the ``sitelinks`` column of an exported CSV (added if missing); returns the rows changed.

    Rows whose item has no count in ``counts`` keep what they had.
    """
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields, rows = list(reader.fieldnames or []), list(reader)
    if "sitelinks" not in fields:
        fields.append("sitelinks")
    changed = 0
    for row in rows:
        count = counts.get((row.get("wikidata_id") or "").strip())
        if count is not None and row.get("sitelinks") != str(count):
            row["sitelinks"] = str(count)
            changed += 1
    if not dry_run:
        temporary = f"{path}.tmp"
        with open(temporary, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    return changed
