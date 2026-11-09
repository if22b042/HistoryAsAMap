"""Re-derive the category of imported events from their Wikidata classes.

``flask haam recategorize`` applies :func:`haam.wikidata.refine_category` to
every imported event (one with a Wikidata id, not submitted on the website)
and, optionally, to the rows of an exported CSV, so a later ``sync-wikidata``
keeps the new categories. Only the broad categories that the rules refine
(natural, disaster, other) are looked at; battles, treaties etc. never move.
"""

from __future__ import annotations

import csv
import os
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import func, select

from haam.data.event_types import REFINED_CATEGORIES
from haam.extensions import db
from haam.models import Category, Event, Status
from haam.wikidata import (P_HAS_CAUSE, P_IMMEDIATE_CAUSE, P_INSTANCE_OF, WikidataClient,
                           category_classes, refine_category)

Reporter = Callable[[str], None]


@dataclass
class RecategorizeStats:
    before: dict[str, int] = field(default_factory=dict)  # approved events per category
    after: dict[str, int] = field(default_factory=dict)
    moves: Counter = field(default_factory=Counter)  # (old, new) -> number of events
    csv_changed: int = 0
    missing: int = 0  # Wikidata returned no classes (item deleted or merged): left alone


def approved_counts() -> dict[str, int]:
    rows = db.session.execute(select(Event.category, func.count()).where(Event.status == Status.APPROVED)
                              .group_by(Event.category))
    return {category.value: count for category, count in rows}


def recategorize(client: WikidataClient, *, csv_path: str | None = None, dry_run: bool = False,
                 report: Reporter = print, chunk: int = 500) -> RecategorizeStats:
    stats = RecategorizeStats(before=approved_counts())
    refined = [Category(c) for c in REFINED_CATEGORIES]
    events = db.session.execute(
        select(Event.id, Event.wikidata_id, Event.category)
        .where(Event.wikidata_id.is_not(None), Event.from_website.is_(False), Event.category.in_(refined))).all()

    rows, fields = [], None
    if csv_path:
        with open(csv_path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
    csv_ids = {r["wikidata_id"] for r in rows if r.get("wikidata_id") and r.get("category") in REFINED_CATEGORIES}

    report("Fetching the class tree…")
    classes = category_classes(client)
    ids = {e.wikidata_id for e in events} | csv_ids
    report(f"Fetching the classes of {len(ids)} items…")
    statements = client.statements(ids)

    def wanted(qid: str, current: str) -> str | None:
        claims = statements.get(qid)
        if not claims or not claims.get(P_INSTANCE_OF):
            return None
        return refine_category(current, claims[P_INSTANCE_OF],
                               claims.get(P_HAS_CAUSE, []) + claims.get(P_IMMEDIATE_CAUSE, []), classes)

    changes: dict[str, list[int]] = {}
    for event in events:
        new = wanted(event.wikidata_id, event.category.value)
        if new is None:
            stats.missing += 1
        elif new != event.category.value:
            changes.setdefault(new, []).append(event.id)
            stats.moves[(event.category.value, new)] += 1

    for row in rows:
        if row.get("wikidata_id") in csv_ids:
            new = wanted(row["wikidata_id"], row["category"])
            if new and new != row["category"]:
                row["category"] = new
                stats.csv_changed += 1

    if not dry_run:
        for category, event_ids in changes.items():
            for start in range(0, len(event_ids), chunk):
                db.session.execute(Event.__table__.update().where(Event.id.in_(event_ids[start:start + chunk]))
                                   .values(category=category))
        db.session.commit()
        if csv_path:
            temporary = f"{csv_path}.tmp"
            with open(temporary, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            os.replace(temporary, csv_path)
    stats.after = approved_counts() if not dry_run else stats.before
    return stats
