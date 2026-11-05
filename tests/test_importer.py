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
        "  'https://en.wikipedia.org/wiki/Battle_of_Stalingrad', 'MILITARY', 0, 0, '[\"World War II\"]'),"
        " (2, 1066, '', 'No location.', 'Orphan', 'https://en.wikipedia.org/wiki/Orphan', 'other', 0, 0, '[]')"))
    # The old app stored two locations for many entries, some only as a string.
    db.session.execute(text(
        "INSERT INTO locations VALUES (1, '48.7,44.5', 'Russia', 0, 1, NULL, NULL),"
        " (2, '0,0', NULL, 0, 1, 0, 0)"))
    db.session.commit()

    stats = importer.import_legacy(report=quiet)
    assert (stats.added, stats.rejected) == (1, 1)
    event = db.session.scalar(db.select(Event))
    assert (event.title, event.lat, event.lon, event.country) == ("Battle of Stalingrad", 48.7, 44.5, "Russia")
    assert event.category == Category.MILITARY
    assert event.status == Status.APPROVED
    assert [t.name for t in event.tags] == ["World War II"]

    assert importer.import_legacy(report=quiet).skipped == 1
