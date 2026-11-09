"""The manage page's list editing: remove (one or many), reorder, move – as fetch() and as plain forms."""

import pytest

from haam.extensions import db
from haam.models import Collection, Tag

from tests.test_collections import create, custom

JSON = {"Accept": "application/json"}


@pytest.fixture
def five(client):
    """A collection (editable by ``client``) with five custom entries A–E, in that order."""
    collection, _ = create(client)
    for title in "ABCDE":
        client.post(f"/collections/{collection.view_token}/entries/custom", data=custom(title=title))
    return collection


def titles(collection):
    db.session.expire_all()
    collection = db.session.get(Collection, collection.id)
    assert [e.position for e in collection.entries] == list(range(len(collection.entries)))
    return "".join(e.title for e in collection.entries)


def ids(collection, letters):
    by_title = {e.title: e.id for e in collection.entries}
    return [by_title[letter] for letter in letters]


@pytest.fixture
def stranger(app):
    return app.test_client()


# ------------------------------------------------------------ remove

def test_remove_one_entry_with_fetch_returns_json(client, five):
    base = f"/collections/{five.view_token}"
    entry_id = ids(five, "B")[0]
    response = client.post(f"{base}/entries/{entry_id}/delete", headers=JSON)
    assert response.status_code == 200
    assert response.get_json() == {"message": "Removed “B”.", "count": 4, "removed": [entry_id]}
    assert titles(five) == "ACDE"


def test_remove_one_entry_without_javascript_jumps_back_to_the_next(client, five):
    entry_b, entry_c = ids(five, "BC")
    response = client.post(f"/collections/{five.view_token}/entries/{entry_b}/delete")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/manage#entry-{entry_c}")
    assert titles(five) == "ACDE"


def test_remove_several_entries(client, five):
    base = f"/collections/{five.view_token}"
    response = client.post(f"{base}/entries/remove", data={"entry_id": ids(five, "ACE")}, headers=JSON)
    assert response.status_code == 200
    assert response.get_json()["message"] == "Removed 3 entries."
    assert response.get_json()["count"] == 2
    assert titles(five) == "BD"

    # The plain form (no JavaScript) does the same and redirects.
    response = client.post(f"{base}/entries/remove", data={"entry_id": ids(five, "D")})
    assert response.status_code == 302
    assert titles(five) == "B"


def test_remove_needs_a_selection_and_ignores_other_collections(client, five):
    other, _ = create(client, title="Other")
    client.post(f"/collections/{other.view_token}/entries/custom", data=custom(title="Z"))
    foreign = other.entries[0].id
    base = f"/collections/{five.view_token}"
    assert client.post(f"{base}/entries/remove", headers=JSON).status_code == 400
    response = client.post(f"{base}/entries/remove", data={"entry_id": [foreign]}, headers=JSON)
    assert response.status_code == 400
    assert titles(five) == "ABCDE" and titles(other) == "Z"
    assert client.post(f"{base}/entries/{foreign}/delete", headers=JSON).status_code == 404


# ------------------------------------------------------------ order

def test_reorder_saves_positions_and_the_view_uses_them(client, five):
    base = f"/collections/{five.view_token}"
    response = client.post(f"{base}/entries/order", data={"entry_id": ids(five, "EBDAC")}, headers=JSON)
    assert response.status_code == 200
    assert titles(five) == "EBDAC"

    # The collection page, its map data and the full map all list the entries in that order.
    page = client.get(base).get_data(as_text=True)
    assert [page.index(f'"title": "{t}"') for t in "EBDAC"] == sorted(page.index(f'"title": "{t}"') for t in "EBDAC")
    assert [e["title"] for e in client.get(f"{base}/map.json").get_json()] == list("EBDAC")


def test_reorder_must_list_every_entry_once(client, five):
    base = f"/collections/{five.view_token}"
    for order in ("EBDA", "EBDACC", "EBDAA"):
        response = client.post(f"{base}/entries/order", data={"entry_id": ids(five, order)}, headers=JSON)
        assert response.status_code == 409
        assert "reload" in response.get_json()["error"]
    assert titles(five) == "ABCDE"


