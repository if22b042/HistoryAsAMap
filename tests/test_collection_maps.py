"""Collections: full map view, starting from a tag, moving entries; the natural category."""

import pytest

from haam import collections_service as service
from haam.extensions import db
from haam.models import Category, Collection, CollectionEntry, Status, Tag

from tests.test_collections import create, custom


@pytest.fixture
def napoleonic(make_event):
    """A tag with three approved events, one pending event and one untagged event."""
    tag = Tag(name="Napoleonic Wars", start_year=1803, end_year=1815)
    db.session.add(tag)
    db.session.commit()
    events = [make_event(title=title, year=year, tags=[tag]) for title, year in
              (("Battle of Austerlitz", 1805), ("Battle of Jena", 1806), ("Battle of Waterloo", 1815))]
    make_event(title="Pending battle", year=1810, status=Status.PENDING, tags=[tag])
    make_event(title="Untagged battle", year=1810)
    return tag, events


# ------------------------------------------------------- start from a tag

def test_new_collection_can_start_from_a_tag(client, napoleonic):
    tag, _ = napoleonic
    response = client.post("/collections/new", data={"title": "Napoleon", "description": "", "tag_id": tag.id})
    assert response.status_code == 302
    collection = db.session.scalar(db.select(Collection).filter_by(title="Napoleon"))
    assert [e.title for e in collection.entries] == ["Battle of Austerlitz", "Battle of Jena", "Battle of Waterloo"]


def test_new_collection_from_a_tag_within_years(client, napoleonic):
    tag, _ = napoleonic
    client.post("/collections/new", data={"title": "Early", "description": "", "tag_id": tag.id,
                                          "year_from": "1805", "year_to": "1806"})
    collection = db.session.scalar(db.select(Collection).filter_by(title="Early"))
    assert [e.title for e in collection.entries] == ["Battle of Austerlitz", "Battle of Jena"]


def test_new_collection_without_a_tag_is_empty(client, napoleonic):
    collection, _ = create(client, title="Empty")
    assert collection.entries == []


def test_bad_year_is_an_error(client, napoleonic):
    tag, _ = napoleonic
    response = client.post("/collections/new", data={"title": "X", "description": "", "tag_id": tag.id,
                                                     "year_from": "soon"})
    assert response.status_code == 400
    assert db.session.scalar(db.select(Collection).filter_by(title="X")) is None


def test_add_tag_to_an_existing_collection_skips_duplicates(client, napoleonic):
    tag, events = napoleonic
    collection, _ = create(client)
    service.add_event(collection, events[0].id, "")
    response = client.post(f"/collections/{collection.view_token}/entries/tag", data={"tag_id": tag.id})
    assert response.status_code == 302
    db.session.refresh(collection)
    assert len(collection.entries) == 3
    flashed = client.get(f"/collections/{collection.view_token}/manage").get_data(as_text=True)
    assert "Added 2 events" in flashed and "1 were already in the collection" in flashed


def test_add_tag_needs_a_tag(client, napoleonic):
    collection, _ = create(client)
    response = client.post(f"/collections/{collection.view_token}/entries/tag", data={"tag_id": 0})
    assert response.status_code == 400
    assert "Choose a tag from the list" in response.get_data(as_text=True)


def test_add_tag_respects_the_entry_limit(client, napoleonic, monkeypatch):
    tag, _ = napoleonic
    monkeypatch.setattr(service, "MAX_ENTRIES", 2)
    collection, _ = create(client)
    result = service.add_tag_events(collection, tag.id)
    assert (result.added, result.no_room) == (2, 1)


def test_only_editors_can_add_a_tag(app, client, napoleonic):
    tag, _ = napoleonic
    collection, _ = create(client)
    other = app.test_client()
    other.post(f"/collections/{collection.view_token}/entries/tag", data={"tag_id": tag.id})
    db.session.refresh(collection)
    assert collection.entries == []


# --------------------------------------------------------- moving entries

