import csv
import gzip
import json
from datetime import date

import pytest

from haam import importer
from haam.data.event_types import EVENT_TYPES
from haam.extensions import db
from haam.models import Category, Event, Status
from haam.wikidata import Candidate, export, validate

BATTLE, TREATY = "Q178561", "Q131569"
TODAY = date(2026, 11, 6)


def claim(value, rank="normal", kind="value"):
    return {"rank": rank, "mainsnak": {"snaktype": kind, "datavalue": {"value": value}}}


def item(qid):
    return {"id": qid}


def time(value, precision=11):
    return {"time": value, "precision": precision}


def coord(lat, lon, globe="http://www.wikidata.org/entity/Q2"):
    return {"latitude": lat, "longitude": lon, "globe": globe}


def battle(**claims):
    base = {"P31": [claim(item(BATTLE))], "P585": [claim(time("+1066-10-14T00:00:00Z"))],
            "P625": [claim(coord(50.91, 0.49))]}
    base.update(claims)
    return Candidate("Q1", BATTLE, "Battle of Hastings", base)


# ------------------------------------------------------------- validation

def test_valid_event():
    verdict = validate(battle(), today=TODAY)
    assert verdict.ok
    assert (verdict.year, verdict.date_label, verdict.lat, verdict.lon) == (1066, "14 October 1066", 50.91, 0.49)
    assert (verdict.date_source, verdict.coord_source) == ("P585", "P625")


def test_needs_english_article():
    candidate = battle()
    candidate.title = None
    assert validate(candidate, today=TODAY).reason == "no English Wikipedia article"


def test_type_must_be_accepted():
    candidate = battle()
    candidate.event_type = "Q5"
    assert "not an accepted event type" in validate(candidate, today=TODAY).reason


@pytest.mark.parametrize("blocked, label", [("Q5", "human"), ("Q486972", "human settlement"),
                                            ("Q4895508", "battlefield"), ("Q15275719", "recurring event")])
def test_items_also_typed_as_non_events_are_rejected(blocked, label):
    candidate = battle(P31=[claim(item(BATTLE)), claim(item(blocked))])
    assert validate(candidate, today=TODAY).reason == f"also an instance of: {label}"


def test_fictional_subclasses_are_rejected():
    candidate = battle(P31=[claim(item("Q15707521"))])  # fictional battle
    verdict = validate(candidate, today=TODAY, blocked_types={"Q15707521": "fictional entity"})
    assert verdict.reason == "also an instance of: fictional entity"


def test_date_rules():
    assert validate(battle(P585=[]), today=TODAY).reason == "no usable date (P585/P580)"
    vague = battle(P585=[claim(time("+1000-00-00T00:00:00Z", precision=7))])
    assert validate(vague, today=TODAY).reason == "date less precise than a year"
    future = battle(P585=[claim(time("+2030-01-01T00:00:00Z"))])
    assert validate(future, today=TODAY).reason == "date in the future (2030)"
    deprecated = battle(P585=[claim(time("+1065-01-01T00:00:00Z"), rank="deprecated"),
                              claim(time("+1066-10-14T00:00:00Z"))])
    assert validate(deprecated, today=TODAY).year == 1066


def test_start_time_and_bc_dates():
    candidate = battle(P585=[], P580=[claim(time("-0480-08-11T00:00:00Z"))])
    verdict = validate(candidate, today=TODAY)
    assert (verdict.year, verdict.date_label, verdict.date_source) == (-480, "11 August 480 BC", "P580")


def test_preferred_rank_wins():
    candidate = battle(P585=[claim(time("+1065-01-01T00:00:00Z")), claim(time("+1066-10-14T00:00:00Z"), "preferred")])
    assert validate(candidate, today=TODAY).year == 1066


def test_coordinates_from_location_and_other_planets():
    treaty = Candidate("Q2", TREATY, "Treaty of Versailles", {
        "P31": [claim(item(TREATY))], "P585": [claim(time("+1919-06-28T00:00:00Z"))],
        "P276": [claim(item("Q99"))]}, location_coords={"Q99": (48.8049, 2.1204)})
    verdict = validate(treaty, today=TODAY)
    assert (verdict.ok, verdict.lat, verdict.coord_source) == (True, 48.8049, "P276:Q99")

    moon = battle(P625=[claim(coord(0.67, 23.47, globe="http://www.wikidata.org/entity/Q405"))])
    assert validate(moon, today=TODAY).reason.startswith("no coordinates")


def test_event_types_are_unique():
    ids = [qid for qid, _, _ in EVENT_TYPES]
    assert len(ids) == len(set(ids))
    assert {category for _, _, category in EVENT_TYPES} <= {c.value for c in Category}


# ----------------------------------------------------------------- export

class FakeWikidata:
    def __init__(self, found, entities, locations=None, labels=None):
        self.found, self._entities = found, entities
        self.locations, self._labels = locations or {}, labels or {}

    def subclasses(self, root):
        return {"Q15707521"}

    def discover(self, type_qid):
        return self.found.get(type_qid, [])

    def entities(self, ids, props="claims"):
        return {i: self._entities[i] for i in ids if i in self._entities}

    def coordinates(self, ids):
        return {i: self.locations[i] for i in ids if i in self.locations}

    def labels(self, ids):
        return {i: self._labels.get(i, "") for i in ids}

    def introductions(self, titles):
        qids = {"Battle of Trafalgar": "Q10", "Battle of Hastings": "Q11", "Redirected": "Q999"}
        return {t: (1000 + n, t if t != "Redirected" else "Domenico Tintoretto", f"The {t} was an event.",
                    qids.get(t)) for n, t in enumerate(titles) if t != "Gone"}


