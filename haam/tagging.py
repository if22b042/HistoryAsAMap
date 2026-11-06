"""Assign curated tags (haam/data/tags.py) to events from Wikidata's "part of" chains.

An event gets every tag it is part of, directly or further up the chain:
Battle of Freeman's Farm → Battles of Saratoga → American Revolutionary War →
American Revolution gives both "American Revolutionary War" and "American
Revolution". Names are compared loosely (case, accents, dashes, apostrophes, a
leading "The") against the Wikidata labels *and* aliases of every item on the
chain. TAG_PARENTS adds broader tags Wikidata does not link, and a tag is only
given when the event's year lies within the tag's years (so the Battle of
Austerlitz, 1805, is not tagged "French Revolution" although its chain reaches it).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from haam.data.tags import TAGS

P_PART_OF = "P361"
MAX_DEPTH = 5  # Siege of Leningrad → … → World War II is four steps up
# An event may be a year *before* a tag's start (wars are often dated from their
# declaration, fighting starts earlier: 1755 battles of the Seven Years' War), but
# not after its end: hand checks found 1919 events tagged "World War I" and 1946
# events tagged "World War II" when a year after the end was allowed.
START_SLACK = 1
END_SLACK = 0

# Items whose own name still counts but whose "part of" links are not followed,
# because Wikidata links them to conflicts most historians treat as separate.
# Found by checking 660 tag assignments by hand (all examples are real ones):
NO_CLIMB = {
    # part of the Syrian Civil War and the Iraqi insurgency, while the wars in
    # Afghanistan and the Sahel are part of it: tagged 138 Afghan and Malian battles
    # "Iraq War", "Syrian Civil War" or "Arab Spring"
    "Q17507684": "War against the Islamic State",
    "Q17272643": "spillover of the Syrian Civil War",  # Iraq 2014–15 → "Syrian Civil War"
    "Q4783165": "Arab Cold War",  # Lebanese civil war, Western Sahara 1989 → "Cold War"
    "Q322607": "War of Attrition",  # Battle of Karameh 1968 → "Cold War"
    "Q75984": "Dirty War",  # Argentina 1975 → "Cold War"
    "Q13557549": "Annexation of Tibet",  # Battle of Chamdo 1950 → "Cold War"
    "Q211855": "Finnish Civil War",  # → "Russian Civil War" and "World War I"
    "Q186284": "Polish–Soviet War",  # Battle of Warsaw 1920 → "Russian Civil War"
    "Q2015687": "Armenian–Azerbaijani War (1918–1920)",  # → "World War I"
    "Q11813124": "Polish–Ukrainian conflict (1943–1947)",  # → "World War II"
    "Q944941": "Irish Rebellion of 1798",  # → "French Revolution"
}

# Single questionable links straight from the event to a tag (no chain to cut).
EXCLUDED_TAGS = {
    "Q784397": {"Vietnam War"},  # Battle of the Paracel Islands, China v South Vietnam
    "Q183286": {"Russian Civil War"},  # Battle of Cēsis, Estonian/Latvian independence wars
    "Q96363613": {"Cold War"},  # 1978 Somali coup attempt
}

# Broader tags implied by a narrower one, where Wikidata's chain does not link them.
TAG_PARENTS = {
    "American Revolutionary War": ["American Revolution"],
    "Reign of Terror": ["French Revolution"],
    "Directory": ["French Revolution"],
    "Peninsular War": ["Napoleonic Wars"],
    "Napoleonic Wars": ["Napoleonic Era"],
    "Congress of Vienna": ["Napoleonic Era"],
    "First Industrial Revolution": ["Industrial Revolution"],
}


def normalise(name: str) -> str:
    text = name.replace("'", "").replace("’", "")  # "Years’ War" = "Years War"
    text = re.sub(r"[‐-―−]", " ", text)  # dashes separate words: "Russo–Japanese"
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"^the ", "", text)


class TagMatcher:
    """Turns the names on an event's chain into tag names."""

    def __init__(self, tags: Iterable[tuple[str, int, int | None]] = TAGS,
                 parents: dict[str, list[str]] | None = None, only: Iterable[str] | None = None):
        allowed = set(only) if only is not None else None
        self.years = {name: (start, end) for name, start, end in tags if allowed is None or name in allowed}
        self.by_key = {normalise(name): name for name in self.years}
        self.parents = TAG_PARENTS if parents is None else parents

    def match(self, names: Iterable[str], year: int | None) -> list[str]:
        found = {self.by_key[key] for key in map(normalise, names) if key in self.by_key}
        todo = list(found)
        while todo:  # add implied broader tags (transitively)
            for parent in self.parents.get(todo.pop(), []):
                if parent in self.years and parent not in found:
                    found.add(parent)
                    todo.append(parent)
        return sorted(name for name in found if self._covers(name, year))

    def _covers(self, name: str, year: int | None) -> bool:
        if year is None:
            return True
        start, end = self.years[name]
        return start - START_SLACK <= year <= (end if end is not None else 10**6) + END_SLACK


