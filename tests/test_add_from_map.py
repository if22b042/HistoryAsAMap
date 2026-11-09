"""Adding events to a collection straight from the main map (details panel / big search)."""

from haam.extensions import db
from haam.models import Collection, Status
from tests.test_collections import create


def add(client, collection, event_id, **kwargs):
    return client.post(f"/collections/{collection.view_token}/entries/event.json",
                       json={"event_id": event_id}, **kwargs)


def test_mine_lists_editable_collections_with_their_events(app, client, make_event):
    event = make_event()
    assert client.get("/collections/mine.json").get_json()["collections"] == []
    collection, _ = create(client)
    add(client, collection, event.id)

    data = client.get("/collections/mine.json").get_json()
    assert data["csrf_token"]
    assert data["new_url"] == "/collections/new"
    assert data["collections"] == [{
        "title": "Roman battles",
        "url": f"/collections/{collection.view_token}",
        "add_url": f"/collections/{collection.view_token}/entries/event.json",
        "event_ids": [event.id],
    }]
    # Another browser sees nothing and gets no CSRF token (so no session cookie).
    assert app.test_client().get("/collections/mine.json").get_json() == {
        "csrf_token": None, "new_url": "/collections/new", "collections": []}


def test_add_event_from_the_map(client, make_event):
    event = make_event()
    collection, _ = create(client)
    response = add(client, collection, event.id)
    assert response.status_code == 201
    data = response.get_json()
    assert data["message"] == "Added “Battle of Hastings” to “Roman battles”."
    assert data["collection"]["event_ids"] == [event.id]
    assert [entry.event_id for entry in collection.entries] == [event.id]


def test_add_event_needs_edit_access(app, client, make_event):
    event = make_event()
    collection, _ = create(client)
    response = add(app.test_client(), collection, event.id)
    assert response.status_code == 403
    assert "edit link" in response.get_json()["error"]
    assert collection.entries == []
    assert client.post("/collections/missing/entries/event.json", json={"event_id": event.id}).status_code == 404


def test_add_event_only_once(client, make_event):
    event = make_event()
    collection, _ = create(client)
    assert add(client, collection, event.id).status_code == 201
    response = add(client, collection, event.id)
    assert response.status_code == 409
    assert response.get_json()["error"] == "“Battle of Hastings” is already in this collection."
    assert len(collection.entries) == 1


def test_add_event_rejects_bad_input(client, make_event):
    collection, _ = create(client)
    pending = make_event(title="Pending battle", status=Status.PENDING)
    assert add(client, collection, pending.id).status_code == 400
    assert add(client, collection, "1").status_code == 400
    assert add(client, collection, True).status_code == 400
    assert client.post(f"/collections/{collection.view_token}/entries/event.json",
                       data="nonsense").status_code == 400
    assert collection.entries == []


def test_add_event_checks_csrf(app, client, make_event):
    event = make_event()
    collection, _ = create(client)
    app.config["WTF_CSRF_ENABLED"] = True
    assert add(client, collection, event.id).status_code == 400  # no token
    assert collection.entries == []

    token = client.get("/collections/mine.json").get_json()["csrf_token"]
    assert add(client, collection, event.id, headers={"X-CSRFToken": token}).status_code == 201


def test_new_collection_with_an_event(client, make_event):
    event = make_event()
    page = client.get(f"/collections/new?event={event.id}").get_data(as_text=True)
    assert "Battle of Hastings" in page and "will be its first entry" in page

    response = client.post(f"/collections/new?event={event.id}", data={"title": "Hastings", "event": event.id})
    assert response.status_code == 302
    collection = db.session.scalar(db.select(Collection).filter_by(title="Hastings"))
    assert [entry.event_id for entry in collection.entries] == [event.id]


def test_new_collection_ignores_pending_events(client, make_event):
    pending = make_event(title="Pending battle", status=Status.PENDING)
    assert "first entry" not in client.get(f"/collections/new?event={pending.id}").get_data(as_text=True)
    client.post("/collections/new", data={"title": "Empty", "event": pending.id})
    collection = db.session.scalar(db.select(Collection).filter_by(title="Empty"))
    assert collection.entries == []
