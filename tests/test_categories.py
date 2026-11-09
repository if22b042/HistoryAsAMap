"""Categories from Wikidata classes: natural vs human-made disasters."""

import csv
import importlib.util
from pathlib import Path

import pytest
from flask_migrate import downgrade, upgrade
from sqlalchemy import text

from haam import create_app
from haam.data.event_types import CATEGORY_CLASSES, EVENT_TYPES
from haam.extensions import db
from haam.models import Category
from haam.recategorize import recategorize
from haam.wikidata import category_classes, refine_category

# Real Wikidata ids; each group's "subclasses" are kept tiny here.
EARTHQUAKE, ERUPTION, WILDFIRE, CONFLAGRATION = "Q7944", "Q7692360", "Q169950", "Q168983"
STRUCTURE_FIRE, CITY_FIRE, GAS_EXPLOSION, MINING_ACCIDENT = "Q7625093", "Q838718", "Q1362483", "Q1550225"
MASSACRE, MASS_SHOOTING, ASSASSINATION, COUP, REBELLION = "Q3199915", "Q21480300", "Q3882219", "Q45382", "Q124734"
ARSON, LIGHTNING_STRIKE, BATTLE, NATURAL_DISASTER = "Q327541", "Q15120872", "Q178561", "Q8065"
NON_WATER_FLOOD = "Q113549847"

SUBCLASSES = {  # root -> the root and the subclasses these tests use
    "Q179057": {"Q179057", GAS_EXPLOSION},  # explosion
    "Q171558": {"Q171558", MINING_ACCIDENT},  # accident
    "Q8068": {"Q8068", NON_WATER_FLOOD},  # flood
    "Q3199915": {MASSACRE, MASS_SHOOTING},
    NON_WATER_FLOOD: {NON_WATER_FLOOD},
}


class FakeWikidata:
    def __init__(self, statements=None):
        self._statements = statements or {}

    def subclasses(self, root):
        return SUBCLASSES.get(root, {root})

    def statements(self, ids, props=None):
        return {i: self._statements[i] for i in ids if i in self._statements}


@pytest.fixture
def classes():
    return category_classes(FakeWikidata())


def test_new_categories_exist():
    assert "disaster" in {c.value for c in Category} and "violence" not in {c.value for c in Category}
    assert dict((qid, cat) for qid, _, cat in EVENT_TYPES)["Q3199915"] == "disaster"
    assert dict((qid, cat) for qid, _, cat in EVENT_TYPES)["Q3882219"] == "other"
    assert dict((qid, cat) for qid, _, cat in EVENT_TYPES)["Q168983"] == "disaster"


@pytest.mark.parametrize("base, types, causes, expected", [
    # natural hazards stay natural
    ("natural", [EARTHQUAKE], [], "natural"),
    ("natural", [ERUPTION, NATURAL_DISASTER], [], "natural"),
    # an earthquake that set the city on fire is still an earthquake
    ("natural", [EARTHQUAKE, CITY_FIRE], [], "natural"),
    # fires, explosions and accidents are human-made disasters
    ("natural", [STRUCTURE_FIRE], [], "disaster"),
    ("natural", [CITY_FIRE, NATURAL_DISASTER], [], "disaster"),
    ("natural", [GAS_EXPLOSION], [], "disaster"),
    ("natural", [MINING_ACCIDENT], [], "disaster"),
    ("natural", [CONFLAGRATION], [], "disaster"),
    ("disaster", [CONFLAGRATION], [], "disaster"),
    # wildfires: natural unless Wikidata names a human cause
    ("natural", [WILDFIRE], [], "natural"),
    ("natural", [WILDFIRE], [LIGHTNING_STRIKE], "natural"),
    ("natural", [WILDFIRE], [ARSON], "disaster"),
    ("disaster", [WILDFIRE, CONFLAGRATION], [], "natural"),
    # a burning river of whiskey is a "non-water flood", not a natural one
    ("natural", [CONFLAGRATION, NON_WATER_FLOOD], [], "disaster"),
    # massacres, shootings and arson attacks with victims are human-made disasters too
    ("other", [MASSACRE], [], "disaster"),
    ("other", [REBELLION, MASSACRE], [], "disaster"),
    ("natural", [STRUCTURE_FIRE, MASS_SHOOTING], [], "disaster"),
    # an assassination is not a disaster
    ("other", [ASSASSINATION], [], "other"),
    # "other" items only move for massacres and the like: a coup that burned a palace stays a coup
    ("other", [COUP], [], "other"),
    ("other", [COUP, ARSON], [], "other"),
    # battles, treaties... never move
    ("military", [BATTLE, MASSACRE], [], "military"),
    ("naval", [STRUCTURE_FIRE], [], "naval"),
])
def test_refine_category(classes, base, types, causes, expected):
    assert refine_category(base, types, causes, classes) == expected


def test_category_classes_drop_exclusions(classes):
    assert NON_WATER_FLOOD not in classes["natural"]
    assert {EARTHQUAKE, "Q8068"} <= classes["natural"]
    assert set(CATEGORY_CLASSES) == set(classes)


