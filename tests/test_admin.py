from haam.extensions import db
from haam.models import Event, Status

from tests.conftest import ADMIN_PASSWORD


def test_admin_pages_require_login(client, make_event):
    event = make_event(status=Status.PENDING)
    assert client.get("/admin/").status_code == 302
    assert client.get(f"/admin/events/{event.id}/edit").status_code == 302
    assert client.post(f"/admin/events/{event.id}/approve").status_code == 302
    assert db.session.get(Event, event.id).status == Status.PENDING


def test_wrong_password(client):
    response = client.post("/admin/login", data={"username": "admin", "password": "nope"})
    assert b"Wrong username or password" in response.data
    assert client.get("/admin/").status_code == 302


def test_login_disabled_without_hash(app, client):
    app.config["ADMIN_PASSWORD_HASH"] = None
    client.post("/admin/login", data={"username": "admin", "password": ADMIN_PASSWORD})
    assert client.get("/admin/").status_code == 302


def test_login_redirect_stays_on_site(client):
    response = client.post("/admin/login?next=https://evil.example/", data={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.headers["Location"] == "/admin/"


def test_review_queue_and_approve(admin_client, make_event):
    event = make_event(status=Status.PENDING)
    html = admin_client.get("/admin/").get_data(as_text=True)
    assert "Battle of Hastings" in html

    admin_client.post(f"/admin/events/{event.id}/approve")
    assert db.session.get(Event, event.id).status == Status.APPROVED
    assert admin_client.get(f"/api/events/{event.id}").json["title"] == "Battle of Hastings"


def test_reject_and_delete(admin_client, make_event):
    event = make_event(status=Status.PENDING)
    admin_client.post(f"/admin/events/{event.id}/reject")
    assert db.session.get(Event, event.id).status == Status.REJECTED
    admin_client.post(f"/admin/events/{event.id}/delete")
    assert db.session.get(Event, event.id) is None


def test_edit(admin_client, make_event):
    event = make_event()
    assert admin_client.get(f"/admin/events/{event.id}/edit").status_code == 200
    response = admin_client.post(f"/admin/events/{event.id}/edit", data={
        "url": event.wiki_url, "title": "Battle of Hastings (1066)", "year": "1066",
        "date_label": "14 October 1066", "summary": "Edited.", "lat": "50.91", "lon": "0.49",
        "category": "military",
    })
    assert response.status_code == 302
    event = db.session.get(Event, event.id)
    assert (event.title, event.summary, event.lat, event.modified) == ("Battle of Hastings (1066)", "Edited.", 50.91, True)


def test_unknown_event_is_404(admin_client):
    assert admin_client.get("/admin/events/999/edit").status_code == 404
    assert admin_client.get("/admin/?status=bogus").status_code == 404


def test_logout(admin_client):
    admin_client.post("/admin/logout")
    assert admin_client.get("/admin/").status_code == 302


# ------------------------------------------------------------ bulk actions and tags

import pytest

from haam import feed
from haam.models import Tag, event_tags


def _bulk(client, action, ids, **extra):
    return client.post(f"/admin/events/bulk/{action}", data={"event_ids": [str(i) for i in ids], **extra})


def test_bulk_requires_login(client, make_event):
    event = make_event(status=Status.PENDING)
    assert _bulk(client, "approve", [event.id]).status_code == 302
    assert db.session.get(Event, event.id).status == Status.PENDING


def test_bulk_approve_and_reject(admin_client, make_event):
    a, b, c = (make_event(title=t, status=Status.PENDING) for t in "ABC")
    response = _bulk(admin_client, "approve", [a.id, b.id, 99999, "junk"])
    assert response.status_code == 302
    assert db.session.get(Event, a.id).status == Status.APPROVED
    assert db.session.get(Event, b.id).status == Status.APPROVED
    assert db.session.get(Event, c.id).status == Status.PENDING
    _bulk(admin_client, "reject", [c.id, b.id])
    assert db.session.get(Event, c.id).status == Status.REJECTED
    assert db.session.get(Event, b.id).status == Status.REJECTED


def test_bulk_without_selection_changes_nothing(admin_client, make_event):
    event = make_event(status=Status.PENDING)
    html = admin_client.post("/admin/events/bulk/approve", data={}, follow_redirects=True).get_data(as_text=True)
    assert "Select at least one event" in html
    assert db.session.get(Event, event.id).status == Status.PENDING


def test_bulk_approve_changes_feed_version(app, admin_client, make_event):
    app.config["FEED_STATE_TTL"] = 0
    event = make_event(status=Status.PENDING)
    before = feed.state()["version"]
    _bulk(admin_client, "approve", [event.id])
    assert feed.state()["version"] != before


def test_bulk_needs_csrf(app, admin_client, make_event):
    event = make_event(status=Status.PENDING)
    app.config["WTF_CSRF_ENABLED"] = True
    assert _bulk(admin_client, "approve", [event.id]).status_code == 400
    assert db.session.get(Event, event.id).status == Status.PENDING


def test_review_page_has_bulk_controls(admin_client, make_event):
    make_event(status=Status.PENDING)
    html = admin_client.get("/admin/").get_data(as_text=True)
    assert "Approve selected" in html and "Reject selected" in html and 'name="event_ids"' in html
    assert "/admin/tags" in html


def _tag(name):
    return db.session.scalar(db.select(Tag).where(Tag.name == name))


def test_tags_page_requires_login(client):
    assert client.get("/admin/tags").status_code == 302
    assert client.post("/admin/tags/new", data={"name": "X"}).status_code == 302
    assert _tag("X") is None


def test_tags_page_lists_largest_first_and_flags_empty(admin_client, make_event):
    ww2 = _tag("World War II")
    for i in range(2):
        make_event(title=f"E{i}", tags=[ww2])
    html = admin_client.get("/admin/tags").get_data(as_text=True)
    assert html.index("World War II") < html.index("Norman Conquest of England")
    assert "2 events" in html and "empty" in html


def test_create_tag(admin_client):
    admin_client.post("/admin/tags/new", data={"name": "  Cold   War ", "start_year": "1947", "end_year": ""})
    tag = _tag("Cold War")
    assert tag is not None and tag.start_year == 1947 and tag.end_year is None
    # duplicates (case-insensitive) and blanks are refused
    admin_client.post("/admin/tags/new", data={"name": "cold war"})
    admin_client.post("/admin/tags/new", data={"name": "  "})
    assert db.session.scalar(db.select(db.func.count(Tag.id)).where(Tag.name.ilike("cold war"))) == 1


def test_rename_tag_updates_feed_version_and_rejects_duplicates(app, admin_client):
    app.config["FEED_STATE_TTL"] = 0
    tag = _tag("World War II")
    before = feed.state()["version"]
    admin_client.post(f"/admin/tags/{tag.id}/rename", data={"name": "Second World War"})
    assert _tag("Second World War").id == tag.id
    assert feed.state()["version"] != before
    admin_client.post(f"/admin/tags/{tag.id}/rename", data={"name": "Norman Conquest of England"})
    assert _tag("Second World War") is not None


def test_delete_only_empty_tags(admin_client, make_event):
    used, empty = _tag("World War II"), _tag("Norman Conquest of England")
    make_event(tags=[used])
    admin_client.post(f"/admin/tags/{used.id}/delete")
    assert _tag("World War II") is not None
    admin_client.post(f"/admin/tags/{empty.id}/delete")
    assert _tag("Norman Conquest of England") is None


def test_merge_tags(app, admin_client, make_event):
    app.config["FEED_STATE_TTL"] = 0
    source, target = _tag("Norman Conquest of England"), _tag("World War II")
    only_source = make_event(title="One", tags=[source])
    both = make_event(title="Two", tags=[source, target])
    before = feed.state()["version"]
    admin_client.post(f"/admin/tags/{source.id}/merge", data={"target": str(target.id)})
    assert _tag("Norman Conquest of England") is None
    assert {t.name for t in db.session.get(Event, only_source.id).tags} == {"World War II"}
    assert [t.name for t in db.session.get(Event, both.id).tags] == ["World War II"]
    assert db.session.scalar(db.select(db.func.count()).select_from(event_tags)) == 2
    assert feed.state()["version"] != before


def test_merge_into_itself_or_nothing_changes_nothing(admin_client):
    tag = _tag("World War II")
    admin_client.post(f"/admin/tags/{tag.id}/merge", data={"target": str(tag.id)})
    admin_client.post(f"/admin/tags/{tag.id}/merge", data={})
    assert _tag("World War II") is not None


@pytest.mark.parametrize("path", ["new", "{id}/rename", "{id}/delete", "{id}/merge"])
def test_tag_actions_need_csrf(app, admin_client, path):
    tag = _tag("World War II")
    app.config["WTF_CSRF_ENABLED"] = True
    response = admin_client.post(f"/admin/tags/{path.format(id=tag.id)}", data={"name": "Y", "target": "1"})
    assert response.status_code == 400
    assert _tag("World War II") is not None and _tag("Y") is None
