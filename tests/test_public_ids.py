"""Events are addressed by their Wikipedia page id (row id for events without one)."""

import html as htmllib
import json
import re

import pytest

from haam import events, feed
from haam.models import Status

SITE = "https://haam.test"


def _manifest(client, query=""):
    page = client.get("/" + query).get_data(as_text=True)
    return json.loads(htmllib.unescape(re.search(r"data-manifest='([^']*)'", page).group(1)))


# ---------------------------------------------------------------- the helpers

def test_public_id_is_the_page_id_or_the_row_id(make_event):
    with_page = make_event("Battle of Zama", wiki_page_id=7001)
    without = make_event("Battle of Cannae")
    assert events.public_id(with_page) == 7001
    assert events.public_id(without) == without.id


def test_find_by_public_id(make_event):
    with_page = make_event("Battle of Zama", wiki_page_id=7001)
    without = make_event("Battle of Cannae")
    assert events.find_by_public_id(7001) is with_page
    assert events.find_by_public_id(without.id) is without
    # A row that has a page id is not reachable by its row id.
    assert events.find_by_public_id(with_page.id) is None
    assert events.find_by_public_id(0) is None
    assert events.find_by_public_id(None) is None
    assert events.find_by_public_id(10**30) is None


def test_find_approved_ignores_other_statuses(make_event):
    make_event("Pending battle", wiki_page_id=7002, status=Status.PENDING)
    assert events.find_by_public_id(7002) is not None
    assert events.find_approved(7002) is None


def test_moved_event_only_for_unused_ids(make_event):
    old = make_event("Battle of Zama", wiki_page_id=7001)
    assert events.moved_event(old.id) is old
    assert events.moved_event(7001) is None  # a live address
    taken = make_event("Battle of Cannae", wiki_page_id=old.id)  # a page id equal to another row id
    assert events.moved_event(old.id) is None
    assert events.find_approved(old.id) is taken


def test_public_ids_to_events_keeps_order_and_drops_unknown(make_event):
    a = make_event("Battle of Zama", wiki_page_id=7001)
    b = make_event("Battle of Cannae")
    make_event("Pending", wiki_page_id=7003, status=Status.PENDING)
    found = events.public_ids_to_events([b.id, 7003, 99999, 7001, 7001, True, "x"])
    assert found == [b, a]


# ------------------------------------------------------------- event pages

def test_event_page_uses_the_page_id(client, make_event):
    event = make_event("Battle of Zama", wiki_page_id=7001)
    response = client.get("/event/7001-battle-of-zama")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert f'<link rel="canonical" href="{SITE}/event/7001-battle-of-zama">' in page
    assert 'href="/?event=7001"' in page
    assert 'action="/event/7001/report"' in page
    assert f"/event/{event.id}-" not in page


def test_old_row_id_address_redirects_to_the_page_id_address(client, make_event):
    event = make_event("Battle of Zama", wiki_page_id=7001)
    for path in (f"/event/{event.id}-battle-of-zama", f"/event/{event.id}", f"/event/{event.id}-old-slug"):
        response = client.get(path)
        assert response.status_code == 301, path
        assert response.headers["Location"] == "/event/7001-battle-of-zama"


def test_row_id_that_is_another_events_page_id_is_not_redirected(client, make_event):
    first = make_event("Battle of Zama", wiki_page_id=7001)
    make_event("Battle of Cannae", wiki_page_id=first.id)
    response = client.get(f"/event/{first.id}-battle-of-cannae")
    assert response.status_code == 200


def test_unknown_and_unapproved_ids_are_404(client, make_event):
    make_event("Pending battle", wiki_page_id=7002, status=Status.PENDING)
    assert client.get("/event/7002-pending-battle").status_code == 404
    assert client.get("/event/123456-nothing").status_code == 404
    assert client.get("/event/99999999999999999999-nothing").status_code == 404


def test_event_without_a_page_id_has_a_working_address(client, make_event):
    event = make_event("Battle of Cannae")
    assert event.wiki_page_id is None
    response = client.get(f"/event/{event.id}-battle-of-cannae")
    assert response.status_code == 200
    assert f'<link rel="canonical" href="{SITE}/event/{event.id}-battle-of-cannae">' in response.get_data(as_text=True)
    assert client.get(f"/?event={event.id}").status_code == 200
    assert client.get(f"/api/events/{event.id}").json["id"] == event.id


