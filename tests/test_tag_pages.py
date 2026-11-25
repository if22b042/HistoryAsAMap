"""Tag landing pages: /tag/<id>-<slug>, their key numbers, neighbours, map and sitemap entries."""

import re
from contextlib import contextmanager

import pytest
from sqlalchemy import event as sa_event

from haam import events as event_service
from haam import seo, tag_pages
from haam.extensions import db
from haam.models import Category, Status, Tag

SITE = "https://haam.test"


def tag_named(name: str) -> Tag:
    return db.session.query(Tag).filter_by(name=name).one()


def tagged(make_event, tags, title, **kwargs):
    """An event with tags, committed (an event left unreferenced cannot take tags later)."""
    event = make_event(title, **kwargs)
    event.tags.extend(tags)
    db.session.commit()
    return event


def add_tag(name: str, start: int | None, end: int | None) -> Tag:
    tag = Tag(name=name, start_year=start, end_year=end)
    db.session.add(tag)
    db.session.commit()
    return tag


@pytest.fixture
def ww2(make_event):
    """World War II with three approved events (made out of date order) and a pending one."""
    tag = tag_named("World War II")
    for title, year, label, page in [("Battle of Midway", 1942, "4 June 1942", 101),
                                     ("Invasion of Poland", 1939, "1 September 1939", 102),
                                     ("Battle of the Coral Sea", 1942, "4 May 1942", 103)]:
        tagged(make_event, [tag], title, year=year, date_label=label, wiki_page_id=page)
    tagged(make_event, [tag], "Pending raid", year=1940, status=Status.PENDING)
    db.session.commit()
    return tag


@contextmanager
def count_queries():
    statements = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sa_event.listen(db.engine, "before_cursor_execute", listener)
    try:
        yield statements
    finally:
        sa_event.remove(db.engine, "before_cursor_execute", listener)


# ---------------------------------------------------------------- the page

def test_tag_page_lists_approved_events_in_date_order(client, ww2):
    response = client.get(f"/tag/{ww2.id}-world-war-ii")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<h1>World War II</h1>" in html
    assert "1939 – 1945" in html
    titles = re.findall(r'<a href="/event/\d+-[a-z0-9-]+">([^<]+)</a>', html)
    assert titles == ["Invasion of Poland", "Battle of the Coral Sea", "Battle of Midway"]
    assert 'href="/event/102-invasion-of-poland"' in html
    assert "Pending raid" not in html
    assert "All 3 events, in date order" in html
    assert 'id="y1939"' in html and 'id="y1942"' in html  # the timeline's anchors


def test_tag_page_has_canonical_share_preview_and_buttons(client, ww2):
    html = client.get(f"/tag/{ww2.id}-world-war-ii").get_data(as_text=True)
    canonical = f"{SITE}/tag/{ww2.id}-world-war-ii"
    assert f'<link rel="canonical" href="{canonical}">' in html
    assert "<title>World War II on the map (1939 – 1945) · History As A Map</title>" in html
    assert '<meta property="og:title" content="World War II on the map">' in html
    assert f'<meta property="og:url" content="{canonical}">' in html
    assert "og-card.png" in html
    assert re.search(r'<meta name="description" content="3 historical events of World War II', html)
    assert "noindex" not in html
    assert f'href="/?tag={ww2.id}"' in html
    assert f'href="/collections/new?tag={ww2.id}"' in html
    assert "tile.openstreetmap.org/" in html  # tiles are loaded by the visitor's browser
    assert html.count('class="tile-map-dot') == 1  # the fixture's three events share one place
    assert '"@type": "BreadcrumbList"' in html


def test_tag_page_shows_key_numbers(client, ww2, make_event):
    tagged(make_event, [ww2], "Sinking of a ship", year=1943, category=Category.NAVAL, country="Japan")
    db.session.commit()
    html = client.get(f"/tag/{ww2.id}-world-war-ii").get_data(as_text=True)
    stats = re.search(r'<div class="figures tag-figures">(.*?)<nav', html, re.S).group(1)
    assert "<b>4</b><span>Events</span>" in stats
    assert "<b>1939–1943</b>" in stats
    assert "<b>1</b><span>Country</span>" in stats
    assert "Military 75%" in stats and "Naval 25%" in stats


