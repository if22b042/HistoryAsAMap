"""Events within a year are ordered by date (month, day), undated ones last, then title."""

from haam import feed


def _chunk_rows(client, manifest):
    rows = []
    for url in manifest["core"]:
        chunk = client.get(url).json
        assert len(chunk["md"]) == chunk["count"]
        rows += list(zip(chunk["year"], chunk["md"], chunk["title"]))
    return rows


def _manifest(client):
    import html
    import json
    import re
    page = client.get("/").get_data(as_text=True)
    return json.loads(html.unescape(re.search(r"data-manifest='([^']*)'", page).group(1)))


def test_core_chunk_orders_a_year_by_date_not_title(client, make_event):
    # All in one chunk: ids 20 apart would be needed, so check each chunk and the md key.
    make_event(title="Normandy landings", year=1944, date_label="6 June 1944")
    make_event(title="Battle of the Bulge", year=1944, date_label="16 December 1944")
    make_event(title="Aaa undated", year=1944, date_label="1944")
    make_event(title="Zzz second of June", year=1944, date_label="6 June 1944")
    manifest = _manifest(client)
    assert feed.FORMAT >= 2
    rows = _chunk_rows(client, manifest)
    md = {title: key for _, key, title in rows}
    assert md == {"Normandy landings": 606, "Battle of the Bulge": 1216,
                  "Aaa undated": 0, "Zzz second of June": 606}
    # Within each chunk the order is: by md (0 last), then title.
    for url in manifest["core"]:
        chunk = client.get(url).json
        keys = [(y, m or 9999, t) for y, m, t in zip(chunk["year"], chunk["md"], chunk["title"])]
        assert keys == sorted(keys)


def test_tag_events_are_oldest_first_by_date(app, make_event):
    from haam.collections_service import tag_events
    from haam.extensions import db
    from haam.models import Tag
    tag = Tag(name="WWII")
    db.session.add(tag)
    late = make_event(title="Battle of the Bulge", year=1944, date_label="16 December 1944")
    early = make_event(title="Normandy landings", year=1944, date_label="6 June 1944")
    late.tags.append(tag)
    early.tags.append(tag)
    db.session.commit()
    assert [e.title for e in tag_events(tag.id)] == ["Normandy landings", "Battle of the Bulge"]
