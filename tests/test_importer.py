from sqlalchemy import text

from haam import importer
from haam.extensions import db
from haam.models import Category, Event, Status, Tag


def quiet(_message):
    pass


def test_seed_tags_is_idempotent(app):
    added = importer.seed_tags()
    assert added > 300
    assert importer.seed_tags() == 0
    names = db.session.scalars(db.select(Tag.name)).all()
    assert len(names) == len(set(names))


def test_import_titles(wiki):
    wiki.add("Battle of Hastings")
    wiki.add("Some Village", year=None)
    wiki.add("No Coordinates", lat=None, lon=None)
    stats = importer.import_titles(["Battle of Hastings", "Some Village", "No Coordinates", "Missing"],
                                   delay=0, report=quiet)
    assert (stats.added, stats.rejected) == (1, 3)
    event = db.session.scalar(db.select(Event))
    assert event.status == Status.PENDING
    assert event.category == Category.OTHER

    again = importer.import_titles(["Battle of Hastings"], delay=0, report=quiet)
    assert again.skipped == 1


def test_import_region_requires_wikidata_date(wiki):
    wiki.add("Battle of Hastings", dated_by_wikidata=True)
    wiki.add("Hastings Pier", dated_by_wikidata=False)
    wiki.geo_titles = ["Battle of Hastings", "Hastings Pier"]
    titles = importer.region_titles(50, 50, 0, 0, step=5, radius=1000)
    stats = importer.import_titles(titles, require_wikidata_date=True, approve=True, delay=0, report=quiet)
    assert stats.added == 1
    assert db.session.scalar(db.select(Event)).status == Status.APPROVED


def test_import_csv(wiki, tmp_path):
    wiki.add("Battle of Hastings")
    wiki.add("Battle of the Teutoburg Forest", year=None, lat=52.4, lon=8.1)
    path = tmp_path / "events.csv"
    path.write_text(
        "url,category,year,tags\n"
        "https://en.wikipedia.org/wiki/Battle_of_Hastings,military,,Norman Conquest of England\n"
        "https://en.wikipedia.org/wiki/Battle_of_the_Teutoburg_Forest,military,AD 9,\n"
        "https://de.wikipedia.org/wiki/Foo,,,\n",
        encoding="utf-8",
    )
    stats = importer.import_csv(str(path), report=quiet)
    assert (stats.added, stats.rejected) == (2, 1)
    teutoburg = db.session.scalar(db.select(Event).filter_by(title="Battle of the Teutoburg Forest"))
    assert teutoburg.year == 9
    hastings = db.session.scalar(db.select(Event).filter_by(title="Battle of Hastings"))
    assert [t.name for t in hastings.tags] == ["Norman Conquest of England"]


def test_import_legacy(app):
    db.session.execute(text(
        "CREATE TABLE entries (id INTEGER PRIMARY KEY, year INTEGER, dateString TEXT, firstParagraph TEXT,"
        " title TEXT, wikiLink TEXT, category TEXT, modified BOOLEAN, used BOOLEAN, tags JSON)"))
    db.session.execute(text(
        "CREATE TABLE locations (id INTEGER PRIMARY KEY, coordinates TEXT, country TEXT, on_water BOOLEAN,"
        " entry_id INTEGER, lat REAL, lon REAL)"))
    db.session.execute(text(
        "INSERT INTO entries VALUES"
        " (1, 1942, '23 August 1942', 'A battle.', 'Battle of Stalingrad',"
        "  'https://en.wikipedia.org/wiki/Battle_of_Stalingrad', 'MILITARY', FALSE, FALSE, '[\"World War II\"]'),"
        " (2, 1066, '', 'No location.', 'Orphan', 'https://en.wikipedia.org/wiki/Orphan', 'other', FALSE, FALSE, '[]')"))
    # The old app stored two locations for many entries, some only as a string.
    db.session.execute(text(
        "INSERT INTO locations VALUES (1, '48.7,44.5', 'Russia', FALSE, 1, NULL, NULL),"
        " (2, '0,0', NULL, FALSE, 1, 0, 0)"))
    db.session.commit()

    stats = importer.import_legacy(report=quiet)
    assert (stats.added, stats.rejected) == (1, 1)
    event = db.session.scalar(db.select(Event))
    assert (event.title, event.lat, event.lon, event.country) == ("Battle of Stalingrad", 48.7, 44.5, "Russia")
    assert event.category == Category.MILITARY
    assert event.status == Status.APPROVED
    assert [t.name for t in event.tags] == ["World War II"]

    assert importer.import_legacy(report=quiet).skipped == 1