@pytest.mark.parametrize("path", ["", "-wrong-slug"])
def test_wrong_or_missing_slug_redirects(client, ww2, path):
    response = client.get(f"/tag/{ww2.id}{path}")
    assert response.status_code == 301
    assert response.headers["Location"].endswith(f"/tag/{ww2.id}-world-war-ii")


def test_renamed_tag_redirects_from_its_old_slug(client, ww2):
    event_service.rename_tag(ww2, "Second World War")
    response = client.get(f"/tag/{ww2.id}-world-war-ii")
    assert response.status_code == 301
    assert response.headers["Location"].endswith(f"/tag/{ww2.id}-second-world-war")
    assert client.get(f"/tag/{ww2.id}-second-world-war").status_code == 200


def test_unknown_tag_is_404(client):
    assert client.get("/tag/999999-nothing").status_code == 404


def test_tag_without_approved_events_is_404(client, make_event):
    tag = tag_named("Norman Conquest of England")
    assert client.get(f"/tag/{tag.id}-norman-conquest-of-england").status_code == 404
    tagged(make_event, [tag], "Pending battle", status=Status.PENDING)
    db.session.commit()
    assert client.get(f"/tag/{tag.id}-norman-conquest-of-england").status_code == 404


def test_merged_tags_old_id_is_404(client, ww2):
    """A merge deletes the tag and records nowhere where it went."""
    old = add_tag("WWII", 1939, 1945)
    old_id = old.id
    event_service.merge_tags(old, ww2)
    assert client.get(f"/tag/{old_id}-wwii").status_code == 404


def test_small_tags_render_but_are_noindex(client, make_event):
    tag = tag_named("Norman Conquest of England")
    tagged(make_event, [tag], "Battle of Hastings")
    tagged(make_event, [tag], "Harrying of the North", year=1069)
    db.session.commit()
    response = client.get(f"/tag/{tag.id}-norman-conquest-of-england")
    assert response.status_code == 200
    assert '<meta name="robots" content="noindex">' in response.get_data(as_text=True)


def test_tag_page_queries_do_not_grow_with_its_events(client, ww2, make_event):
    with count_queries() as few:
        assert client.get(f"/tag/{ww2.id}-world-war-ii").status_code == 200
    for n in range(30):
        event = make_event(f"Battle {n}", year=1940 + n % 5, lat=40 + n, lon=n, country=f"Country {n}")
        event.tags.append(ww2)
    db.session.commit()
    db.session.expire_all()
    with count_queries() as many:
        assert client.get(f"/tag/{ww2.id}-world-war-ii").status_code == 200
    assert len(many) == len(few), many
    assert len(many) < 12, many


def test_event_page_links_its_tags_to_tag_pages(client, ww2):
    html = client.get("/event/102-invasion-of-poland").get_data(as_text=True)
    assert f'<a class="tag-pill" href="/tag/{ww2.id}-world-war-ii"' in html
    assert f'More from <a href="/tag/{ww2.id}-world-war-ii">World War II</a>' in html


def test_make_a_collection_starts_with_the_tag(client, ww2):
    html = client.get(f"/collections/new?tag={ww2.id}").get_data(as_text=True)
    assert re.search(rf'<option[^>]*selected[^>]*value="{ww2.id}"|<option[^>]*value="{ww2.id}"[^>]*selected', html)
    assert 'value="World War II"' in html
    assert client.get("/collections/new?tag=999999").status_code == 200


# ---------------------------------------------------------------- sitemap

def test_sitemap_lists_tag_pages_with_enough_events(client, ww2, make_event):
    small = tag_named("Norman Conquest of England")
    tagged(make_event, [small], "Battle of Hastings")
    db.session.commit()
    xml = client.get("/sitemap.xml").get_data(as_text=True)
    assert f"<loc>{SITE}/tag/{ww2.id}-world-war-ii</loc><lastmod>" in xml
    assert "norman-conquest" not in xml