def test_recategorize_updates_database_and_csv(app, make_event, tmp_path):
    fire = make_event(title="Great Fire of London", wikidata_id="Q1", category=Category.NATURAL, year=1666)
    quake = make_event(title="1755 Lisbon earthquake", wikidata_id="Q2", category=Category.NATURAL, year=1755)
    massacre = make_event(title="Massacre of Glencoe", wikidata_id="Q3", category=Category.OTHER, year=1692)
    battle = make_event(title="Battle of Hastings", wikidata_id="Q4", category=Category.MILITARY)
    own = make_event(title="Our village fire", wikidata_id="Q5", category=Category.NATURAL, year=1900,
                     from_website=True)
    gone = make_event(title="Merged item", wikidata_id="Q6", category=Category.OTHER, year=1900)
    client = FakeWikidata({
        "Q1": {"P31": [CITY_FIRE]}, "Q2": {"P31": [EARTHQUAKE]}, "Q3": {"P31": [MASSACRE]},
        "Q4": {"P31": [BATTLE, MASSACRE]}, "Q5": {"P31": [STRUCTURE_FIRE]},
    })
    path = tmp_path / "events.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["wikidata_id", "title", "category"])
        writer.writeheader()
        writer.writerows([{"wikidata_id": "Q1", "title": "Great Fire of London", "category": "natural"},
                          {"wikidata_id": "Q4", "title": "Battle of Hastings", "category": "military"}])

    stats = recategorize(client, csv_path=str(path), report=lambda m: None)

    assert (fire.category, quake.category, massacre.category) == (Category.DISASTER, Category.NATURAL,
                                                                  Category.DISASTER)
    assert (battle.category, own.category, gone.category) == (Category.MILITARY, Category.NATURAL,
                                                              Category.OTHER)
    assert dict(stats.moves) == {("natural", "disaster"): 1, ("other", "disaster"): 1}
    assert stats.missing == 1
    assert stats.before["natural"] == 3 and stats.after["natural"] == 2
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert [r["category"] for r in rows] == ["disaster", "military"]
    assert stats.csv_changed == 1


def test_recategorize_dry_run_changes_nothing(app, make_event):
    fire = make_event(title="Great Fire of London", wikidata_id="Q1", category=Category.NATURAL, year=1666)
    stats = recategorize(FakeWikidata({"Q1": {"P31": [CITY_FIRE]}}), dry_run=True, report=lambda m: None)
    db.session.refresh(fire)
    assert fire.category == Category.NATURAL
    assert dict(stats.moves) == {("natural", "disaster"): 1}


def test_new_categories_show_on_the_map(client, make_event):
    make_event(title="Great Fire of London", category=Category.DISASTER, year=1666)
    page = client.get("/").get_data(as_text=True)
    assert 'data-category="disaster"' in page and 'data-category="violence"' not in page
    assert client.get("/api/events").json[0]["category"] == "disaster"


# --------------------------------------------------------------- migration

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def _migration(revision="7b2f9c41d8a3"):
    path = next((MIGRATIONS / "versions").glob(f"{revision}_*.py"))
    spec = importlib.util.spec_from_file_location("categories_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_moves_listed_events_and_downgrades(tmp_path, monkeypatch):
    moves = {(old, new): ids.split() for old, new, ids in _migration().MOVES}
    fire_qid = moves[("natural", "disaster")][0]
    back_to_other = _migration("a91c3e5f7b20").BACK_TO_OTHER.split()
    massacre_qid = next(q for q in moves[("other", "violence")] if q not in back_to_other)
    assassination_qid = next(q for q in back_to_other if q in moves[("other", "violence")])
    monkeypatch.setenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'haam.db'}")
    app = create_app("testing")
    with app.app_context():
        upgrade(directory=str(MIGRATIONS), revision="c3f1d2a4b5e6")
        insert = text(
            "INSERT INTO haam_events (title, year, date_label, summary, wiki_url, wikidata_id, lat, lon,"
            " category, status, modified, from_website, created_at, updated_at) VALUES (:title, 1900, '', '',"
            " :url, :qid, 0, 0, :category, 'approved', 0, :website, '2026-01-01', '2026-01-01')")
        rows = [("fire", fire_qid, "natural", 0), ("massacre", massacre_qid, "other", 0),
                ("own", None, "natural", 0), ("edited", moves[("natural", "disaster")][1], "military", 0),
                ("website", moves[("natural", "disaster")][2], "natural", 1),
                ("assassination", assassination_qid, "other", 0)]
        for title, qid, category, website in rows:
            db.session.execute(insert, {"title": title, "url": f"https://x/{title}", "qid": qid,
                                        "category": category, "website": website})
        db.session.commit()

        def categories():
            return dict(db.session.execute(text("SELECT title, category FROM haam_events")).all())

        upgrade(directory=str(MIGRATIONS), revision="7b2f9c41d8a3")
        first = {"fire": "disaster", "massacre": "violence", "own": "natural", "edited": "military",
                 "website": "natural", "assassination": "violence"}
        assert categories() == first
        upgrade(directory=str(MIGRATIONS))
        assert categories() == dict(first, massacre="disaster", assassination="other")
        downgrade(directory=str(MIGRATIONS), revision="7b2f9c41d8a3")
        assert categories() == first
        downgrade(directory=str(MIGRATIONS), revision="d4e5f6a7b8c9")
        assert categories() == {"fire": "natural", "massacre": "other", "own": "natural",
                                "edited": "military", "website": "natural", "assassination": "other"}
        db.session.remove()
        db.engine.dispose()


def test_bulk_recategorisation_changes_the_data_version(app, make_event):
    """The map's chunk URLs are cached forever, so a category change must give new ones."""
    from haam import feed
    from haam.models import Event

    event = make_event(title="Great Fire of London", category=Category.NATURAL, year=1666)
    before = feed.state()["version"]
    # Like the migrations and `recategorize`: a bulk update that leaves updated_at alone.
    db.session.execute(Event.__table__.update().where(Event.id == event.id).values(category="disaster"))
    db.session.commit()
    assert feed.state()["version"] != before
