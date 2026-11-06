from datetime import datetime, timedelta, timezone

from haam import collections_service, events
from haam.collections_service import CustomEntryData
from haam.extensions import db
from haam.models import Category, Event, Status
from haam.views import admin as admin_views

from tests.test_submission import form_data


def test_website_submissions_are_marked(client, wiki, make_event):
    wiki.add("Battle of Hastings")
    client.post("/submit/confirm", data=form_data())
    submitted = db.session.scalar(db.select(Event).filter_by(title="Battle of Hastings"))
    imported = make_event(title="Battle of Stamford Bridge")
    assert submitted.from_website is True
    assert imported.from_website is False


def test_recent_requires_login(client):
    assert client.get("/admin/recent").status_code == 302


def test_recent_lists_new_things_but_not_imports(admin_client, wiki, make_event):
    wiki.add("Battle of Hastings")
    admin_client.post("/submit/confirm", data=form_data())
    make_event(title="Imported Battle")
    main_event = make_event(title="Siege of Paris")
    collection, _ = collections_service.create_collection("Norman wars", "", is_public=True)
    collections_service.add_event(collection, main_event.id, "")
    collections_service.add_custom(collection, CustomEntryData(
        title="My grandfather's village", year=1950, date_label="", category=Category.OTHER,
        lat=45.0, lon=9.0, summary="", link="", note=""))
    collections_service.report(collection, "spam please check")

    html = admin_client.get("/admin/recent").get_data(as_text=True)
    assert "Battle of Hastings" in html
    assert "Imported Battle" not in html
    assert "2</strong> imported" in html
    assert "Norman wars" in html
    assert "My grandfather&#39;s village" in html
    assert "Siege of Paris" in html  # added to the collection from the main map
    assert "spam please check" in html


def test_recent_respects_the_period(admin_client, make_event):
    old = make_event(title="Old Submission", from_website=True)
    old.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db.session.commit()
    assert "Old Submission" not in admin_client.get("/admin/recent?days=7").get_data(as_text=True)
    assert "Old Submission" in admin_client.get("/admin/recent?days=30").get_data(as_text=True)
    assert admin_client.get("/admin/recent?days=999").status_code == 200  # falls back to 7 days


def test_status_counts(make_event):
    make_event(title="A")
    make_event(title="B")
    make_event(title="C", status=Status.PENDING)
    assert events.status_counts() == {Status.APPROVED: 2, Status.PENDING: 1, Status.REJECTED: 0}


def test_review_tabs_are_paginated(admin_client, make_event, monkeypatch):
    monkeypatch.setattr(admin_views, "REVIEW_PER_PAGE", 2)
    for i in range(5):
        make_event(title=f"Battle {i}")
    first = admin_client.get("/admin/?status=approved").get_data(as_text=True)
    last = admin_client.get("/admin/?status=approved&page=3").get_data(as_text=True)
    assert "Page 1 of 3" in first and "Battle 4" in first and "Battle 0" not in first
    assert "Page 3 of 3" in last and "Battle 0" in last
    assert admin_client.get("/admin/?status=approved&page=99").status_code == 200