def test_split_sitemap_puts_tag_pages_with_the_pages(client, ww2, monkeypatch):
    monkeypatch.setattr(seo, "SITEMAP_LIMIT", 2)
    assert f"/tag/{ww2.id}-world-war-ii" in client.get("/sitemap-pages.xml").get_data(as_text=True)


# ---------------------------------------------------------------- parts of the page

class E:
    """Enough of an Event for stats and timeline."""

    def __init__(self, year, category=Category.MILITARY, country=None):
        self.year, self.category, self.country = year, category, country


def test_timeline_groups_years_into_at_most_forty_bars():
    yearly = tag_pages.timeline([E(1914), E(1914), E(1916), E(1918)])
    assert [b.label for b in yearly] == ["1914", "1915", "1916", "1917", "1918"]
    assert [b.count for b in yearly] == [2, 0, 1, 0, 1]
    assert yearly[0].height == 100 and yearly[1].height == 0 and yearly[2].height == 50
    assert yearly[2].anchor == 1916 and yearly[1].anchor is None

    long = tag_pages.timeline([E(-500), E(-120), E(1453)])
    assert len(long) <= tag_pages.TIMELINE_BARS
    assert "BC" in long[0].label

    assert tag_pages.timeline([E(1066), E(1066)]) == []  # one bar says nothing


def test_neighbours_follow_shared_events_and_tag_parents(client, make_event):
    era = add_tag("Napoleonic Era", 1799, 1815)
    wars = add_tag("Napoleonic Wars", 1803, 1815)
    peninsular = add_tag("Peninsular War", 1807, 1814)
    other = add_tag("Anglo-Spanish War", 1804, 1809)
    same_time = add_tag("War of the Fourth Coalition", 1806, 1807)
    for n in range(4):
        event = make_event(f"Battle {n}", year=1808)
        event.tags += [era, wars, peninsular]
    shared = make_event("Shared battle", year=1806)
    shared.tags += [era, wars, other]
    shared_too = make_event("Another shared battle", year=1806)
    shared_too.tags += [wars, other]
    tagged(make_event, [other], "Battle off Cadiz", year=1805)  # not all of its events are Napoleonic
    for n in range(3):
        tagged(make_event, [same_time], f"Coalition battle {n}", year=1807)
    db.session.commit()

    groups = tag_pages.neighbours(wars, 6)
    assert [n.tag.name for n in groups["broader"]] == ["Napoleonic Era"]
    assert [n.tag.name for n in groups["narrower"]] == ["Peninsular War"]
    assert [n.tag.name for n in groups["related"]] == ["Anglo-Spanish War"]
    assert "War of the Fourth Coalition" not in [n.tag.name for n in groups["same_time"]]  # 2 of 13 years

    groups = tag_pages.neighbours(peninsular, 4)
    assert {n.tag.name for n in groups["broader"]} == {"Napoleonic Era", "Napoleonic Wars"}


def test_area_map_fits_the_points_and_draws_close_dots_once():
    europe = [(48.8, 2.3, "military"), (52.5, 13.4, "naval"), (52.5001, 13.4001, "other"), (41.9, 12.5, "military")]
    area = seo.area_map(europe)
    assert area.tiles[0].url.startswith("https://tile.openstreetmap.org/")
    assert len(area.dots) == 3
    assert {d.category for d in area.dots} == {"military", "naval"}
    for dot in area.dots:  # every dot inside the box the figure shows around the centre
        assert abs(dot.x - area.point_x) <= seo.AREA_FIT[0] / 2 + 1
        assert abs(dot.y - area.point_y) <= seo.AREA_FIT[1] / 2 + 1

    world = seo.area_map([(51.5, -0.1, "military"), (-33.9, 151.2, "military"), (40.7, -74.0, "military")])
    assert world.tiles[0].url.startswith("https://tile.openstreetmap.org/2/")
    assert seo.area_map([]) is None
