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
    assert [e["title"] for e in admin_client.get("/api/events").json] == ["Battle of Hastings"]


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