def test_report_form_posts_to_the_page_id(client, make_event):
    event = make_event("Battle of Zama", wiki_page_id=7001)
    response = client.post("/event/7001/report", data={"message": "Wrong year"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/event/7001-battle-of-zama#report"
    assert len(event.reports) == 1


# -------------------------------------------------------------- shared links

def test_map_link_uses_the_page_id(client, make_event):
    make_event("Battle of Zama", year=-202, summary="Rome defeated Carthage.", wiki_page_id=7001)
    page = client.get("/?event=7001").get_data(as_text=True)
    assert "<title>Battle of Zama (202 BC) · Map · History As A Map</title>" in page
    assert f'content="{SITE}/event/7001-battle-of-zama"' in page


def test_old_map_link_redirects_and_keeps_the_rest_of_the_query(client, make_event):
    event = make_event("Battle of Zama", wiki_page_id=7001)
    response = client.get(f"/?event={event.id}&tag=3&view=5/48.2/16.4")
    assert response.status_code == 301
    assert response.headers["Location"] == "/?event=7001&tag=3&view=5/48.2/16.4"
    # An id that names nothing shows the plain map.
    assert client.get("/?event=424242").status_code == 200


# ------------------------------------------------------------------- the API

def test_api_event_by_page_id(client, make_event):
    event = make_event("Battle of Zama", wiki_page_id=7001)
    data = client.get("/api/events/7001").json
    assert data["title"] == "Battle of Zama" and data["id"] == 7001
    assert client.get(f"/api/events/{event.id}").status_code == 404


# --------------------------------------------------------------- map data

def test_chunks_carry_page_ids_and_group_by_them(client, make_event):
    made = [make_event(f"Battle {n}", wiki_page_id=9000 + n * 7, year=1000 + n) for n in range(30)]
    made.append(make_event("No page id", year=1500))
    manifest = _manifest(client)
    assert feed.FORMAT >= 3
    seen = {}
    for number, url in enumerate(manifest["core"]):
        chunk = client.get(url).json
        for pid in chunk["id"]:
            low, high = manifest["bounds"][number], manifest["bounds"][number + 1]
            assert low <= pid % manifest["modulus"] < high  # what chunkOf() in events-data.js computes
        seen.update(zip(chunk["id"], chunk["title"]))
    assert seen[9000 + 7 * 3] == "Battle 3"
    assert seen[made[-1].id] == "No page id"
    assert len(seen) == 31
    # The descriptions are keyed the same way.
    text_ids = set()
    for url in manifest["text"]:
        text_ids.update(client.get(url).json["id"])
    assert text_ids == set(seen)


def test_chunk_tags_follow_the_right_event(client, make_event):
    from haam.extensions import db
    from haam.models import Tag
    tag = db.session.query(Tag).filter_by(name="World War II").one()
    tagged = make_event("Tagged", wiki_page_id=5555)
    make_event("Untagged", wiki_page_id=5556)
    tagged.tags.append(tag)
    db.session.commit()
    manifest = _manifest(client)
    by_id = {}
    for url in manifest["core"]:
        chunk = client.get(url).json
        by_id.update(zip(chunk["id"], chunk["tags"]))
    assert by_id == {5555: [tag.id], 5556: []}


def test_a_changed_page_id_changes_the_version(client, make_event):
    event = make_event("Battle of Zama", wiki_page_id=7001)
    before = _manifest(client)["version"]
    from haam.extensions import db
    event.wiki_page_id = 7002
    db.session.commit()
    client.application.extensions.pop("haam_feed_state", None)
    assert _manifest(client)["version"] != before


# ---------------------------------------------------------- sitemap, welcome, game

def test_sitemap_lists_page_id_addresses(client, make_event):
    make_event("Battle of Zama", wiki_page_id=7001)
    cannae = make_event("Battle of Cannae")
    body = client.get("/sitemap.xml").get_data(as_text=True)
    assert f"{SITE}/event/7001-battle-of-zama" in body
    assert f"{SITE}/event/{cannae.id}-battle-of-cannae" in body


def test_welcome_card_carries_public_ids(client, make_event):
    make_event("Battle of Zama", date_label="19 October 202 BC", year=-202, wiki_page_id=7001)
    data = client.get("/api/welcome?month=10&day=19").json
    assert [e["id"] for e in data["on_this_day"]] == [7001]


def test_game_answer_links_to_the_page_id(client, make_event):
    from haam import game
    for n in range(6):
        make_event(f"Battle {n}", year=1000 + 100 * n, wiki_page_id=8000 + n, lat=10.0 * n, lon=20.0 * n,
                   summary="A long description. " * 20)
    day = game.today_utc().isoformat()
    answer = client.post("/api/game/check", json={"date": day, "index": 0, "lat": 0, "lon": 0}).json["answer"]
    assert answer["id"] >= 8000
    assert answer["map_url"] == f"/?event={answer['id']}"


# ---------------------------------------------------------------- collections

def test_collections_use_public_ids(client, make_event):
    from tests.test_collections import create
    event = make_event("Battle of Zama", wiki_page_id=7001)
    collection, _ = create(client)
    url = f"/collections/{collection.view_token}/entries/event.json"

    assert client.post(url, json={"event_id": event.id}).status_code == 400  # a row id is not an address
    response = client.post(url, json={"event_id": 7001})
    assert response.status_code == 201
    assert response.get_json()["collection"]["event_ids"] == [7001]
    assert client.get("/collections/mine.json").get_json()["collections"][0]["event_ids"] == [7001]
    assert client.post(url, json={"event_id": 7001}).status_code == 409


def test_new_collection_with_an_event_by_page_id(client, make_event):
    event = make_event("Battle of Zama", wiki_page_id=7001)
    page = client.get("/collections/new?event=7001").get_data(as_text=True)
    assert 'name="event" value="7001"' in page
    response = client.post("/collections/new", data={"title": "Zama", "event": "7001"})
    assert response.status_code == 302
    from haam.extensions import db
    from haam.models import Collection
    assert [e.event_id for e in db.session.scalar(db.select(Collection)).entries] == [event.id]


@pytest.mark.parametrize("who", ["owner", "visitor"])
def test_event_pickers_send_public_ids(client, app, make_event, who):
    from tests.test_collections import create
    event = make_event("Battle of Zama", wiki_page_id=7001)
    collection, _ = create(client)
    if who == "owner":
        response = client.post(f"/collections/{collection.view_token}/entries/event", data={"event_id": "7001"})
        assert response.status_code == 302
    else:
        response = app.test_client().post(f"/collections/{collection.view_token}/suggest",
                                          data={"event_id": "7001", "message": "Add it"})
        assert response.status_code == 302
        assert [s.event_id for s in collection.suggestions] == [event.id]
        return
    assert [e.event_id for e in collection.entries] == [event.id]
