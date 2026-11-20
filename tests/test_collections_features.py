"""Collections: query counts, compact cookies, copying, suggestions and the links email."""

import re
from contextlib import contextmanager

import pytest
from sqlalchemy import event as sa_event

from haam import collections_service as service
from haam import mail
from haam.extensions import db
from haam.models import Collection, CollectionEntry, CollectionSuggestion, Tag


def create(client, title="Roman battles", public=True, **extra):
    data = {"title": title, "description": "Wars of Rome.", **extra}
    if public:
        data["is_public"] = "y"
    response = client.post("/collections/new", data=data)
    assert response.status_code == 302
    return db.session.scalar(db.select(Collection).filter_by(title=title))


def edit_url(client, collection):
    html = client.get(f"/collections/{collection.view_token}/manage").get_data(as_text=True)
    found = re.search(r'id="edit-url"[^>]*value="([^"]+)"', html)
    return found.group(1) if found else None


@contextmanager
def count_queries():
    statements = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = db.engine
    sa_event.listen(engine, "before_cursor_execute", listener)
    try:
        yield statements
    finally:
        sa_event.remove(engine, "before_cursor_execute", listener)


# ------------------------------------------------------------------ B1: queries

@pytest.fixture
def big_collection(app, make_event):
    tag = db.session.scalar(db.select(Tag).filter_by(name="World War II"))
    collection, _ = service.create_collection("Sixty", "Many entries.", True)
    for i in range(60):
        event = make_event(f"Event {i}", year=1900 + i)
        event.tags.append(tag)
        collection.entries.append(CollectionEntry(event=event, note=f"note {i}", position=i))
    collection.entries.append(CollectionEntry(custom_title="Mine", custom_year=1950, custom_lat=1.0,
                                              custom_lon=2.0, position=60))
    db.session.commit()
    return collection


@pytest.mark.parametrize("path", ["", "/map", "/map.json"])
def test_collection_pages_use_few_queries(client, big_collection, path):
    with count_queries() as statements:
        response = client.get(f"/collections/{big_collection.view_token}{path}")
    assert response.status_code == 200
    assert len(statements) < 10, statements


def test_collection_index_uses_few_queries(client, big_collection):
    with count_queries() as statements:
        response = client.get("/collections/")
    assert response.status_code == 200 and b"Sixty" in response.data
    assert len(statements) < 10, statements


def test_featured_collections_use_few_queries(app, big_collection):
    from haam import welcome

    if hasattr(Collection, "is_featured"):  # featuring became an editor's choice
        big_collection.is_featured = True
        db.session.commit()
    with count_queries() as statements:
        featured = welcome.featured_collections()
        assert featured[0][0].year_span and not featured[0][0].all_wikipedia  # the custom entry has no article
    assert len(statements) < 10, statements


def test_admin_collections_are_paginated(admin_client, app):
    for i in range(25):
        service.create_collection(f"Collection {i:02d}", "", True)
    first = admin_client.get("/admin/collections").get_data(as_text=True)
    assert first.count('class="card review-card"') == 20 and "Page 1 of 2" in first
    second = admin_client.get("/admin/collections?page=2").get_data(as_text=True)
    assert second.count('class="card review-card"') == 5


# ------------------------------------------------------------------ B14: cookie

def test_cookie_holds_a_proof_not_the_token(client):
    collection = create(client)
    link = edit_url(client, collection)
    token = link.rsplit("/", 1)[1]
    with client.session_transaction() as session:
        stored = session["collections"][str(collection.id)]
        assert token not in str(dict(session)) or "fresh_edit_tokens" in session
    assert token not in stored and stored.startswith("~") and len(stored) < 30
    # The one-time token is gone after the first manage page.
    with client.session_transaction() as session:
        assert "fresh_edit_tokens" not in session
        assert token not in str(dict(session))


def test_edit_link_is_shown_only_once(client):
    collection = create(client)
    assert edit_url(client, collection) is not None
    html = client.get(f"/collections/{collection.view_token}/manage").get_data(as_text=True)
    assert 'id="edit-url"' not in html and "shown only once" in html
    assert client.get(f"/collections/{collection.view_token}/manage").status_code == 200  # still editable


def test_claim_shows_the_link_once_and_edits(client, app):
    collection = create(client)
    link = edit_url(client, collection)
    other = app.test_client()
    assert other.get(f"/collections/{collection.view_token}/manage").status_code == 302
    other.get(link)
    assert edit_url(other, collection) == link
    assert edit_url(other, collection) is None
    assert other.get(f"/collections/{collection.view_token}/manage").status_code == 200