class ChainResolver:
    """Names (labels and aliases) of every item an event is part of, up to MAX_DEPTH.

    Items are fetched once per level for all events together and cached, so a
    war shared by thousands of battles costs one request.
    """

    def __init__(self, client):
        self.client = client
        self.names: dict[str, set[str]] = {}
        self.parents: dict[str, list[str]] = {}

    def _fetch(self, qids: Iterable[str]) -> None:
        from haam.wikidata import item_ids  # local: haam.wikidata imports this module

        missing = sorted({q for q in qids if q not in self.parents})
        if not missing:
            return
        for qid, entity in self.client.entities(missing, props="claims|labels|aliases").items():
            label = entity.get("labels", {}).get("en", {}).get("value")
            aliases = [a.get("value") for a in entity.get("aliases", {}).get("en", [])]
            self.names[qid] = {n for n in [label, *aliases] if n}
            parents = item_ids(entity.get("claims", {}), P_PART_OF)
            self.parents[qid] = [] if qid in NO_CLIMB else parents
        for qid in missing:  # unknown or deleted items
            self.names.setdefault(qid, set())
            self.parents.setdefault(qid, [])

    def resolve(self, part_of: dict[str, list[str]]) -> dict[str, set[str]]:
        """``event id → its direct "part of" ids`` to ``event id → names on its chain``."""
        reach = {event: list(dict.fromkeys(direct)) for event, direct in part_of.items()}
        frontier = {q for direct in reach.values() for q in direct}
        for _ in range(MAX_DEPTH):
            self._fetch(frontier)
            frontier = {p for q in frontier for p in self.parents.get(q, []) if p not in self.parents}
            if not frontier:
                break
        result = {}
        for event, direct in reach.items():
            seen, level, names = set(), list(direct), set()
            for _ in range(MAX_DEPTH):
                level = [q for q in level if q not in seen]
                if not level:
                    break
                seen.update(level)
                for q in level:
                    names |= self.names.get(q, set())
                level = [p for q in level for p in self.parents.get(q, [])]
            result[event] = names
        return result


class Tagger:
    """Tags for many events at once: ``tags({qid: [part-of ids]}, {qid: year})``."""

    def __init__(self, client, tag_names: Iterable[str] | None = None):
        names = list(tag_names) if tag_names is not None else None
        self.matcher = TagMatcher(only=names if names else None)
        self.resolver = ChainResolver(client)

    def tags(self, part_of: dict[str, list[str]], years: dict[str, int | None]) -> dict[str, list[str]]:
        chains = self.resolver.resolve(part_of)
        return {qid: [tag for tag in self.matcher.match(chains.get(qid, set()), years.get(qid))
                      if tag not in EXCLUDED_TAGS.get(qid, ())]
                for qid in part_of}


# ------------------------------------------------------------- re-tagging

