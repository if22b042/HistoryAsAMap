"""Importance from Wikidata sitelinks: the column, `fetch-sitelinks`, sync and the map's chunks."""

import csv
from pathlib import Path

import pytest
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from haam import create_app, feed, importer
from haam.extensions import db
from haam.models import Event, Status
from haam.sitelinks import fetch_sitelinks
from haam.wikidata import EVENT_COLUMNS

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def quiet(_message):
    pass


class FakeWikidata:
    """Answers ``sitelinks`` from a dict; records the ids asked for (no network)."""

    def __init__(self, counts):
        self.counts = counts
        self.asked = []

    def sitelinks(self, ids, report=None):
        ids = list(ids)
        self.asked.append(ids)
        return {q: self.counts[q] for q in ids if q in self.counts}


def write_csv(path, rows, columns=EVENT_COLUMNS):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


# ------------------------------------------------------------ model, migration

def test_new_events_start_at_zero(make_event):
    assert make_event().sitelinks == 0


def test_migration_adds_and_drops_the_column(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'haam.db'}")
    app = create_app("testing")
    with app.app_context():
        upgrade(directory=str(MIGRATIONS), revision="c5d6e7f8a9b0")
        db.session.execute(text(
            "INSERT INTO haam_events (title, year, date_label, summary, wiki_url, lat, lon, category, status,"
            " modified, from_website, created_at, updated_at) VALUES ('Old', 1900, '', '', 'https://x/old', 0, 0,"
            " 'military', 'approved', 0, 0, '2026-01-01', '2026-01-01')"))
        db.session.commit()
        upgrade(directory=str(MIGRATIONS), revision="b7c8d9e0f1a2")
        assert db.session.execute(text("SELECT sitelinks FROM haam_events")).scalar() == 0  # existing rows: unknown
        downgrade(directory=str(MIGRATIONS), revision="c5d6e7f8a9b0")
        assert "sitelinks" not in {c["name"] for c in inspect(db.engine).get_columns("haam_events")}
        assert db.session.execute(text("SELECT title FROM haam_events")).scalar() == "Old"
        db.session.remove()
        db.engine.dispose()


# ------------------------------------------------------------------- buckets

@pytest.mark.parametrize("count, bucket", [
    (0, 0), (2, 0), (3, 1), (6, 2), (12, 4), (19, 5), (48, 7), (74, 8), (81, 9), (108, 9), (5000, 9), (None, 0),
])
def test_importance_bucket(count, bucket):
    assert feed.importance_bucket(count) == bucket


def test_buckets_never_go_down():
    buckets = [feed.importance_bucket(n) for n in range(200)]
    assert buckets == sorted(buckets) and buckets[-1] == 9


# ----------------------------------------------------------- fetch-sitelinks

def test_fetch_stores_counts_and_writes_the_csv(app, make_event, tmp_path):
    hastings = make_event(title="Battle of Hastings", wikidata_id="Q1")
    fire = make_event(title="A fire", wikidata_id="Q2", sitelinks=4)
    merged = make_event(title="Merged item", wikidata_id="Q3", sitelinks=7)  # Wikidata no longer has it
    own = make_event(title="No Wikidata id")
    updated_at = hastings.updated_at
    ids = hastings.id, fire.id, merged.id, own.id
    path = tmp_path / "events.csv"
    old_columns = [c for c in EVENT_COLUMNS if c != "sitelinks"]  # a file from before the column
    write_csv(path, [{"wikidata_id": "Q1", "title": "Battle of Hastings"}, {"wikidata_id": "Q9", "title": "Not in db"},
                     {"wikidata_id": "Q3", "title": "Merged item"}], columns=old_columns)
    client = FakeWikidata({"Q1": 81, "Q2": 4, "Q9": 12})

    dry = fetch_sitelinks(client, csv_path=str(path), dry_run=True, report=quiet)
    assert (dry.asked, dry.found, dry.changed, dry.csv_changed) == (4, 3, 1, 2)
    assert "sitelinks" not in read_csv(path)[0]
    db.session.expire_all()
    assert db.session.get(Event, ids[0]).sitelinks == 0

    stats = fetch_sitelinks(client, csv_path=str(path), report=quiet)
    assert sorted(client.asked[-1]) == ["Q1", "Q2", "Q3", "Q9"]  # only Wikidata ids are sent
    assert (stats.changed, stats.csv_changed) == (1, 2)
    db.session.expire_all()
    assert [db.session.get(Event, i).sitelinks for i in ids] == [81, 4, 7, 0]
    assert db.session.get(Event, ids[0]).updated_at == updated_at  # not an edit
    assert [(r["wikidata_id"], r["sitelinks"]) for r in read_csv(path)] == [("Q1", "81"), ("Q9", "12"), ("Q3", "")]

    again = fetch_sitelinks(client, csv_path=str(path), report=quiet)
    assert (again.changed, again.csv_changed) == (0, 0)