def test_old_cookie_with_raw_token_still_works_and_is_upgraded(client, app):
    collection = create(client)
    token = edit_url(client, collection).rsplit("/", 1)[1]
    other = app.test_client()
    with other.session_transaction() as session:
        session["collections"] = {str(collection.id): token}
    assert other.get(f"/collections/{collection.view_token}/manage").status_code == 200
    with other.session_transaction() as session:
        assert session["collections"][str(collection.id)].startswith("~")
        assert token not in str(dict(session))


def test_forged_or_wrong_cookie_is_refused(client, app):
    collection = create(client)
    other = app.test_client()
    for value in ("~" + "0" * 22, "wrong-token", "", 5):
        with other.session_transaction() as session:
            session["collections"] = {str(collection.id): value}
        assert other.get(f"/collections/{collection.view_token}/manage").status_code == 302
    # A proof for one collection does not work for another.
    second = create(client, "Second")
    with client.session_transaction() as session:
        proof = session["collections"][str(second.id)]
    with other.session_transaction() as session:
        session["collections"] = {str(collection.id): proof}
    assert other.get(f"/collections/{collection.view_token}/manage").status_code == 302


def test_many_collections_keep_the_cookie_small(client):
    for i in range(40):
        create(client, f"Collection {i}")
    with client.session_transaction() as session:
        assert len(str(dict(session["collections"]))) < 1800


# ------------------------------------------------------------------ copy

def test_copy_collection(client, app, make_event):
    event = make_event("Battle A")
    collection = create(client, "Original")
    service.add_event(collection, event.id, "my note")
    service.add_custom(collection, service.CustomEntryData(
        title="Village", year=1944, date_label="", category=service.Category.OTHER, lat=1.5, lon=2.5,
        summary="Where he lived", link="", note="family"))
    service.move_entry(collection.entries[0], 10.0, 20.0)

    visitor = app.test_client()
    response = visitor.post(f"/collections/{collection.view_token}/copy")
    assert response.status_code == 302
    copy = db.session.scalar(db.select(Collection).filter(Collection.id != collection.id))
    assert response.headers["Location"] == f"/collections/{copy.view_token}/manage"
    assert copy.view_token != collection.view_token and copy.edit_token_hash != collection.edit_token_hash
    assert copy.is_public is False and copy.title == "Original (copy)"
    assert [(e.event_id, e.note, e.custom_title, e.position) for e in copy.entries] == \
           [(event.id, "my note", None, 0), (None, "family", "Village", 1)]
    assert (copy.entries[0].custom_lat, copy.entries[0].custom_lon) == (10.0, 20.0)
    assert copy.entries[1].custom_year == 1944
    # The visitor can edit the copy (and sees the edit link once), but not the original.
    assert edit_url(visitor, copy) is not None
    assert visitor.get(f"/collections/{copy.view_token}/manage").status_code == 200
    assert visitor.get(f"/collections/{collection.view_token}/manage").status_code == 302
    # The original is untouched and the entries are separate rows.
    assert len(collection.entries) == 2 and {e.id for e in copy.entries}.isdisjoint({e.id for e in collection.entries})


def test_copy_button_on_view_page_and_hidden_collections(client, app):
    collection = create(client)
    html = app.test_client().get(f"/collections/{collection.view_token}").get_data(as_text=True)
    assert "Use as a base for my own collection" in html
    collection.is_hidden = True
    db.session.commit()
    assert app.test_client().post(f"/collections/{collection.view_token}/copy").status_code == 410


# ------------------------------------------------------------------ suggestions

def test_suggest_event_and_accept(client, app, make_event):
    event = make_event("Battle B")
    collection = create(client)
    visitor = app.test_client()
    page = visitor.get(f"/collections/{collection.view_token}").get_data(as_text=True)
    assert "Suggest an entry" in page and "data-event-picker" in page
    response = visitor.post(f"/collections/{collection.view_token}/suggest",
                            data={"event_id": event.id, "message": "Please add"})
    assert response.status_code == 302
    suggestion = db.session.scalar(db.select(CollectionSuggestion))
    assert suggestion.event_id == event.id and suggestion.message == "Please add"
    # Visitors cannot decide.
    assert visitor.post(f"/collections/{collection.view_token}/suggestions/{suggestion.id}/accept"
                        ).status_code == 302
    assert db.session.get(CollectionSuggestion, suggestion.id) is not None

    html = client.get(f"/collections/{collection.view_token}/manage").get_data(as_text=True)
    assert "Suggestions (1)" in html and "Battle B" in html and "Please add" in html
    client.post(f"/collections/{collection.view_token}/suggestions/{suggestion.id}/accept")
    db.session.expire_all()
    assert [e.event_id for e in collection.entries] == [event.id]
    assert collection.entries[0].note == "Please add"
    assert db.session.scalar(db.select(CollectionSuggestion)) is None


