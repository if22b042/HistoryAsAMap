from haam.extensions import db
from haam.models import Event, EventReport, ReportStatus


def _report(client, event, **data):
    return client.post(f"/event/{event.id}/report", data={"message": "Wrong place.", **data})


def test_report_form_is_on_the_event_page(client, make_event):
    event = make_event()
    html = client.get(f"/event/{event.id}-battle-of-hastings").get_data(as_text=True)
    assert f'action="/event/{event.id}/report"' in html


def test_report_is_stored(client, make_event):
    event = make_event()
    response = _report(client, event, proposed_year="1067", proposed_lat="51.1", proposed_lon="0.5")
    assert response.status_code == 302
    report = db.session.scalar(db.select(EventReport))
    assert (report.event_id, report.status) == (event.id, ReportStatus.OPEN)
    assert (report.proposed_year, report.proposed_lat, report.proposed_lon) == (1067, 51.1, 0.5)
    assert report.proposed_date_label is None


def test_report_needs_a_message_and_valid_values(client, make_event):
    event = make_event()
    assert client.post(f"/event/{event.id}/report", data={"message": ""}).status_code == 400
    assert _report(client, event, proposed_year="nonsense").status_code == 400
    assert _report(client, event, proposed_lat="51.1").status_code == 400  # latitude without longitude
    assert _report(client, event, proposed_lat="95", proposed_lon="0").status_code == 400
    assert db.session.scalar(db.select(db.func.count(EventReport.id))) == 0


def test_report_is_limited_to_five_an_hour(app, client, make_event):
    app.config["RATELIMIT_ENABLED"] = True
    event = make_event()
    assert [_report(client, event).status_code for _ in range(5)] == [302] * 5
    assert _report(client, event).status_code == 429


def test_admin_applies_a_report(admin_client, make_event):
    event = make_event(year=1066, date_label="14 October 1066", lat=50.9, lon=0.49)
    _report(admin_client, event, proposed_year="1067", proposed_lat="51.0", proposed_lon="0.5")
    report = db.session.scalar(db.select(EventReport))

    assert "Reports" in admin_client.get("/admin/").get_data(as_text=True)
    page = admin_client.get("/admin/reports").get_data(as_text=True)
    assert "Wrong place." in page and "1067" in page and "51.0000, 0.5000" in page

    admin_client.post(f"/admin/reports/{report.id}/apply")
    db.session.expire_all()
    event = db.session.get(Event, event.id)
    assert (event.year, event.lat, event.lon, event.modified) == (1067, 51.0, 0.5, True)
    assert event.date_label == "1067"  # the old date no longer fitted the new year
    assert db.session.get(EventReport, report.id).status == ReportStatus.APPLIED
    assert "No open reports" in admin_client.get("/admin/reports").get_data(as_text=True)


def test_admin_dismisses_a_report(admin_client, make_event):
    event = make_event()
    _report(admin_client, event, proposed_year="1100")
    report = db.session.scalar(db.select(EventReport))
    admin_client.post(f"/admin/reports/{report.id}/dismiss")
    db.session.expire_all()
    assert db.session.get(EventReport, report.id).status == ReportStatus.DISMISSED
    assert db.session.get(Event, event.id).year == 1066


def test_reports_need_login(client, make_event):
    event = make_event()
    _report(client, event)
    report = db.session.scalar(db.select(EventReport))
    assert client.get("/admin/reports").status_code == 302
    assert client.post(f"/admin/reports/{report.id}/apply").status_code == 302


def test_review_header_shows_the_open_count(admin_client, make_event):
    event = make_event()
    _report(admin_client, event)
    assert '<span class="tab-count">1</span></a>' in admin_client.get("/admin/").get_data(as_text=True)


def test_admin_features_a_collection(admin_client):
    from haam import collections_service

    collection, _ = collections_service.create_collection("Mine", "", is_public=True)
    assert "Feature" in admin_client.get("/admin/collections").get_data(as_text=True)
    admin_client.post(f"/admin/collections/{collection.id}/feature")
    db.session.expire_all()
    assert db.session.get(type(collection), collection.id).is_featured is True
    admin_client.post(f"/admin/collections/{collection.id}/unfeature")
    db.session.expire_all()
    assert db.session.get(type(collection), collection.id).is_featured is False