def test_fetch_limit_and_no_csv(app, make_event):
    for n in range(5):
        make_event(title=f"Event {n}", wikidata_id=f"Q{n + 1}")
    client = FakeWikidata({f"Q{n + 1}": 10 for n in range(5)})
    stats = fetch_sitelinks(client, limit=2, report=quiet)
    assert client.asked == [["Q1", "Q2"]]
    assert (stats.asked, stats.changed) == (2, 2)
    assert sorted(db.session.scalars(db.select(Event.sitelinks))) == [0, 0, 0, 10, 10]


def test_client_batches_sparql_queries(monkeypatch):
    from haam.wikidata import WikidataClient

    client = WikidataClient("test", pause=0)
    queries = []

    def fake_sparql(query, attempts=4):
        queries.append(query)
        ids = query.split("VALUES ?item {")[1].split("}")[0].split()
        return [{"item": {"value": f"http://www.wikidata.org/entity/{i[3:]}"}, "n": {"value": "3"}} for i in ids]

    monkeypatch.setattr(client, "_sparql", fake_sparql)
    counts = client.sitelinks([f"Q{n}" for n in range(1, 1001)])
    assert len(queries) == 3  # 400 per query
    assert "wikibase:sitelinks" in queries[0]
    assert len(counts) == 1000 and counts["Q1000"] == 3


def test_cli_dry_run(app, make_event, tmp_path, monkeypatch):
    from haam import wikidata

    make_event(wikidata_id="Q1")
    monkeypatch.setattr(wikidata.WikidataClient, "sitelinks", lambda self, ids, report=None: {"Q1": 81})
    result = app.test_cli_runner().invoke(args=["haam", "fetch-sitelinks", "--dry-run", "--csv", ""])
    assert result.exit_code == 0, result.output
    assert "Would change the count of 1 events" in result.output
    assert db.session.scalar(db.select(Event.sitelinks)) == 0


# ---------------------------------------------------------------------- sync