def test_suggest_free_text_opens_prefilled_form_and_clears_it(client, app):
    collection = create(client)
    app.test_client().post(f"/collections/{collection.view_token}/suggest",
                           data={"title": "Siege of Vienna", "link": "https://example.org/x", "message": "1683"})
    suggestion = db.session.scalar(db.select(CollectionSuggestion))
    assert suggestion.event_id is None and suggestion.title == "Siege of Vienna"
    response = client.post(f"/collections/{collection.view_token}/suggestions/{suggestion.id}/accept")
    assert f"suggestion={suggestion.id}" in response.headers["Location"]
    html = client.get(f"/collections/{collection.view_token}/manage?suggestion={suggestion.id}").get_data(as_text=True)
    assert 'value="Siege of Vienna"' in html and "https://example.org/x" in html
    assert f'name="suggestion_id" value="{suggestion.id}"' in html
    client.post(f"/collections/{collection.view_token}/entries/custom", data={
        "title": "Siege of Vienna", "year": "1683", "category": "military", "lat": "48.2", "lon": "16.4",
        "link": "", "note": "1683", "suggestion_id": suggestion.id})
    db.session.expire_all()
    assert [e.custom_title for e in collection.entries] == ["Siege of Vienna"]
    assert db.session.scalar(db.select(CollectionSuggestion)) is None


def test_dismiss_suggestion(client, app):
    collection = create(client)
    app.test_client().post(f"/collections/{collection.view_token}/suggest", data={"title": "Spam"})
    suggestion = db.session.scalar(db.select(CollectionSuggestion))
    client.post(f"/collections/{collection.view_token}/suggestions/{suggestion.id}/dismiss")
    assert db.session.scalar(db.select(CollectionSuggestion)) is None
    assert len(collection.entries) == 0


def test_suggestion_validation(client, app, make_event):
    from haam.models import Status

    pending = make_event("Pending", status=Status.PENDING)
    present = make_event("Present")
    collection = create(client)
    service.add_event(collection, present.id, "")
    visitor = app.test_client()
    url = f"/collections/{collection.view_token}/suggest"
    visitor.post(url, data={"message": "nothing chosen"})  # neither event nor title
    visitor.post(url, data={"event_id": pending.id})  # not on the main map
    visitor.post(url, data={"event_id": present.id})  # already in the collection
    visitor.post(url, data={"event_id": 99999})
    visitor.post(url, data={"title": "x", "link": "javascript:alert(1)"})
    assert db.session.scalar(db.select(CollectionSuggestion)) is None


def test_suggestions_are_capped_at_50(client, app):
    collection = create(client)
    visitor = app.test_client()
    for i in range(55):
        visitor.post(f"/collections/{collection.view_token}/suggest", data={"title": f"Idea {i}"})
    assert db.session.scalar(db.select(db.func.count(CollectionSuggestion.id))) == 50


def test_suggestions_are_deleted_with_the_collection(client):
    collection = create(client)
    service.suggest(collection, None, "Idea", "", "")
    service.delete_collection(collection)
    assert db.session.scalar(db.select(db.func.count(CollectionSuggestion.id))) == 0


def test_only_the_owner_decides_on_their_own_collections_suggestions(client, app):
    first, second = create(client, "One"), create(client, "Two")
    service.suggest(first, None, "Idea", "", "")
    suggestion = db.session.scalar(db.select(CollectionSuggestion))
    # Right to edit "Two", but the suggestion belongs to "One".
    assert client.post(f"/collections/{second.view_token}/suggestions/{suggestion.id}/dismiss").status_code == 404


# ------------------------------------------------------------------ email

@pytest.fixture
def smtp(app, monkeypatch):
    app.config.update(SMTP_HOST="smtp.test", MAIL_FROM="haam@test.example")
    sent = []
    monkeypatch.setattr(mail, "send_links", lambda *args: sent.append(args))
    return sent