def test_import_csv_status_and_coordinate_override(wiki, tmp_path):
    wiki.add("Treaty of Versailles", year=1919, lat=None, lon=None)
    wiki.add("Spanish Armada", year=1588)
    path = tmp_path / "events.csv"
    path.write_text(
        "url,category,status,year,lat,lon,tags\n"
        "https://en.wikipedia.org/wiki/Treaty_of_Versailles,diplomatic,approved,,48.8049,2.1204,\n"
        "https://en.wikipedia.org/wiki/Spanish_Armada,naval,rejected,,,,\n"
        "https://en.wikipedia.org/wiki/Spanish_Armada,naval,bogus,,,,\n",
        encoding="utf-8",
    )
    stats = importer.import_csv(str(path), report=quiet)
    assert (stats.added, stats.rejected) == (2, 1)
    versailles = db.session.scalar(db.select(Event).filter_by(title="Treaty of Versailles"))
    assert (versailles.status, versailles.lat, versailles.lon) == (Status.APPROVED, 48.8049, 2.1204)
    armada = db.session.scalar(db.select(Event).filter_by(title="Spanish Armada"))
    assert armada.status == Status.REJECTED


SYNC_COLUMNS = ["wikidata_id", "wiki_page_id", "url", "title", "year", "date", "lat", "lon", "country",
                "category", "status", "tags", "summary", "event_type", "date_source", "coord_source"]


def write_sync_csv(path, rows):
    import csv
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SYNC_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in SYNC_COLUMNS})


def test_sync_wikidata(app, make_event, tmp_path):
    from haam import collections_service

    ww2 = db.session.scalar(db.select(Tag).filter_by(name="World War II"))
    norman = db.session.scalar(db.select(Tag).filter_by(name="Norman Conquest of England"))
    stays = make_event(title="Battle of Hastings", wikidata_id="Q1")  # tags change
    gone = make_event(title="Battle of the Atlantic", wikidata_id="Q2", year=1940)  # not in the file
    in_collection = make_event(title="Tyrolean Rebellion", wikidata_id="Q3", year=1809)  # not in file, but used
    demo = make_event(title="Battle of Stalingrad", year=1942)  # demo row, no Wikidata id
    submitted = make_event(title="Battle of Midway", year=1942, from_website=True)
    stays.tags = [ww2]
    db.session.commit()
    collection, _ = collections_service.create_collection("Mine", "", is_public=False)
    collections_service.add_event(collection, in_collection.id, "")
    stays_id, gone_id, demo_id, submitted_id = stays.id, gone.id, demo.id, submitted.id

    path = tmp_path / "final.csv"
    base = {"lat": "50", "lon": "1", "category": "military", "status": "approved", "summary": "x"}
    write_sync_csv(path, [
        {**base, "wikidata_id": "Q1", "url": "https://en.wikipedia.org/wiki/Battle_of_Hastings",
         "title": "Battle of Hastings", "year": "1066", "tags": "Norman Conquest of England"},
        {**base, "wikidata_id": "Q4", "url": "https://en.wikipedia.org/wiki/Battle_of_Stalingrad",
         "title": "Battle of Stalingrad", "year": "1942", "tags": "World War II"},
        {**base, "wikidata_id": "Q5", "url": "https://en.wikipedia.org/wiki/Siege_of_Trondheim",
         "title": "Siege of Trondheim", "year": "1658", "status": "pending"},
    ])

    dry = importer.sync_wikidata(str(path), dry_run=True, report=quiet)
    assert (dry.added, dry.removed, dry.adopted) == (1, 1, 1)
    assert db.session.get(Event, gone_id) is not None

    stats = importer.sync_wikidata(str(path), report=quiet)
    assert (stats.added, stats.removed, stats.adopted, stats.retagged) == (1, 1, 1, 2)
    assert stats.kept_in_collections == ["Tyrolean Rebellion"]
    db.session.expire_all()
    assert db.session.get(Event, gone_id) is None
    assert [t.name for t in db.session.get(Event, stays_id).tags] == ["Norman Conquest of England"]
    adopted = db.session.get(Event, demo_id)
    assert (adopted.wikidata_id, [t.name for t in adopted.tags]) == ("Q4", ["World War II"])
    trondheim = db.session.scalar(db.select(Event).filter_by(wikidata_id="Q5"))
    assert (trondheim.year, trondheim.status) == (1658, Status.PENDING)
    assert db.session.get(Event, submitted_id) is not None
    assert norman  # used above via the file

    again = importer.sync_wikidata(str(path), report=quiet)
    assert (again.added, again.removed, again.retagged, again.adopted) == (0, 0, 0, 0)