def test_sync_keeps_counts_and_sets_them_from_the_file(app, make_event, tmp_path):
    with_count = make_event(title="Battle of Hastings", wikidata_id="Q1", sitelinks=81)
    edited = make_event(title="Edited by hand", wikidata_id="Q2", sitelinks=5, modified=True)
    unknown = make_event(title="Battle of Waterloo", wikidata_id="Q3", year=1815, sitelinks=95)
    ids = with_count.id, edited.id, unknown.id
    base = {"lat": "50.9", "lon": "0.49", "category": "military", "status": "approved", "summary": "A battle."}
    path = tmp_path / "final.csv"
    write_csv(path, [
        {**base, "wikidata_id": "Q1", "url": "https://en.wikipedia.org/wiki/Battle_of_Hastings",
         "title": "Battle of Hastings", "year": "1066", "date": "14 October 1066", "sitelinks": "82"},
        {**base, "wikidata_id": "Q2", "url": "https://en.wikipedia.org/wiki/Edited_by_hand",
         "title": "Edited by hand", "year": "1066", "sitelinks": "6"},
        # No count in the file: the database keeps its own (never 0).
        {**base, "wikidata_id": "Q3", "url": "https://en.wikipedia.org/wiki/Battle_of_Waterloo",
         "title": "Battle of Waterloo", "year": "1815", "sitelinks": ""},
        {**base, "wikidata_id": "Q4", "url": "https://en.wikipedia.org/wiki/Battle_of_Stalingrad",
         "title": "Battle of Stalingrad", "year": "1942", "sitelinks": "108"},
    ])

    dry = importer.sync_wikidata(str(path), dry_run=True, report=quiet)
    assert (dry.sitelinks, dry.removed) == (2, 0)

    stats = importer.sync_wikidata(str(path), report=quiet)
    assert (stats.sitelinks, stats.removed, stats.added) == (2, 0, 1)
    db.session.expire_all()
    assert [db.session.get(Event, i).sitelinks for i in ids] == [82, 6, 95]
    assert db.session.scalar(db.select(Event.sitelinks).filter_by(wikidata_id="Q4")) == 108

    again = importer.sync_wikidata(str(path), report=quiet)
    assert (again.sitelinks, again.removed, again.added) == (0, 0, 0)


def test_sync_of_a_file_without_the_column_changes_no_count(app, make_event, tmp_path):
    event = make_event(title="Battle of Hastings", wikidata_id="Q1", sitelinks=81)
    columns = [c for c in EVENT_COLUMNS if c != "sitelinks"]
    path = tmp_path / "old.csv"
    write_csv(path, [{"wikidata_id": "Q1", "url": "https://en.wikipedia.org/wiki/Battle_of_Hastings",
                      "title": "Battle of Hastings", "year": "1066", "lat": "50.9", "lon": "0.49",
                      "category": "military", "status": "approved"}], columns=columns)
    stats = importer.sync_wikidata(str(path), report=quiet)
    assert (stats.sitelinks, stats.removed) == (0, 0)
    db.session.expire_all()
    assert db.session.get(Event, event.id).sitelinks == 81


# ---------------------------------------------------------------------- feed

def test_core_chunks_carry_the_bucket(client, make_event):
    make_event(title="Battle of Stalingrad", year=1942, sitelinks=108)
    make_event(title="A fire", year=1900, sitelinks=2)
    make_event(title="Pending", status=Status.PENDING, sitelinks=50)
    manifest = client.get("/api/events/manifest").json
    seen = {}
    for url in manifest["core"]:
        chunk = client.get(url).json
        assert len(chunk["imp"]) == chunk["count"]
        seen.update(zip(chunk["title"], chunk["imp"]))
    assert seen == {"Battle of Stalingrad": 9, "A fire": 0}
    assert feed.FORMAT >= 4


def test_bulk_sitelink_change_gives_a_new_version(app, make_event):
    app.config["FEED_STATE_TTL"] = 0
    first = make_event(title="One", wikidata_id="Q1")
    second = make_event(title="Two", wikidata_id="Q2", year=1067)
    before = feed.state()["version"]
    db.session.execute(Event.__table__.update().where(Event.id == first.id).values(sitelinks=40))
    db.session.commit()
    after = feed.state()["version"]
    assert after != before
    # The same counts moved to the other event: still a new version.
    db.session.execute(Event.__table__.update().where(Event.id == first.id).values(sitelinks=0))
    db.session.execute(Event.__table__.update().where(Event.id == second.id).values(sitelinks=40))
    db.session.commit()
    assert feed.state()["version"] not in (before, after)


def test_only_the_main_map_has_the_major_events_button(client):
    from haam import collections_service

    assert 'id="major-toggle"' in client.get("/").get_data(as_text=True)
    assert 'id="major-toggle"' in client.get("/embed").get_data(as_text=True)
    collection, _ = collections_service.create_collection("Mine", "", is_public=False)
    page = client.get(f"/collections/{collection.view_token}/map").get_data(as_text=True)
    assert 'id="heatmap-toggle"' in page and 'id="major-toggle"' not in page  # no importance data there
