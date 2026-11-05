import re

import pytest

from haam.extensions import db
from haam.models import Collection, CollectionEntry, Event, Status


def create(client, title="Roman battles", public=True, description="Wars of Rome."):
    data = {"title": title, "description": description}
    if public:
        data["is_public"] = "y"
    response = client.post("/collections/new", data=data)
    assert response.status_code == 302
    collection = db.session.scalar(db.select(Collection).filter_by(title=title))
    return collection, response


def edit_link(client, collection):
    html = client.get(f"/collections/{collection.view_token}/manage").get_data(as_text=True)
    return re.search(r'id="edit-url"[^>]*value="([^"]+)"', html).group(1)


def custom(**overrides):
    data = {"title": "My grandfather's village", "year": "1944", "date_label": "", "category": "other",
            "lat": "45.5", "lon": "9.2", "summary": "Where he was born.", "link": "", "note": "Family history"}
    data.update(overrides)
    return data


# ------------------------------------------------------------- creating

def test_create_gives_share_and_edit_links(client):
    collection, response = create(client)
    assert response.headers["Location"] == f"/collections/{collection.view_token}/manage"
    link = edit_link(client, collection)
    assert f"/collections/{collection.view_token}/edit/" in link
    token = link.rsplit("/", 1)[1]
    assert token not in collection.edit_token_hash  # only the hash is stored
    assert len(collection.edit_token_hash) == 64


def test_title_is_required(client):
    response = client.post("/collections/new", data={"title": ""})
    assert response.status_code == 400


# --------------------------------------------------------------- access

def test_other_browsers_cannot_edit(app, client):
    collection, _ = create(client)
    link = edit_link(client, collection)
    stranger = app.test_client()

    assert stranger.get(f"/collections/{collection.view_token}").status_code == 200
    assert stranger.get(f"/collections/{collection.view_token}/manage").status_code == 302
    response = stranger.post(f"/collections/{collection.view_token}/entries/custom", data=custom())
    assert response.status_code == 302
    assert db.session.scalar(db.select(db.func.count(CollectionEntry.id))) == 0

    # The edit link grants access in the new browser too.
    path = link.split("localhost", 1)[1]
    assert stranger.get(path).status_code == 302
    assert stranger.get(f"/collections/{collection.view_token}/manage").status_code == 200


def test_wrong_edit_token_is_404(client, app):
    collection, _ = create(client)
    assert app.test_client().get(f"/collections/{collection.view_token}/edit/wrong").status_code == 404


def test_forget_removes_edit_access(client):
    collection, _ = create(client)
    client.post(f"/collections/{collection.view_token}/forget")
    assert client.get(f"/collections/{collection.view_token}/manage").status_code == 302


def test_admin_login_keeps_collection_access(client):
    from tests.conftest import ADMIN_PASSWORD

    collection, _ = create(client)
    client.post("/admin/login", data={"username": "admin", "password": ADMIN_PASSWORD})
    client.post("/admin/logout")
    assert client.get(f"/collections/{collection.view_token}/manage").status_code == 200


def test_collection_pages_are_not_indexed(client):
    collection, _ = create(client)
    response = client.get(f"/collections/{collection.view_token}")
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert response.headers["Referrer-Policy"] == "no-referrer"


# -------------------------------------------------------------- entries

def test_add_custom_entry(client):
    collection, _ = create(client)
    response = client.post(f"/collections/{collection.view_token}/entries/custom", data=custom(year="44 BC"))
    assert response.status_code == 302
    entry = collection.entries[0]
    assert (entry.title, entry.year, entry.lat, entry.note) == ("My grandfather's village", -44, 45.5, "Family history")
    assert not entry.is_event and not entry.has_wikipedia
    # Custom entries never reach the main map.
    assert client.get("/api/events").json == []


def test_custom_entry_with_wikipedia_link_gets_star(client, wiki):
    wiki.add("Battle of Hastings")
    collection, _ = create(client)
    client.post(f"/collections/{collection.view_token}/entries/custom",
                data=custom(link="https://en.m.wikipedia.org/wiki/Battle_of_Hastings#Battle"))
    entry = collection.entries[0]
    assert entry.wiki_verified and entry.has_wikipedia
    assert entry.link == "https://en.wikipedia.org/wiki/Battle_of_Hastings"


def test_missing_or_non_wikipedia_links_get_no_star(client):
    collection, _ = create(client)
    client.post(f"/collections/{collection.view_token}/entries/custom",
                data=custom(link="https://en.wikipedia.org/wiki/Does_not_exist"))
    client.post(f"/collections/{collection.view_token}/entries/custom",
                data=custom(title="Blog", link="https://example.com/post"))
    assert [e.wiki_verified for e in collection.entries] == [False, False]
    assert collection.entries[1].link == "https://example.com/post"


@pytest.mark.parametrize("bad", [{"link": "javascript:alert(1)"}, {"lat": ""}, {"lat": "95"}, {"year": "soon"}, {"title": ""}])
def test_custom_entry_validation(client, bad):
    collection, _ = create(client)
    response = client.post(f"/collections/{collection.view_token}/entries/custom", data=custom(**bad))
    assert response.status_code == 400
    assert collection.entries == []


def test_add_main_map_event(client, make_event):
    event = make_event()
    collection, _ = create(client)
    url = f"/collections/{collection.view_token}/entries/event"
    assert client.post(url, data={"event_id": event.id, "note": "Classic"}).status_code == 302
    entry = collection.entries[0]
    assert entry.is_event and entry.is_confirmed and entry.has_wikipedia
    assert (entry.title, entry.note) == ("Battle of Hastings", "Classic")

    # Not twice, and never pending events.
    assert client.post(url, data={"event_id": event.id}).status_code == 400
    pending = make_event(title="Pending battle", status=Status.PENDING)
    assert client.post(url, data={"event_id": pending.id}).status_code == 400
    assert len(collection.entries) == 1


