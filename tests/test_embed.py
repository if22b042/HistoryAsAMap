"""The embeddable map (/embed), the shareable-view script rules and the add-event warning."""

from pathlib import Path

from haam import create_app
from tests.test_submission import URL, form_data

STATIC_JS = Path(create_app("testing").static_folder) / "js"


def test_embed_is_the_map_without_the_site_around_it(client, make_event):
    page = client.get("/embed").get_data(as_text=True)
    assert 'id="map"' in page and 'id="year-slider"' in page and 'id="sidebar"' in page
    assert 'data-manifest=' in page
    assert 'class="page-map page-embed filters-hidden"' in page
    for gone in ('class="navbar"', 'class="footer"', 'id="welcome"', 'id="near"', 'id="near-open"',
                 'welcome.js', 'data-collections-url', 'data-collection-from-search', 'id="embed-view"',
                 'class="scroll-to-list'):
        assert gone not in page, gone
    # The list below the map is not shown; the link back to the full site is.
    assert '<section class="events-section" id="events" hidden>' in page
    assert 'id="embed-brand" href="/"' in page
    assert '<meta name="robots" content="noindex">' in page
    assert 'rel="canonical"' not in page


def test_embed_link_back_keeps_the_query_string(client):
    page = client.get("/embed?tag=3&q=battle&view=5/48.2/16.4&event=7001").get_data(as_text=True)
    assert 'id="embed-brand" href="/?tag=3&amp;q=battle&amp;view=5/48.2/16.4&amp;event=7001"' in page


def test_embed_may_be_framed_by_anyone_and_is_noindex(client):
    response = client.get("/embed")
    csp = response.headers["Content-Security-Policy"]
    assert "frame-ancestors *" in csp and "frame-ancestors 'none'" not in csp
    assert "default-src 'self'" in csp  # everything else stays as strict as on the other pages
    assert response.headers["X-Robots-Tag"] == "noindex"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_other_pages_still_forbid_framing(client):
    for path in ("/", "/about", "/game", "/collections/"):
        response = client.get(path)
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"], path
        assert "X-Robots-Tag" not in response.headers or "/collections" in path


def test_embed_shows_a_linked_event(client, make_event):
    make_event("Battle of Zama", year=-202, summary="Rome defeated Carthage.", wiki_page_id=7001)
    response = client.get("/embed?event=7001")
    assert response.status_code == 200
    assert "Battle of Zama" in response.get_data(as_text=True)
    old = client.get("/embed?event=1&tag=2")
    assert old.status_code == 301
    assert old.headers["Location"] == "/embed?event=7001&tag=2"


def test_full_map_offers_the_embed_snippet_and_the_collection_button(client):
    page = client.get("/").get_data(as_text=True)
    assert 'id="copy-view"' in page and 'id="embed-view"' in page
    assert page.count("data-collection-from-search>") == 2  # filter panel and big search
    assert 'data-from-search-url="/collections/from-search"' in page


# ---------------------------------------------------------------- small leftovers

def test_shared_base_map_is_not_saved_over_the_visitors_choice():
    map_js = (STATIC_JS / "map.js").read_text(encoding="utf-8")
    basemaps = (STATIC_JS / "basemaps.js").read_text(encoding="utf-8")
    assert 'localStorage.setItem("basemap"' not in map_js
    assert "addBasemapSwitcher(map, { initial: linkedBase })" in map_js
    assert "initial && choices.includes(initial)" in basemaps


def test_challenge_link_and_report_link_are_in_the_scripts():
    game_js = (STATIC_JS / "game.js").read_text(encoding="utf-8")
    assert 'if (HARD) url.searchParams.set("hard", "1")' in game_js
    map_js = (STATIC_JS / "map.js").read_text(encoding="utf-8")
    assert "#report" in map_js


def test_confirm_keeps_the_may_not_be_an_event_warning(client, wiki):
    wiki.add("Battle of Hastings", year=None, dated_by_wikidata=False)
    preview = client.post("/submit", data={"url": URL, "category": ""}).get_data(as_text=True)
    assert "may not be an event" in preview
    assert 'name="dated_by_wikidata"' in preview and 'value="0"' in preview

    # Back from a validation error (no summary): the warning is still there.
    again = client.post("/submit/confirm", data={**form_data(summary=""), "dated_by_wikidata": "0"})
    assert again.status_code == 400
    assert "may not be an event" in again.get_data(as_text=True)

    # A value that says the article was dated, or none at all, shows no warning.
    for value in ({"dated_by_wikidata": "1"}, {}):
        shown = client.post("/submit/confirm", data={**form_data(summary=""), **value})
        assert "may not be an event" not in shown.get_data(as_text=True)


def test_the_warning_flag_changes_nothing_about_what_is_stored(client, wiki):
    from haam.extensions import db
    from haam.models import Event, Status
    wiki.add("Battle of Hastings")
    response = client.post("/submit/confirm", data={**form_data(), "dated_by_wikidata": "0"})
    assert response.status_code == 200
    assert db.session.scalar(db.select(Event)).status == Status.PENDING
