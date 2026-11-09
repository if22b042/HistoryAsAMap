"""Event pages, share previews, the sitemap, robots.txt and icons."""

import json
import re
from xml.etree import ElementTree

import pytest

from haam import game, seo
from haam.extensions import db
from haam.models import Status, Tag

SITE = "https://haam.test"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def meta(html: str, key: str) -> str | None:
    """The content of <meta property|name="key">, unescaped enough for comparisons."""
    match = re.search(rf'<meta (?:property|name)="{re.escape(key)}" content="([^"]*)"', html)
    return match.group(1) if match else None


def test_slugify():
    assert seo.slugify("Battle of Zama") == "battle-of-zama"
    assert seo.slugify("Siège de Paris (1870–1871)") == "siege-de-paris-1870-1871"
    assert seo.slugify("東京") == "event"
    assert len(seo.slugify("word " * 50)) <= seo.SLUG_LENGTH


def test_describe_cuts_at_a_word():
    text = "word " * 100
    short = seo.describe(text)
    assert len(short) <= seo.DESCRIPTION_LENGTH
    assert short.endswith("word…")
    assert seo.describe("  Short\n text. ") == "Short text."


# ---------------------------------------------------------------- event pages

def test_event_page_renders_server_side(client, make_event):
    event = make_event("Battle of Zama", year=-202, date_label="19 October 202 BC",
                       summary="The Battle of Zama was fought in 202 BC.", lat=36.3, lon=9.4)
    event.tags.append(db.session.query(Tag).filter_by(name="World War II").one())
    db.session.commit()

    response = client.get(f"/event/{event.id}-battle-of-zama")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<h1>Battle of Zama</h1>" in html
    assert "202 BC" in html
    assert "The Battle of Zama was fought in 202 BC." in html
    assert "Military" in html
    assert "World War II" in html
    assert "https://en.wikipedia.org/wiki/Battle_of_Zama" in html
    assert "CC BY-SA 4.0" in html
    assert f'href="/?event={event.id}"' in html
    assert "tile.openstreetmap.org/6/" in html
    canonical = f"{SITE}/event/{event.id}-battle-of-zama"
    assert f'<link rel="canonical" href="{canonical}">' in html
    assert "<title>Battle of Zama (202 BC) · History As A Map</title>" in html
    assert meta(html, "og:url") == canonical
    assert meta(html, "og:type") == "article"
    assert meta(html, "og:title") == "Battle of Zama (202 BC)"
    assert meta(html, "og:description") == "The Battle of Zama was fought in 202 BC."
    assert meta(html, "og:image") == f"{SITE}/static/img/og-card.png"
    assert meta(html, "twitter:card") == "summary_large_image"


@pytest.mark.parametrize("status", [Status.PENDING, Status.REJECTED])
def test_unapproved_event_page_is_404(client, make_event, status):
    event = make_event("Battle of Zama", status=status)
    assert client.get(f"/event/{event.id}-battle-of-zama").status_code == 404
    assert client.get(f"/event/{event.id}").status_code == 404


def test_missing_event_page_is_404(client):
    assert client.get("/event/999-nothing").status_code == 404


@pytest.mark.parametrize("suffix", ["", "-wrong-slug", "-Battle-of-Zama"])
def test_wrong_slug_redirects_to_the_canonical_page(client, make_event, suffix):
    event = make_event("Battle of Zama")
    response = client.get(f"/event/{event.id}{suffix}")
    assert response.status_code == 301
    assert response.headers["Location"] == f"/event/{event.id}-battle-of-zama"


def test_event_page_lists_related_events(client, make_event):
    tag = db.session.query(Tag).filter_by(name="World War II").one()
    first = make_event("Battle of Britain", year=1940)
    second = make_event("Battle of Midway", year=1942)
    hidden = make_event("Battle of Nowhere", year=1941, status=Status.PENDING)
    for event in (first, second, hidden):
        event.tags.append(tag)
    db.session.commit()
    html = client.get(f"/event/{first.id}-battle-of-britain").get_data(as_text=True)
    assert "More from World War II" in html
    assert f'href="/event/{second.id}-battle-of-midway"' in html
    assert "Battle of Nowhere" not in html


def test_tile_map_centres_the_point():
    tiles = seo.tile_map(0, 0)
    assert len(tiles.tiles) == 15
    assert (tiles.point_x, tiles.point_y) == (512, 256)  # middle of the 5×3 mosaic
    near_pole = seo.tile_map(89, 179.9)
    assert all("/6/" in tile.url for tile in near_pole.tiles)
    assert 0 <= near_pole.point_y <= near_pole.height


# ---------------------------------------------------------------- share previews

def test_map_has_meta_and_canonical(client):
    html = client.get("/").get_data(as_text=True)
    assert f'<link rel="canonical" href="{SITE}/">' in html
    assert meta(html, "og:title") == "Interactive map of historical events"
    assert meta(html, "og:image") == f"{SITE}/static/img/og-card.png"
    assert meta(html, "description") == seo.DEFAULT_DESCRIPTION