def test_email_field_hidden_without_smtp(client):
    html = client.get("/collections/new").get_data(as_text=True)
    assert 'name="email"' not in html


def test_email_field_shown_with_smtp(client, smtp):
    assert 'name="email"' in client.get("/collections/new").get_data(as_text=True)


def test_links_are_emailed_once_and_not_stored(client, smtp):
    response = client.post("/collections/new", data={"title": "Mailed", "email": "me@example.org"})
    assert response.status_code == 302
    collection = db.session.scalar(db.select(Collection))
    [(to, title, share, edit)] = smtp
    assert to == "me@example.org" and title == "Mailed"
    assert share.endswith(f"/collections/{collection.view_token}")
    assert f"/collections/{collection.view_token}/edit/" in edit
    assert service.check_edit_token(collection, edit.rsplit("/", 1)[1])
    assert "me@example.org" not in str([getattr(collection, c.name) for c in Collection.__table__.columns])
    page = client.get(f"/collections/{collection.view_token}/manage").get_data(as_text=True)
    assert "We emailed you" in page


def test_no_email_when_field_empty_or_smtp_missing(client, app, monkeypatch):
    calls = []
    monkeypatch.setattr(mail, "send_links", lambda *args: calls.append(args))
    client.post("/collections/new", data={"title": "No mail", "email": "me@example.org"})  # no SMTP
    app.config.update(SMTP_HOST="smtp.test", MAIL_FROM="a@b.example")
    client.post("/collections/new", data={"title": "Empty"})
    assert calls == []


def test_invalid_email_is_rejected(client, smtp):
    response = client.post("/collections/new", data={"title": "Bad", "email": "not an address"})
    assert response.status_code == 400 and not smtp
    assert db.session.scalar(db.select(Collection)) is None


def test_send_failure_does_not_break_creation(client, app, monkeypatch):
    app.config.update(SMTP_HOST="smtp.test", MAIL_FROM="a@b.example")

    def boom(*args):
        raise mail.MailError("connection refused")

    monkeypatch.setattr(mail, "send_links", boom)
    response = client.post("/collections/new", data={"title": "Survives", "email": "me@example.org"})
    assert response.status_code == 302
    assert db.session.scalar(db.select(Collection).filter_by(title="Survives")) is not None
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "could not send the email" in page and 'id="edit-url"' in page


def test_smtp_send_uses_starttls_and_login(app, monkeypatch):
    app.config.update(SMTP_HOST="smtp.test", SMTP_PORT=587, SMTP_USERNAME="user", SMTP_PASSWORD="pw",
                      MAIL_FROM="haam@test.example")
    events = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            events.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, context=None):
            events.append(("starttls",))

        def login(self, user, password):
            events.append(("login", user, password))

        def send_message(self, message):
            events.append(("send", message["To"], message["From"], message.get_content()))

    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    mail.send_links("me@example.org", "Mine", "https://h/collections/v", "https://h/collections/v/edit/t")
    assert [e[0] for e in events] == ["connect", "starttls", "login", "send"]
    assert "https://h/collections/v/edit/t" in events[-1][3] and events[-1][1] == "me@example.org"


# ------------------------------------------------------------------ abuse limits

def test_copy_and_suggest_are_rate_limited(client, app):
    app.config["RATELIMIT_ENABLED"] = True
    collection = create(client)
    visitor = app.test_client()
    for _ in range(10):
        assert visitor.post(f"/collections/{collection.view_token}/copy").status_code == 302
    assert visitor.post(f"/collections/{collection.view_token}/copy").status_code == 429
    for _ in range(10):
        visitor.post(f"/collections/{collection.view_token}/suggest", data={"title": "A thing"})
    assert visitor.post(f"/collections/{collection.view_token}/suggest",
                        data={"title": "A thing"}).status_code == 429


def test_session_remembers_a_bounded_number_of_collections(client, app):
    from haam import collections_service as service

    first = create(client, title="First")
    with client.session_transaction() as session:
        assert str(first.id) in session[service.SESSION_KEY]
    for number in range(service.MAX_REMEMBERED):
        create(client, title=f"Extra {number}")
    with client.session_transaction() as session:
        owned = session[service.SESSION_KEY]
    assert len(owned) == service.MAX_REMEMBERED
    assert str(first.id) not in owned
    cookie = next(c for c in client._cookies.values() if c.key == "session")  # werkzeug test cookie jar
    assert len(cookie.value) < 3500  # well under the ~4 KB browser limit
