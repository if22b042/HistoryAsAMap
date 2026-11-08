"""The map's welcome card: "On this day", today's game and featured collections."""

from datetime import date, timedelta

import pytest

from haam import collections_service as service
from haam import welcome
from haam.cli import check_on_this_day_command
from haam.dates import month_day
from haam.extensions import db
from haam.models import Category, CollectionReport, Status, Tag


@pytest.mark.parametrize("label, expected", [
    ("8 November 1592", (11, 8)),
    ("14 October 1066", (10, 14)),
    ("31 August 44 BC", (8, 31)),
    ("8–10 November 1592", (11, 8)),
    ("30 November – 2 December 1592", (11, 30)),
    ("July 4, 1776", (7, 4)),
    ("4 July", (7, 4)),
    ("29 February 1704", (2, 29)),
    ("30 February 1700", None),
    ("November 1592", None),
    ("July 1916", None),
    ("September AD 9", None),
    ("1592", None),
    ("44 BC", None),
    ("", None),
    (None, None),
])
def test_month_day_from_label(label, expected):
    assert month_day(label) == expected


def test_event_month_and_day_follow_its_date_label(make_event):
    event = make_event(date_label="14 October 1066")
    assert (event.month, event.day) == (10, 14)
    event.date_label = "1066"
    db.session.commit()
    assert (event.month, event.day) == (None, None)
    event.date_label = "25 December 1066"
    db.session.commit()
    assert (event.month, event.day) == (12, 25)


def test_on_this_day_picks_the_best_events_of_that_day(make_event):
    tag = db.session.get(Tag, 1)
    short = make_event("Short", year=1500, date_label="8 November 1500", summary="Short.")
    long_ = make_event("Long", year=1600, date_label="8 November 1600", summary="Long. " * 100)
    tagged = make_event("Tagged", year=1066, date_label="8 November 1066", summary="Tagged.")
    tagged.tags.append(tag)
    db.session.commit()
    make_event("Other day", year=1700, date_label="9 November 1700", summary="x" * 900)
    make_event("Pending", year=1800, date_label="8 November 1800", status=Status.PENDING, summary="x" * 900)
    make_event("Month only", year=1900, date_label="November 1900", summary="x" * 900)

    assert [e.title for e in welcome.on_this_day(11, 8, limit=2)] == ["Tagged", "Long"]  # oldest first
    assert [e.id for e in welcome.on_this_day(11, 8)] == [tagged.id, short.id, long_.id]


def test_on_this_day_spreads_centuries_and_categories(make_event):
    for i in range(5):
        make_event(f"Military {i}", year=1800 + i, date_label=f"1 May {1800 + i}", summary="x" * (900 - i))
    make_event("Science", year=1600, date_label="1 May 1600", summary="Short.", category=Category.SCIENTIFIC)
    make_event("Treaty", year=1900, date_label="1 May 1900", summary="Short.", category=Category.DIPLOMATIC)

    picked = [e.title for e in welcome.on_this_day(5, 1, limit=3)]
    assert picked == ["Science", "Military 0", "Treaty"]


def test_every_calendar_day_has_an_event_when_the_data_covers_it(app, make_event):
    days = [date(2000, 1, 1) + timedelta(days=n) for n in range(366)]  # 2000 is a leap year
    for n, day in enumerate(days):
        make_event(f"Event {n}", year=1900, date_label=f"{day.day} {day:%B} 1900")
    assert welcome.days_without_events() == []
    for day in days:
        assert [e.title for e in welcome.on_this_day(day.month, day.day)], day

    result = app.test_cli_runner().invoke(check_on_this_day_command)
    assert result.exit_code == 0
    assert "366 days" in result.output


def test_check_reports_missing_days(app, make_event):
    make_event(date_label="14 October 1066")
    missing = welcome.days_without_events()
    assert len(missing) == 365 and (10, 14) not in missing and (2, 29) in missing

    result = app.test_cli_runner().invoke(check_on_this_day_command)
    assert result.exit_code == 1
    assert "29 February" in result.output


def _collection(title, entries, *, public=True, hidden=False, reports=0):
    collection, _ = service.create_collection(title, "", public)
    collection.is_hidden = hidden
    for event in entries:
        service.add_event(collection, event.id, "")
    for _ in range(reports):
        db.session.add(CollectionReport(collection=collection, reason="spam"))
    db.session.commit()
    return collection


def test_featured_collections_are_public_unreported_and_largest(make_event):
    events = [make_event(f"Battle {i}", year=1000 + i) for i in range(4)]
    big = _collection("Big", events[:3])
    small = _collection("Small", events[:1])
    newer = _collection("Newer", events[:1])
    _collection("Private", events, public=False)
    _collection("Hidden", events, hidden=True)
    _collection("Reported", events, reports=1)
    _collection("Empty", [])

    featured = welcome.featured_collections()
    assert featured == [(big, 3), (newer, 1), (small, 1)]  # ties: newest first


def test_welcome_api(client, make_event):
    event = make_event(date_label="29 February 1704", year=1704)
    _collection("Leap years", [event])

    data = client.get("/api/welcome?month=2&day=29").json
    assert data["day_label"] == "29 February"
    assert [e["id"] for e in data["on_this_day"]] == [event.id]
    assert data["on_this_day"][0]["date"] == "29 February 1704"
    assert data["game"]["url"] == "/game" and data["game"]["number"] >= 1
    assert data["collections"][0]["title"] == "Leap years"
    assert data["collections"][0]["url"].startswith("/collections/")
    assert client.get(data["collections"][0]["url"]).status_code == 200
    assert client.get(data["game"]["url"]).status_code == 200
    # Collection maps reuse the map page, without the welcome card.
    assert 'id="welcome"' not in client.get(data["collections"][0]["url"] + "/map").get_data(as_text=True)


@pytest.mark.parametrize("query", ["", "?month=2&day=30", "?month=13&day=1", "?month=x&day=1"])
def test_welcome_api_falls_back_to_today(client, query):
    response = client.get(f"/api/welcome{query}")
    assert response.status_code == 200
    today = welcome.game.today_utc()
    assert response.json["day_label"] == f"{today.day} {today:%B}"
    assert "max-age=300" in response.headers["Cache-Control"]


def test_map_page_has_the_welcome_card(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="welcome"' in html and 'data-url="/api/welcome"' in html
    assert "js/welcome.js" in html