def tags_for_items(client, years: dict[str, int | None], tag_names: Iterable[str] | None = None,
                   report=print, chunk: int = 2000) -> dict[str, list[str]]:
    """Tags for Wikidata items (``qid → year``), reading their "part of" from Wikidata."""
    from haam.wikidata import item_ids  # local: haam.wikidata imports this module

    tagger = Tagger(client, tag_names)
    qids = sorted(years)
    result: dict[str, list[str]] = {}
    for start in range(0, len(qids), chunk):
        part = qids[start:start + chunk]
        entities = client.entities(part)
        part_of = {q: item_ids(entities.get(q, {}).get("claims", {}), P_PART_OF) for q in part}
        result.update(tagger.tags(part_of, {q: years[q] for q in part}))
        report(f"  {min(start + chunk, len(qids))}/{len(qids)} items tagged")
    return result


def retag_csv(client, path: str, tag_names: Iterable[str] | None = None, report=print) -> dict[str, int]:
    """Rewrite the ``tags`` column of an exported CSV (wikidata_id, year, tags...) in place."""
    import csv
    import os

    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    years = {r["wikidata_id"]: int(r["year"]) for r in rows if r.get("wikidata_id")}
    tags = tags_for_items(client, years, tag_names, report=report)

    stats = {"rows": len(rows), "tagged_before": 0, "tagged_after": 0, "changed": 0}
    for row in rows:
        before = row.get("tags") or ""
        after = ";".join(tags.get(row.get("wikidata_id"), before.split(";") if before else []))
        stats["tagged_before"] += bool(before)
        stats["tagged_after"] += bool(after)
        stats["changed"] += before != after
        row["tags"] = after
    temporary = f"{path}.tmp"
    with open(temporary, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)
    return stats


def retag_database(client, dry_run: bool = False, replace: bool = False, report=print) -> dict[str, int]:
    """Re-apply the tag rules to every imported event that has a Wikidata id.

    By default only missing tags are added. With ``replace`` an imported event's
    tags become exactly what the rules give, so tags the rules no longer give are
    removed too. Events submitted on the website are never changed.
    """
    from sqlalchemy import and_, select

    from haam.extensions import db
    from haam.models import Event, Tag, event_tags

    tags_by_name = {t.name: t.id for t in db.session.scalars(select(Tag))}
    events = db.session.execute(select(Event.id, Event.wikidata_id, Event.year)
                                .where(Event.wikidata_id.is_not(None), Event.from_website.is_(False))).all()
    existing: dict[int, set[int]] = {}
    for event_id, tag_id in db.session.execute(select(event_tags.c.event_id, event_tags.c.tag_id)):
        existing.setdefault(event_id, set()).add(tag_id)

    wanted = tags_for_items(client, {qid: year for _, qid, year in events}, tags_by_name, report=report)
    add, remove = [], []
    after: dict[int, set[int]] = {}
    for event_id, qid, _ in events:
        have = existing.get(event_id, set())
        target = {tags_by_name[name] for name in wanted.get(qid, [])}
        add += [{"event_id": event_id, "tag_id": t} for t in sorted(target - have)]
        if replace:
            remove += [(event_id, t) for t in sorted(have - target)]
        after[event_id] = target if replace else have | target

    stats = {
        "events": len(events),
        "tagged_before": sum(1 for e, _, _ in events if existing.get(e)),
        "tagged_after": sum(1 for e, _, _ in events if after[e]),
        "links_added": len(add),
        "links_removed": len(remove),
        "events_changed": len({link["event_id"] for link in add} | {e for e, _ in remove}),
    }
    if not dry_run:
        for start in range(0, len(remove), 500):
            part = remove[start:start + 500]
            db.session.execute(event_tags.delete().where(
                db.or_(*(and_(event_tags.c.event_id == e, event_tags.c.tag_id == t) for e, t in part))))
            db.session.commit()
        for start in range(0, len(add), 1000):
            db.session.execute(event_tags.insert(), add[start:start + 1000])
            db.session.commit()
    return stats
