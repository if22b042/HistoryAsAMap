"""A new collection made from the events a search or filter showed on the map."""

from haam import collections_service as service
from haam.extensions import db
from haam.models import Collection, Status

FORM = "/collections/from-search"
CREATE = "/collections/from-search/create"


def _events(make_event, count=3):
    return [make_event(f"Battle {n}", year=1000 - n * 10, date_label=str(1000 - n * 10),
                       wiki_page_id=7000 + n) for n in range(count)]


def test_form_is_prefilled_with_the_title_and_the_count(client, make_event):
    _events(make_event)
    response = client.post(FORM, data={"ids": "7000,7001,7002,424242", "title": "Napoleonic Wars – “battle”"})
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "<strong>3 events</strong> will be added" in page
    assert 'value="Napoleonic Wars – “battle”"' in page
    assert f'action="{CREATE}"' in page
    # The ids come back in date order, only the known ones.
    assert 'name="ids"' in page and 'value="7002,7001,7000"' in page
    assert "Start from an official tag" not in page


def test_form_escapes_the_title_and_ignores_unknown_and_unapproved_ids(client, make_event):
    make_event("Pending", wiki_page_id=7100, status=Status.PENDING)
    _events(make_event, 1)
    page = client.post(FORM, data={"ids": "7100, 7000 ,abc,-1,0", "title": '"><script>x</script>'}).get_data(as_text=True)
    assert "<script>x</script>" not in page
    assert "<strong>1 event</strong> will be added" in page


def test_nothing_known_goes_back_to_the_map(client, make_event):
    for ids in ("", "abc", "424242"):
        response = client.post(FORM, data={"ids": ids})
        assert response.status_code == 302 and response.headers["Location"] == "/"


def test_creating_adds_the_events_in_date_order(client, make_event):
    events = _events(make_event, 4)
    response = client.post(CREATE, data={"title": "Medieval battles", "description": "d",
                                         "ids": "7000,7001,7002,7003,424242,7001"})
    assert response.status_code == 302
    collection = db.session.scalar(db.select(Collection))
    assert response.headers["Location"] == f"/collections/{collection.view_token}/manage"
    assert collection.title == "Medieval battles"
    assert [e.event_id for e in collection.entries] == [events[3].id, events[2].id, events[1].id, events[0].id]
    assert [e.position for e in collection.entries] == [0, 1, 2, 3]
    manage = client.get(response.headers["Location"])  # this browser may edit it
    assert manage.status_code == 200 and "Added 4 events" in manage.get_data(as_text=True)


def test_creating_needs_a_title_and_events(client, make_event):
    _events(make_event, 2)
    response = client.post(CREATE, data={"title": "", "ids": "7000"})
    assert response.status_code == 400
    assert db.session.scalar(db.select(db.func.count(Collection.id))) == 0
    assert client.post(CREATE, data={"title": "Empty", "ids": "999"}).status_code == 302
    assert db.session.scalar(db.select(db.func.count(Collection.id))) == 0


def test_collection_is_capped_at_the_maximum(client, make_event, monkeypatch):
    monkeypatch.setattr(service, "MAX_ENTRIES", 3)
    _events(make_event, 5)
    response = client.post(CREATE, data={"title": "Too many", "ids": "7000,7001,7002,7003,7004"})
    collection = db.session.scalar(db.select(Collection))
    assert len(collection.entries) == 3
    assert [e.event.wiki_page_id for e in collection.entries] == [7004, 7003, 7002]  # the oldest three
    assert "did not fit" in client.get(response.headers["Location"]).get_data(as_text=True)
    page = client.post(FORM, data={"ids": "7000,7001,7002,7003,7004"}).get_data(as_text=True)
    assert "<strong>3 events</strong> will be added" in page and "2 more did not fit" in page


def test_the_form_step_needs_no_csrf_but_creating_does(app, client, make_event):
    _events(make_event, 1)
    app.config["WTF_CSRF_ENABLED"] = True
    page = client.post(FORM, data={"ids": "7000", "title": "Mine"}).get_data(as_text=True)
    assert 'name="csrf_token"' in page
    refused = client.post(CREATE, data={"title": "Mine", "ids": "7000"})
    assert refused.status_code == 400
    assert db.session.scalar(db.select(db.func.count(Collection.id))) == 0


def test_creating_is_limited_like_other_collection_creation(app, client, make_event):
    _events(make_event, 1)
    app.config["RATELIMIT_ENABLED"] = True
    for n in range(10):
        assert client.post(CREATE, data={"title": f"C{n}", "ids": "7000"}).status_code == 302
    assert client.post(CREATE, data={"title": "C10", "ids": "7000"}).status_code == 429
    # The same budget as /collections/new.
    assert client.post("/collections/new", data={"title": "Other"}).status_code == 429
