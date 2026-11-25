"""Story mode: the payload for collections and tags, the four pages and their headers."""

import json
import re

import pytest

from haam import collections_service as service
from haam import story
from haam.extensions import db
from haam.models import Status, Tag
from haam.tag_tree import PartOfGraph
from tests.test_collections import create, custom, edit_link


def payload(response) -> dict:
    html = response.get_data(as_text=True)
    return json.loads(re.search(r'<script type="application/json" id="story-data">(.*?)</script>', html, re.S).group(1))


def add_custom(client, collection, **overrides):
    response = client.post(f"/collections/{collection.view_token}/entries/custom", data=custom(**overrides))
    assert response.status_code in (200, 302)
    db.session.refresh(collection)


# ------------------------------------------------------------ collections

def test_collection_story_follows_entry_order_with_links(client, make_event):
    first = make_event("Battle of Zama", year=-202, summary="Rome defeated Carthage.", wiki_page_id=7001)
    collection, _ = create(client)
    service.add_event(collection, first.id, "A turning point")
    add_custom(client, collection, title="Safe", link="https://example.org/page")
    add_custom(client, collection, title="Unsafe", link="https://example.org/x")
    collection.entries[-1].link = "javascript:alert(1)"  # the form would refuse it; the page must not trust the DB
    db.session.commit()

    response = client.get(f"/collections/{collection.view_token}/story")
    assert response.status_code == 200
    data = payload(response)
    assert [s["title"] for s in data["steps"]] == ["Battle of Zama", "Safe", "Unsafe"]
    zama, safe, bad = data["steps"]
    assert zama["note"] == "A turning point" and zama["text"] == "Rome defeated Carthage." and not zama["custom"]
    assert zama["link"] == "/event/7001-battle-of-zama" and zama["link_label"] == "Event page"
    assert safe["custom"] and safe["link"] == "https://example.org/page" and safe["link_label"] == "Source"
    assert bad["link"] is None and bad["link_label"] is None
    assert data["kind"] == "collection" and data["path_default"] is True and data["count"] == 3
    assert data["story_url"].startswith("http") and "?" not in data["story_url"]

    ids = [e.id for e in collection.entries]
    service.reorder_entries(collection, ids[::-1])
    data = payload(client.get(f"/collections/{collection.view_token}/story"))
    assert [s["title"] for s in data["steps"]] == ["Unsafe", "Safe", "Battle of Zama"]


def test_a_long_collection_has_no_period_chapters(client, make_event):
    """Its order is the owner's, not the date's: the steps list stays flat."""
    collection, _ = create(client)
    for year in range(1800, 2000, 8):  # 25 entries over two centuries
        service.add_event(collection, make_event(f"Event of {year}", year=year).id, "")
    data = payload(client.get(f"/collections/{collection.view_token}/story"))
    assert data["count"] == 25 and data["chapters"] == []


def test_hidden_unknown_and_empty_collections(client, app):
    collection, _ = create(client)
    page = client.get(f"/collections/{collection.view_token}/story").get_data(as_text=True)
    assert "This story has no steps yet." in page
    collection.is_hidden = True
    db.session.commit()
    fresh = app.test_client()
    for suffix in ("story", "embed"):
        assert fresh.get(f"/collections/{collection.view_token}/{suffix}").status_code == 410
        assert fresh.get(f"/collections/nope/{suffix}").status_code == 404


def test_embed_headers_and_noindex(client):
    collection, _ = create(client)
    embed = client.get(f"/collections/{collection.view_token}/embed")
    assert "frame-ancestors *" in embed.headers["Content-Security-Policy"]
    assert embed.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert embed.headers["Referrer-Policy"] == "strict-origin"
    page = client.get(f"/collections/{collection.view_token}/story")
    assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
    assert page.headers["X-Robots-Tag"] == "noindex, nofollow"


def test_story_pages_show_nothing_editor_related(client):
    collection, _ = create(client)
    token = edit_link(client, collection).rsplit("/", 1)[1]  # this browser can edit, the pages still must not say so
    assert client.get(f"/collections/{collection.view_token}/manage").status_code == 200
    for suffix in ("story", "embed"):
        html = client.get(f"/collections/{collection.view_token}/{suffix}").get_data(as_text=True)
        assert "/edit/" not in html and "/manage" not in html and token not in html


# ------------------------------------------------------------ tags