def test_map_link_to_one_event_previews_that_event(client, make_event):
    event = make_event("Battle of Zama", year=-202, summary="Rome defeated Carthage.")
    html = client.get(f"/?event={event.id}").get_data(as_text=True)
    assert "<title>Battle of Zama (202 BC) · Map · History As A Map</title>" in html
    assert meta(html, "og:description") == "Rome defeated Carthage."
    assert meta(html, "og:url") == f"{SITE}/event/{event.id}-battle-of-zama"
    assert 'rel="canonical"' not in html


def test_map_link_to_pending_event_shows_the_plain_map(client, make_event):
    event = make_event("Secret battle", status=Status.PENDING)
    html = client.get(f"/?event={event.id}").get_data(as_text=True)
    assert "Secret battle" not in html
    assert meta(html, "og:title") == "Interactive map of historical events"


def test_game_has_title_description_and_structured_data(client):
    html = client.get("/game").get_data(as_text=True)
    assert "<title>Where did it happen? Daily history geography game · History As A Map</title>" in html
    assert "daily history geography game" in meta(html, "description")
    assert f'<link rel="canonical" href="{SITE}/game">' in html
    assert meta(html, "og:image") == f"{SITE}/static/img/og-game.png"
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    assert "VideoGame" in data["@type"]
    assert data["url"] == f"{SITE}/game"


def test_game_share_link_names_the_day(client):
    day = game.today_utc()
    number = game.game_number(day)
    html = client.get(f"/game?date={day.isoformat()}&hard=1").get_data(as_text=True)
    assert meta(html, "og:title") == f"History As A Map · Game #{number} (Hard) – where did it happen?"
    assert meta(html, "og:url") == f"{SITE}/game?date={day.isoformat()}&amp;hard=1"
    # Every dated variant still points search engines at /game.
    assert f'<link rel="canonical" href="{SITE}/game">' in html


def test_game_ignores_unplayable_share_dates(client):
    html = client.get("/game?date=1900-01-01").get_data(as_text=True)
    assert meta(html, "og:title") == "Where did it happen? A daily history geography game"


def test_collection_share_page_has_preview_and_stays_noindex(client):
    from haam import collections_service as service
    collection, _token = service.create_collection("Roman wars", "Rome against everyone.", is_public=True)
    response = client.get(f"/collections/{collection.view_token}")
    html = response.get_data(as_text=True)
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert meta(html, "og:title") == "Roman wars"
    assert meta(html, "og:description") == "Rome against everyone."


# ---------------------------------------------------------------- sitemap, robots, icons

def _locs(xml: bytes) -> list[str]:
    root = ElementTree.fromstring(xml)
    return [loc.text for loc in root.iterfind(".//sm:loc", NS)]


def test_sitemap_lists_pages_and_approved_events_only(client, make_event):
    zama = make_event("Battle of Zama")
    make_event("Pending battle", status=Status.PENDING)
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    root = ElementTree.fromstring(response.data)
    assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"
    locs = _locs(response.data)
    assert locs == [f"{SITE}/", f"{SITE}/game", f"{SITE}/about", f"{SITE}/event/{zama.id}-battle-of-zama"]
    assert root.find(".//sm:url/sm:lastmod", NS) is not None
    assert "collections" not in response.get_data(as_text=True)


def test_sitemap_splits_beyond_the_url_limit(client, make_event, monkeypatch):
    events = [make_event(f"Battle {n}") for n in range(5)]
    monkeypatch.setattr(seo, "SITEMAP_LIMIT", 2)
    index = client.get("/sitemap.xml")
    root = ElementTree.fromstring(index.data)
    assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}sitemapindex"
    parts = _locs(index.data)
    assert parts == [f"{SITE}/sitemap-pages.xml"] + [f"{SITE}/sitemap-events-{n}.xml" for n in (1, 2, 3)]
    listed = []
    for part in parts:
        response = client.get(part.removeprefix(SITE))
        assert response.status_code == 200
        listed += _locs(response.data)
    assert len(listed) == 3 + len(events)
    assert client.get("/sitemap-events-4.xml").status_code == 404
    assert client.get("/sitemap-other.xml").status_code == 404


def test_sitemap_parts_are_404_while_one_file_suffices(client):
    assert client.get("/sitemap-pages.xml").status_code == 404


def test_robots_points_to_the_sitemap(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    body = response.get_data(as_text=True)
    assert "User-agent: *" in body
    assert f"Sitemap: {SITE}/sitemap.xml" in body
    assert "Disallow: /admin" in body


@pytest.mark.parametrize("path, mimetype", [
    ("/favicon.ico", "image/vnd.microsoft.icon"),
    ("/apple-touch-icon.png", "image/png"),
    ("/static/img/favicon.svg", "image/svg+xml"),
    ("/static/img/og-card.png", "image/png"),
    ("/static/img/og-game.png", "image/png"),
])
def test_icons_and_share_images_exist(client, path, mimetype):
    response = client.get(path)
    assert response.status_code == 200
    assert response.mimetype in (mimetype, "image/x-icon")


def test_every_page_links_the_icons(client):
    html = client.get("/about").get_data(as_text=True)
    assert 'rel="icon"' in html and 'rel="apple-touch-icon"' in html
    assert f'<link rel="canonical" href="{SITE}/about">' in html


def test_site_url_falls_back_to_the_request(app, client):
    app.config["SITE_URL"] = ""
    html = client.get("/about").get_data(as_text=True)
    assert '<link rel="canonical" href="http://localhost/about">' in html