def test_move_up_and_down(client, five):
    base = f"/collections/{five.view_token}"
    entry_c = ids(five, "C")[0]
    response = client.post(f"{base}/entries/{entry_c}/move", data={"direction": "up"}, headers=JSON)
    assert response.get_json()["position"] == 1
    assert titles(five) == "ACBDE"

    # Without JavaScript: a redirect back to the moved entry.
    response = client.post(f"{base}/entries/{entry_c}/move", data={"direction": "up"})
    assert response.headers["Location"].endswith(f"#entry-{entry_c}")
    assert titles(five) == "CABDE"

    # Already first: nothing changes. A bad direction is refused.
    client.post(f"{base}/entries/{entry_c}/move", data={"direction": "up"})
    assert titles(five) == "CABDE"
    assert client.post(f"{base}/entries/{entry_c}/move", data={"direction": "sideways"},
                       headers=JSON).status_code == 400
    client.post(f"{base}/entries/{entry_c}/move", data={"direction": "down"})
    assert titles(five) == "ACBDE"


def test_new_entries_go_to_the_end_after_a_reorder(client, five):
    base = f"/collections/{five.view_token}"
    client.post(f"{base}/entries/order", data={"entry_id": ids(five, "EDCBA")})
    client.post(f"{base}/entries/custom", data=custom(title="F"))
    assert titles(five) == "EDCBAF"


# ------------------------------------------------------------ access

@pytest.mark.parametrize("path, data", [
    ("entries/remove", {"entry_id": "B"}),
    ("entries/order", {"entry_id": "EDCBA"}),
    ("entries/{B}/delete", {}),
    ("entries/{B}/move", {"direction": "up"}),
])
def test_editing_needs_edit_access(stranger, five, path, data):
    entry_b = ids(five, "B")[0]
    url = f"/collections/{five.view_token}/" + path.replace("{B}", str(entry_b))
    data = {key: (ids(five, value) if key == "entry_id" else value) for key, value in data.items()}

    response = stranger.post(url, data=data, headers=JSON)
    assert response.status_code == 403
    assert "edit link" in response.get_json()["error"]
    # A plain form submission is sent to the read-only page instead.
    response = stranger.post(url, data=data)
    assert response.status_code == 302
    assert response.headers["Location"] == f"/collections/{five.view_token}"
    assert titles(five) == "ABCDE"


def test_editing_needs_the_csrf_token(app, client, five):
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        base = f"/collections/{five.view_token}"
        assert client.post(f"{base}/entries/remove", data={"entry_id": ids(five, "A")},
                           headers=JSON).status_code == 400
        assert client.post(f"{base}/entries/order", data={"entry_id": ids(five, "EDCBA")},
                           headers=JSON).status_code == 400
        assert titles(five) == "ABCDE"
    finally:
        app.config["WTF_CSRF_ENABLED"] = False


# ------------------------------------------------------------ page

def test_manage_page_puts_the_forms_before_the_entries(client, five):
    html = client.get(f"/collections/{five.view_token}/manage").get_data(as_text=True)
    assert html.index('id="add-event"') < html.index('id="settings"') < html.index('id="entries"')
    assert html.count('name="entry_id"') == 5
    assert 'id="entry-actions"' in html and "data-entries-filter" in html


def test_tag_choices_skip_empty_tags_and_count_correctly(client, make_event):
    tag = Tag(name="Space Race", start_year=1955, end_year=1975)
    db.session.add(tag)
    db.session.commit()
    make_event(title="Sputnik 1", year=1957, tags=[tag])

    html = client.get("/collections/new").get_data(as_text=True)
    assert "Space Race (1955 – 1975) – 1 event<" in html
    assert 'data-name="Space Race"' in html and 'data-count="1"' in html and "data-tag-combobox" in html
    assert "World War II" not in html  # a tag of the fixtures without events