@pytest.fixture
def war(make_event):
    tag = Tag(name="Test War", start_year=1900, end_year=1950)
    db.session.add(tag)
    db.session.commit()
    events = [
        make_event("Late", year=1940, date_label="1940", tags=[tag], wiki_page_id=3001),
        make_event("Early", year=1910, date_label="1910", tags=[tag], wiki_page_id=3002),
        make_event("Mid B", year=1920, date_label="2 May 1920", tags=[tag], wiki_page_id=3003),
        make_event("Mid A", year=1920, date_label="1 June 1920", tags=[tag], wiki_page_id=3004),
    ]
    make_event("Pending", year=1930, status=Status.PENDING, tags=[tag], wiki_page_id=3005)
    return tag, events


def test_tag_story_order_and_year_range(client, war):
    tag, _ = war
    data = payload(client.get(f"/story/tag/{tag.id}"))
    expected = [e.title for e in service.tag_events(tag.id)]
    assert [s["title"] for s in data["steps"]] == expected
    assert [s["year"] for s in data["steps"]] == sorted(s["year"] for s in data["steps"])
    assert data["kind"] == "tag" and data["intro"] == tag.display_range and data["path_default"] is False
    assert data["back_url"] == f"/?tag={tag.id}"
    narrowed = payload(client.get(f"/story/tag/{tag.id}?from=1915&to=1930"))
    assert {s["title"] for s in narrowed["steps"]} == {"Mid A", "Mid B"}
    assert narrowed["back_url"] == f"/?tag={tag.id}&from=1915&to=1930"
    assert payload(client.get(f"/story/tag/{tag.id}?from=junk"))["count"] == 4


def test_tag_story_404_cases_and_embed(client, war, make_event):
    tag, _ = war
    assert client.get("/story/tag/9999").status_code == 404
    only_pending = Tag(name="Pending only")
    db.session.add(only_pending)
    db.session.commit()
    make_event("Waiting", status=Status.PENDING, tags=[only_pending])
    assert client.get(f"/story/tag/{only_pending.id}").status_code == 404
    embed = client.get(f"/embed/story/tag/{tag.id}")
    assert embed.status_code == 200
    assert "frame-ancestors *" in embed.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in client.get(f"/story/tag/{tag.id}").headers["Content-Security-Policy"]


def test_tag_part(client, make_event, monkeypatch):
    tag = db.session.scalar(db.select(Tag).filter_by(name="World War II"))
    graph = PartOfGraph(parents={"Q50": ["Q362"], "Q1": ["Q50"], "Q2": ["Q50"], "Q3": ["Q362"]},
                        labels={"Q362": "World War II", "Q50": "Eastern Front"},
                        tag_items={"World War II": ["Q362"]})
    monkeypatch.setattr("haam.tag_tree.load_graph", lambda *a, **k: graph)
    for title, year, qid, pid in (("One", 1941, "Q1", 4001), ("Two", 1942, "Q2", 4002), ("Three", 1943, "Q3", 4003)):
        make_event(title, year=year, wikidata_id=qid, tags=[tag], wiki_page_id=pid)
    data = payload(client.get(f"/story/tag/{tag.id}?part=Q50"))
    assert [s["title"] for s in data["steps"]] == ["One", "Two"]
    assert data["title"] == "Eastern Front" and data["intro"] == "Part of World War II"
    assert data["parts"] == ["World War II › Eastern Front"] and data["steps"][0]["part"] == 0
    assert "part=Q50" in data["back_url"]
    whole = payload(client.get(f"/story/tag/{tag.id}?part=Q999"))
    assert whole["count"] == 3 and whole["title"] == "World War II"
    assert payload(client.get(f"/story/tag/{tag.id}?part=bad"))["count"] == 3
    three = next(s for s in whole["steps"] if s["title"] == "Three")
    assert three["part"] is None


# ------------------------------------------------------------ chapters

def steps_for(years):
    return [{"year": y} for y in years]


def test_chapters_by_span():
    assert story.chapters(steps_for(range(1900, 1919))) == []  # fewer than 20 steps
    by_year = story.chapters(steps_for(list(range(1900, 1920)) + [1920]))
    assert by_year[0] == {"label": "1900", "first": 0} and len(by_year) == 21
    decades = story.chapters(steps_for(range(1800, 2000, 8)))
    assert decades[0] == {"label": "1800 – 1809", "first": 0}
    assert decades[1] == {"label": "1810 – 1819", "first": 2}
    centuries = story.chapters(steps_for(range(1000, 2000, 40)))
    assert [c["label"] for c in centuries][:2] == ["1000 – 1099", "1100 – 1199"]
    assert centuries[1]["first"] == 3


def test_chapters_bc_and_single():
    bc = story.chapters(steps_for(range(-229, -200)))
    assert bc[0]["label"] == "229 BC" and len(bc) == 29
    decades = story.chapters(steps_for(range(-300, -100, 8)))
    assert decades[0]["label"] == "300 BC – 291 BC"
    assert story.chapters(steps_for([1900] * 20)) == []
