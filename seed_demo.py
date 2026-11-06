"""Fill the database with demo data from the CSV files in ``seed/``.

    python seed_demo.py                 # uses DATABASE_URL, or instance/haam.db
    python seed_demo.py --base-url https://your-site.vercel.app

What it loads (safe to run again – existing events and collections are skipped):

* ``seed/events.csv``             real events, looked up live on English Wikipedia.
                                  Columns: url, category, status (approved / pending /
                                  rejected), year, lat, lon, tags – all but url optional.
* ``seed/collections.csv``        map collections: public or unlisted, optionally hidden
                                  by an editor and/or reported (reasons separated by ``;``).
* ``seed/collection_entries.csv`` their entries: ``event`` rows point to an event from
                                  events.csv by its Wikipedia url, ``custom`` rows are the
                                  author's own entries (optional link, verified for the ★).

Edit links are shown once and also written to ``instance/demo-links.txt``.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from sqlalchemy import select

from haam import collections_service, create_app, importer
from haam.collections_service import CollectionError, CustomEntryData
from haam.dates import parse_year_input
from haam.events import find_existing
from haam.extensions import db
from haam.models import Category, Collection, Status
from haam.wikipedia import canonical_url, title_from_url

ROOT = Path(__file__).resolve().parent
SEED = ROOT / "seed"


def read_csv(name: str) -> list[dict]:
    with open(SEED / name, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def update_categories() -> int:
    """Give demo events that are already in the database the category events.csv now gives them.

    Only events without a Wikidata id: the others follow seed/wikidata_events.csv
    through ``sync-wikidata``, and the two files must not overrule each other.
    """
    changed = 0
    for row in read_csv("events.csv"):
        title = title_from_url(row["url"])
        event = find_existing(canonical_url(title)) if title else None
        if event is None or event.from_website or event.wikidata_id or not row.get("category"):
            continue
        category = Category(row["category"].strip().lower())
        if event.category != category:
            event.category = category
            changed += 1
    db.session.commit()
    return changed


def seed_collections(base_url: str) -> list[str]:
    entries_by_key: dict[str, list[dict]] = {}
    for row in read_csv("collection_entries.csv"):
        entries_by_key.setdefault(row["collection"], []).append(row)

    links = []
    for row in read_csv("collections.csv"):
        title = row["title"]
        if db.session.scalar(select(Collection).where(Collection.title == title)):
            print(f"  = {title} (already there)")
            continue

        collection, edit_token = collections_service.create_collection(
            title, row["description"], is_public=row["visibility"].strip().lower() == "public")
        for entry in entries_by_key.get(row["key"], []):
            _add_entry(collection, entry)
        for reason in filter(None, (r.strip() for r in row["reports"].split(";"))):
            collections_service.report(collection, reason)
        if row["hidden"].strip().lower() in ("yes", "true", "1"):
            collections_service.set_hidden(collection, True)

        share = f"{base_url}/collections/{collection.view_token}"
        edit = f"{share}/edit/{edit_token}"
        state = "public" if collection.is_public else "unlisted"
        if collection.is_hidden:
            state += ", hidden"
        if collection.reports:
            state += f", {len(collection.reports)} report(s)"
        badges = (" [all Wikipedia]" if collection.all_wikipedia else "") + \
                 (" [all confirmed]" if collection.all_confirmed else "")
        print(f"  + {title}: {len(collection.entries)} entries ({state}){badges}")
        links.append(f"{title}\n  share: {share}\n  edit:  {edit}\n")
    return links


def _add_entry(collection: Collection, row: dict) -> None:
    try:
        if row["type"] == "event":
            title = title_from_url(row["url"])
            event = find_existing(canonical_url(title)) if title else None
            if event is None:
                print(f"    ! event not found: {row['url']}")
                return
            if event.status != Status.APPROVED:
                print(f"    ! skipped {event.title}: it is {event.status.value}, not on the main map")
                return
            collections_service.add_event(collection, event.id, row["note"])
        else:
            year = parse_year_input(row["year"])
            if year is None:
                print(f"    ! skipped {row['title']}: bad year {row['year']!r}")
                return
            collections_service.add_custom(collection, CustomEntryData(
                title=row["title"], year=year, date_label=row["date"],
                category=Category(row["category"] or "other"),
                lat=float(row["lat"]), lon=float(row["lon"]),
                summary=row["description"], link=row["url"], note=row["note"]))
    except (CollectionError, ValueError) as error:
        print(f"    ! skipped {row.get('title') or row.get('url')}: {getattr(error, 'message', error)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:5000",
                        help="site address used when printing collection links")
    args = parser.parse_args()

    app = create_app()  # also creates missing tables and loads the tags
    with app.app_context():
        print(f"Database: {db.engine.url.render_as_string(hide_password=True)}")
        importer.seed_tags()

        print("\nEvents (fetched from Wikipedia, about 1–2 s each):")
        stats = importer.import_csv(str(SEED / "events.csv"), report=lambda m: print(f"  {m}"))
        print(f"  -> {stats}")
        updated = update_categories()
        if updated:
            print(f"  -> category updated for {updated} demo event(s) already in the database")

        print("\nCollections:")
        links = seed_collections(args.base_url.rstrip("/"))

    if links:
        out = ROOT / "instance" / "demo-links.txt"
        out.parent.mkdir(exist_ok=True)
        out.write_text("\n".join(links), encoding="utf-8")
        print(f"\nShare and edit links saved to {out.relative_to(ROOT)} (keep the edit links private).")


if __name__ == "__main__":
    main()