def test_export_writes_accepted_and_rejected(tmp_path):
    good = battle().claims | {"P17": [claim(item("Q145"))], "P361": [claim(item("Q8"))]}
    naval = dict(good, P31=[claim(item("Q1261499"))])
    client = FakeWikidata(
        found={"Q1261499": [("Q10", "Battle of Trafalgar")],
               BATTLE: [("Q10", "Battle of Trafalgar"), ("Q11", "Battle of Hastings"),
                        ("Q12", "Hastings Pier"), ("Q13", "Gone"), ("Q14", "Redirected")]},
        entities={"Q10": {"claims": naval}, "Q11": {"claims": good},
                  "Q12": {"claims": {**good, "P31": [claim(item("Q41176"))]}}, "Q13": {"claims": good},
                  "Q14": {"claims": good}},
        labels={"Q145": "United Kingdom", "Q8": "Napoleonic Wars"},
    )
    events_path, rejected_path = tmp_path / "events.csv", tmp_path / "rejected.csv"
    stats = export(client, str(events_path), str(rejected_path), tag_names=["Napoleonic Wars"], report=lambda m: None)

    rows = list(csv.DictReader(events_path.open(encoding="utf-8")))
    assert [r["title"] for r in rows] == ["Battle of Trafalgar", "Battle of Hastings"]
    trafalgar = rows[0]
    assert (trafalgar["category"], trafalgar["event_type"]) == ("naval", "naval battle")  # first type wins
    assert (trafalgar["country"], trafalgar["tags"], trafalgar["status"]) == ("United Kingdom", "Napoleonic Wars", "approved")
    assert trafalgar["url"] == "https://en.wikipedia.org/wiki/Battle_of_Trafalgar"

    rejected = {r["title"]: r["reason"] for r in csv.DictReader(rejected_path.open(encoding="utf-8"))}
    assert rejected == {"Hastings Pier": "also an instance of: building", "Gone": "Wikipedia article not found",
                        "Redirected": "Wikipedia link leads to another topic: Domenico Tintoretto (Q999)"}
    assert (stats.candidates, stats.accepted, stats.rejected) == (5, 2, 3)


# ----------------------------------------------------------------- import

def write_full_csv(path, rows):
    columns = ["wikidata_id", "wiki_page_id", "url", "title", "year", "date", "lat", "lon", "country",
               "category", "status", "tags", "summary", "event_type", "date_source", "coord_source"]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})


def full_row(**overrides):
    row = {"wikidata_id": "Q11", "wiki_page_id": "1000", "url": "https://en.wikipedia.org/wiki/Battle_of_Hastings",
           "title": "Battle of Hastings", "year": "1066", "date": "14 October 1066", "lat": "50.91", "lon": "0.49",
           "country": "United Kingdom", "category": "military", "status": "approved",
           "tags": "Norman Conquest of England", "summary": "A battle."}
    row.update(overrides)
    return row


def test_full_csv_imports_offline(app, wiki, tmp_path):
    path = tmp_path / "events.csv"
    write_full_csv(path, [
        full_row(),
        full_row(wikidata_id="Q12", wiki_page_id="1001", url="https://en.wikipedia.org/wiki/Battle_of_Marathon",
                 title="Battle of Marathon", year="-490", status="pending", tags=""),
        full_row(wikidata_id="Q11"),                                 # duplicate Wikidata id
        full_row(wikidata_id="Q13", wiki_page_id="1000", url="https://en.wikipedia.org/wiki/Hastings_battle"),  # same page
        full_row(wikidata_id="Q14", wiki_page_id="", url="https://en.wikipedia.org/wiki/X", lat="200"),
        full_row(wikidata_id="Q15", wiki_page_id="", url="https://en.wikipedia.org/wiki/Y", year="soon"),
    ])
    stats = importer.import_csv(str(path), report=lambda m: None)  # detects the full format
    assert (stats.added, stats.skipped, stats.rejected) == (2, 2, 2)
    assert wiki.articles == {}  # no Wikipedia lookups happened

    hastings = db.session.scalar(db.select(Event).filter_by(wikidata_id="Q11"))
    assert (hastings.year, hastings.country, hastings.status, hastings.wiki_page_id) == (1066, "United Kingdom", Status.APPROVED, 1000)
    assert [t.name for t in hastings.tags] == ["Norman Conquest of England"]
    marathon = db.session.scalar(db.select(Event).filter_by(wikidata_id="Q12"))
    assert (marathon.year, marathon.status) == (-490, Status.PENDING)

    again = importer.import_csv(str(path), report=lambda m: None)
    assert again.added == 0


# -------------------------------------------------------------------- API

def test_event_list_is_compact_and_details_are_separate(client, make_event):
    event = make_event(summary="word " * 100)
    pending = make_event(title="Pending", status=Status.PENDING)
    item = client.get("/api/events").json[0]
    assert "summary" not in item and len(item["excerpt"]) <= 141 and item["excerpt"].endswith("…")
    assert client.get(f"/api/events/{event.id}").json["summary"].startswith("word word")
    assert client.get(f"/api/events/{pending.id}").status_code == 404


def test_event_list_is_gzipped(client, make_event):
    for n in range(30):
        make_event(title=f"Battle {n}")
    response = client.get("/api/events", headers={"Accept-Encoding": "gzip, br"})
    assert response.headers["Content-Encoding"] == "gzip"
    assert len(json.loads(gzip.decompress(response.data))) == 30
    assert "Content-Encoding" not in client.get("/api/events").headers
