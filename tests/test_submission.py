from haam.extensions import db
from haam.models import Event, Status, Tag

URL = "https://en.wikipedia.org/wiki/Battle_of_Hastings"


def form_data(**overrides):
    data = {
        "url": URL,
        "title": "Battle of Hastings",
        "year": "1066",
        "date_label": "1066",
        "summary": "The Battle of Hastings was an event.",
        "lat": "50.9",
        "lon": "0.49",
        "category": "military",
    }
    data.update(overrides)
    return data


def test_pages_render(client):
    for path in ("/", "/about", "/submit"):
        assert client.get(path).status_code == 200


def test_security_headers(client):
    response = client.get("/")
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_rejects_non_english_link(client):
    response = client.post("/submit", data={"url": "https://de.wikipedia.org/wiki/X", "category": ""})
    assert response.status_code == 400
    assert b"English Wikipedia" in response.data


def test_unknown_article(client):
    response = client.post("/submit", data={"url": "https://en.wikipedia.org/wiki/Nope"})
    assert response.status_code == 400
    assert b"does not exist" in response.data


def test_preview_shows_extracted_data_and_suggested_tags(client, wiki):
    wiki.add("Battle of Hastings")
    response = client.post("/submit", data={"url": URL, "category": "military"})
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'value="Battle of Hastings"' in html
    assert "Matching the year" in html
    assert "Norman Conquest of England" in html


def test_preview_warns_about_missing_year(client, wiki):
    wiki.add("Battle of Hastings", year=None)
    html = client.post("/submit", data={"url": URL}).get_data(as_text=True)
    assert "could not find a year" in html


def test_submission_is_pending_until_approved(client, wiki, app):
    wiki.add("Battle of Hastings")
    tag = db.session.scalar(db.select(Tag).filter_by(name="Norman Conquest of England"))
    response = client.post("/submit/confirm", data={**form_data(), "tags": [str(tag.id)]})
    assert response.status_code == 200
    assert b"Thank you" in response.data

    event = db.session.scalar(db.select(Event))
    assert event.status == Status.PENDING
    assert event.modified is False
    assert [t.name for t in event.tags] == ["Norman Conquest of England"]
    assert client.get("/api/events").json == []


def test_edited_submission_is_flagged(client, wiki):
    wiki.add("Battle of Hastings")
    client.post("/submit/confirm", data=form_data(year="44 BC"))
    event = db.session.scalar(db.select(Event))
    assert event.year == -44
    assert event.modified is True


def test_invalid_fields_are_reported(client, wiki):
    wiki.add("Battle of Hastings")
    response = client.post("/submit/confirm", data=form_data(year="soon", lat="200", title=""))
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "Enter a year" in html
    assert db.session.scalar(db.select(db.func.count(Event.id))) == 0


def test_duplicate_submission(client, wiki, make_event):
    wiki.add("Battle of Hastings")
    existing = make_event()
    response = client.post("/submit", data={"url": URL})
    assert response.status_code == 409
    assert f"/?event={existing.id}".encode() in response.data


def test_duplicate_detected_through_url_variants(client, wiki, make_event):
    wiki.add("Battle of Hastings")
    make_event()
    response = client.post("/submit", data={"url": "https://en.m.wikipedia.org/wiki/Battle_of_Hastings#Aftermath"})
    assert response.status_code == 409


def test_html_in_submissions_is_escaped(client, wiki):
    wiki.add("Battle of Hastings")
    client.post("/submit/confirm", data=form_data(title="<script>alert(1)</script>"))
    db.session.scalar(db.select(Event)).status = Status.APPROVED
    db.session.commit()
    # Stored verbatim, delivered as JSON; the map renders it with textContent.
    assert client.get("/api/events").json[0]["title"] == "<script>alert(1)</script>"