def test_move_a_main_map_event_in_a_collection(client, napoleonic):
    _, events = napoleonic
    collection, _ = create(client)
    entry = service.add_event(collection, events[0].id, "")
    url = f"/collections/{collection.view_token}/entries/{entry.id}/edit"
    assert "Place in this collection" in client.get(url).get_data(as_text=True)

    client.post(url, data={"note": "Pratzen Heights", "lat": "49.13", "lon": "16.76"})
    db.session.refresh(entry)
    assert (entry.moved, entry.lat, entry.lon, entry.note) == (True, 49.13, 16.76, "Pratzen Heights")
    assert (events[0].lat, events[0].lon) == (50.9, 0.49)  # the event itself is unchanged

    client.post(url, data={"note": "Pratzen Heights", "lat": "49.13", "lon": "16.76", "reset": "1"})
    db.session.refresh(entry)
    assert (entry.moved, entry.lat) == (False, 50.9)


def test_moving_needs_both_coordinates(client, napoleonic):
    _, events = napoleonic
    collection, _ = create(client)
    entry = service.add_event(collection, events[0].id, "")
    response = client.post(f"/collections/{collection.view_token}/entries/{entry.id}/edit",
                           data={"note": "", "lat": "49.1", "lon": ""})
    assert response.status_code == 400
    assert "Give both latitude and longitude" in response.get_data(as_text=True)
    db.session.refresh(entry)
    assert not entry.moved


# ----------------------------------------------------------- the map view

def test_full_map_view_shows_only_the_collection(client, napoleonic):
    _, events = napoleonic
    collection, _ = create(client, title="Two battles")
    service.add_event(collection, events[0].id, "My favourite")
    client.post(f"/collections/{collection.view_token}/entries/custom", data=custom())

    view = client.get(f"/collections/{collection.view_token}").get_data(as_text=True)
    assert f"/collections/{collection.view_token}/map" in view  # the "Map view" button

    page = client.get(f"/collections/{collection.view_token}/map")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert f'data-events-url="/collections/{collection.view_token}/map.json"' in html
    assert "Two battles" in html and "Back to the collection" in html
    assert page.headers["X-Robots-Tag"] == "noindex, nofollow"

    data = client.get(f"/collections/{collection.view_token}/map.json").json
    assert [d["title"] for d in data] == ["Battle of Austerlitz", "My grandfather's village"]
    event, own = data
    assert event["note"] == "My favourite" and event["wiki_url"].startswith("https://en.wikipedia.org/")
    assert event["tags"] and event["summary"]
    assert own["wiki_url"] is None and own["tags"] == [] and own["category"] == "other"


def test_hidden_collection_map_is_gone_for_visitors(app, client, napoleonic):
    collection, _ = create(client)
    service.set_hidden(collection, True)
    visitor = app.test_client()
    assert visitor.get(f"/collections/{collection.view_token}/map").status_code == 410
    assert visitor.get(f"/collections/{collection.view_token}/map.json").status_code == 410
    assert client.get(f"/collections/{collection.view_token}/map").status_code == 200  # the owner


def test_main_map_still_loads_all_events(client):
    html = client.get("/").get_data(as_text=True)
    assert 'data-events-url="/api/events"' in html and "data-full-text" not in html


# --------------------------------------------------------------- natural

def test_natural_category(client, make_event):
    make_event(title="1755 Lisbon earthquake", category=Category.NATURAL, year=1755)
    assert client.get("/api/events").json[0]["category"] == "natural"
    assert 'data-category="natural"' in client.get("/").get_data(as_text=True)


def test_sync_updates_categories(app, make_event, tmp_path):
    from haam import importer
    from tests.test_importer import write_sync_csv

    event = make_event(title="Great Fire of London", wikidata_id="Q1", category=Category.OTHER, year=1666)
    path = tmp_path / "final.csv"
    write_sync_csv(path, [{"wikidata_id": "Q1", "url": event.wiki_url, "title": event.title, "year": "1666",
                           "lat": "51.5", "lon": "-0.1", "category": "natural", "status": "approved"}])
    stats = importer.sync_wikidata(str(path), report=lambda m: None)
    db.session.refresh(event)
    assert (stats.recategorized, event.category) == (1, Category.NATURAL)
    assert importer.sync_wikidata(str(path), report=lambda m: None).recategorized == 0


def test_collection_entries_keep_working_after_event_moves(client, napoleonic):
    _, events = napoleonic
    collection, _ = create(client)
    entry = service.add_event(collection, events[1].id, "")
    service.move_entry(entry, 51.0, 11.6)
    assert db.session.get(CollectionEntry, entry.id).to_dict()["moved"] is True
