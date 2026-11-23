"""Entries placed away from Wikipedia's own coordinates show a 'manually reconfirmed' note."""

from haam import collections_service as service
from haam.extensions import db
from haam.models import Category

from tests.test_collections import create


def _entry(client):
    collection, _ = create(client)
    entry = service.add_custom(collection, service.CustomEntryData(
        title="Gjøa winters", year=1903, date_label="", category=Category.NAVAL, lat=68.6256, lon=-95.8756,
        summary="", link="", note=""))
    return collection, entry


def test_note_shows_wikipedia_coordinates_and_maps_link(client):
    collection, entry = _entry(client)
    entry.wiki_lat, entry.wiki_lon = 59.9037, 10.699
    db.session.commit()
    html = client.get(f"/collections/{collection.view_token}").get_data(as_text=True)
    assert "Manually reconfirmed here" in html
    assert "68.6256, -95.8756" in html
    assert "https://www.google.com/maps?q=59.9037,10.699" in html


def test_no_note_without_wikipedia_coordinates(client):
    collection, _ = _entry(client)
    assert "Manually reconfirmed" not in client.get(f"/collections/{collection.view_token}").get_data(as_text=True)


def test_moving_the_pin_drops_the_note(client):
    _, entry = _entry(client)
    entry.wiki_lat, entry.wiki_lon = 59.9037, 10.699
    service.update_custom(entry, service.CustomEntryData(
        title="Gjøa winters", year=1903, date_label="", category=Category.NAVAL, lat=68.7, lon=-95.9,
        summary="", link="", note=""))
    assert entry.wiki_lat is None and not entry.reconfirmed