def test_edit_and_remove_entries(client, make_event):
    event = make_event()
    collection, _ = create(client)
    base = f"/collections/{collection.view_token}"
    client.post(f"{base}/entries/event", data={"event_id": event.id})
    client.post(f"{base}/entries/custom", data=custom())
    event_entry, custom_entry = collection.entries

    assert client.get(f"{base}/entries/{event_entry.id}/edit").status_code == 200
    client.post(f"{base}/entries/{event_entry.id}/edit", data={"note": "Changed note"})
    client.post(f"{base}/entries/{custom_entry.id}/edit", data=custom(title="Renamed", lon="10"))
    db.session.refresh(event_entry)
    db.session.refresh(custom_entry)
    assert event_entry.note == "Changed note"
    assert (custom_entry.title, custom_entry.lon) == ("Renamed", 10.0)

    client.post(f"{base}/entries/{event_entry.id}/delete")
    db.session.refresh(collection)
    assert [e.title for e in collection.entries] == ["Renamed"]
    assert collection.entries[0].position == 0


def test_entries_of_other_collections_are_404(client):
    first, _ = create(client, title="First")
    second, _ = create(client, title="Second")
    client.post(f"/collections/{first.view_token}/entries/custom", data=custom())
    entry_id = first.entries[0].id
    assert client.get(f"/collections/{second.view_token}/entries/{entry_id}/edit").status_code == 404


def test_deleting_an_event_removes_it_from_collections(client, make_event, admin_client):
    event = make_event()
    collection, _ = create(client)
    client.post(f"/collections/{collection.view_token}/entries/event", data={"event_id": event.id})
    admin_client.post(f"/admin/events/{event.id}/delete")
    db.session.expire_all()
    assert db.session.get(Event, event.id) is None
    assert db.session.get(Collection, collection.id).entries == []


# --------------------------------------------------------------- badges

def test_collection_badges(client, wiki, make_event):
    wiki.add("Battle of Hastings")
    event = make_event(title="Battle of Waterloo")
    collection, _ = create(client)
    base = f"/collections/{collection.view_token}"
    assert not collection.all_wikipedia and not collection.all_confirmed  # empty

    client.post(f"{base}/entries/event", data={"event_id": event.id})
    assert collection.all_wikipedia and collection.all_confirmed

    client.post(f"{base}/entries/custom", data=custom(link="https://en.wikipedia.org/wiki/Battle_of_Hastings"))
    assert collection.all_wikipedia and not collection.all_confirmed

    client.post(f"{base}/entries/custom", data=custom(title="No source"))
    assert not collection.all_wikipedia

    html = client.get(base).get_data(as_text=True)
    assert html.count("Backed by a Wikipedia article") == 2
    assert "Confirmed event from the main map" in html


# -------------------------------------------------------------- gallery

def test_gallery_lists_public_collections_with_entries(app, client):
    public, _ = create(client, title="Public one")
    create(client, title="Unlisted one", public=False)
    create(client, title="Empty public")
    client.post(f"/collections/{public.view_token}/entries/custom", data=custom())

    html = app.test_client().get("/collections/").get_data(as_text=True)
    assert "Public one" in html
    assert "Unlisted one" not in html and "Empty public" not in html
    # The creator also sees their own collections.
    own = client.get("/collections/").get_data(as_text=True)
    assert "Your collections" in own and "Unlisted one" in own


def test_user_text_is_escaped(client):
    collection, _ = create(client, title="<script>alert(1)</script>")
    client.post(f"/collections/{collection.view_token}/entries/custom", data=custom(note="</script><b>x</b>"))
    html = client.get(f"/collections/{collection.view_token}").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "</script><b>" not in html


# ------------------------------------------------------ reports & admin

def test_report_and_moderation(app, client, admin_client):
    collection, _ = create(client)
    client.post(f"/collections/{collection.view_token}/entries/custom", data=custom())
    visitor = app.test_client()
    visitor.post(f"/collections/{collection.view_token}/report", data={"reason": "Spam"})
    assert [r.reason for r in collection.reports] == ["Spam"]

    html = admin_client.get("/admin/collections").get_data(as_text=True)
    assert "1 report" in html and "Spam" in html

    admin_client.post(f"/admin/collections/{collection.id}/hide")
    assert visitor.get(f"/collections/{collection.view_token}").status_code == 410
    assert "Roman battles" not in visitor.get("/collections/").get_data(as_text=True)
    assert client.get(f"/collections/{collection.view_token}").status_code == 200  # owner still sees it

    admin_client.post(f"/admin/collections/{collection.id}/unhide")
    assert collection.reports == []
    admin_client.post(f"/admin/collections/{collection.id}/delete")
    assert db.session.get(Collection, collection.id) is None


def test_admin_collections_need_login(client):
    assert client.get("/admin/collections").status_code == 302


def test_owner_can_delete_collection(client):
    collection, _ = create(client)
    client.post(f"/collections/{collection.view_token}/entries/custom", data=custom())
    assert client.post(f"/collections/{collection.view_token}/delete").status_code == 302
    assert db.session.scalar(db.select(db.func.count(Collection.id))) == 0
    assert db.session.scalar(db.select(db.func.count(CollectionEntry.id))) == 0