def test_sync_wikidata_updates_changed_fields_of_unedited_events(app, make_event, tmp_path):
    changed = make_event(title="Old title", wikidata_id="Q10", year=1000, date_label="1000", summary="old",
                         lat=1.0, lon=2.0, country="Nowhere")
    edited = make_event(title="Edited by hand", wikidata_id="Q11", year=1100, modified=True)
    website = make_event(title="Site event", wikidata_id="Q12", year=1200, from_website=True)
    make_event(title="Same", wikidata_id="Q13", year=1300, date_label="1300", summary="same", lat=5.0, lon=6.0)
    changed_id, edited_id, website_id = changed.id, edited.id, website.id

    path = tmp_path / "final.csv"
    base = {"category": "military", "status": "approved"}
    write_sync_csv(path, [
        {**base, "wikidata_id": "Q10", "url": "https://en.wikipedia.org/wiki/Old_title", "title": "New title",
         "year": "1215", "date": "15 June 1215", "lat": "51.4", "lon": "-0.56", "country": "England",
         "summary": "new text"},
        {**base, "wikidata_id": "Q11", "url": "https://en.wikipedia.org/wiki/Edited_by_hand", "title": "Other",
         "year": "1111", "lat": "1", "lon": "1", "summary": "csv"},
        {**base, "wikidata_id": "Q12", "url": "https://en.wikipedia.org/wiki/Site_event", "title": "Other",
         "year": "1212", "lat": "1", "lon": "1", "summary": "csv"},
        {**base, "wikidata_id": "Q13", "url": "https://en.wikipedia.org/wiki/Same", "title": "Same",
         "year": "1300", "date": "1300", "lat": "5", "lon": "6", "summary": "same"},
    ])

    dry = importer.sync_wikidata(str(path), dry_run=True, report=quiet)
    assert dry.updated == 1
    assert db.session.get(Event, changed_id).title == "Old title"

    stats = importer.sync_wikidata(str(path), report=quiet)
    assert stats.updated == 1
    db.session.expire_all()
    event = db.session.get(Event, changed_id)
    assert (event.title, event.year, event.date_label, event.summary) == ("New title", 1215, "15 June 1215", "new text")
    assert (event.lat, event.lon, event.country) == (51.4, -0.56, "England")
    assert (event.month, event.day) == (6, 15)
    assert db.session.get(Event, edited_id).title == "Edited by hand"
    assert db.session.get(Event, website_id).title == "Site event"

    assert importer.sync_wikidata(str(path), report=quiet).updated == 0
