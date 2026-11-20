import pytest

from haam.wikipedia import WikipediaClient, canonical_url, title_from_url


@pytest.mark.parametrize("url, title", [
    ("https://en.wikipedia.org/wiki/Battle_of_Hastings", "Battle of Hastings"),
    ("http://en.wikipedia.org/wiki/Battle_of_Hastings#Background", "Battle of Hastings"),
    ("https://en.m.wikipedia.org/wiki/Battle_of_Hastings?oldid=1", "Battle of Hastings"),
    ("https://en.wikipedia.org/wiki/Battle_of_the_Teutoburg_Forest", "Battle of the Teutoburg Forest"),
    ("https://en.wikipedia.org/wiki/Caf%C3%A9_society", "Café society"),
    ("  https://en.wikipedia.org/wiki/D-Day  ", "D-Day"),
])
def test_title_from_url(url, title):
    assert title_from_url(url) == title


@pytest.mark.parametrize("url", [
    "https://de.wikipedia.org/wiki/Schlacht",
    "https://example.com/wiki/Battle",
    "https://en.wikipedia.org/w/index.php?title=X",
    "javascript:alert(1)",
    "",
])
def test_title_from_url_rejects(url):
    assert title_from_url(url) is None


def test_canonical_url():
    assert canonical_url("Battle of Hastings") == "https://en.wikipedia.org/wiki/Battle_of_Hastings"
    assert canonical_url("Thirty Years' War") == "https://en.wikipedia.org/wiki/Thirty_Years'_War"


def test_fetch_article_prefers_wikidata_date(monkeypatch):
    client = WikipediaClient("test-agent")
    responses = {
        "https://en.wikipedia.org/w/api.php": {"query": {"pages": [{
            "pageid": 42,
            "title": "Battle of the Teutoburg Forest",
            "extract": "The battle took place in 1987 according to nobody.\nMore text.",
            "coordinates": [{"lat": 52.4, "lon": 8.1}],
            "pageprops": {"wikibase_item": "Q155922"},
        }]}},
        "https://www.wikidata.org/w/api.php": {"entities": {"Q155922": {"claims": {"P585": [{
            "mainsnak": {"snaktype": "value", "datavalue": {"value": {
                "time": "+0009-09-00T00:00:00Z", "precision": 10}}},
        }]}}}},
    }
    monkeypatch.setattr(client, "_get", lambda url, params: responses[url])

    article = client.fetch_article("Battle of the Teutoburg Forest")
    assert article.year == 9
    assert article.date_label == "September AD 9"
    assert article.dated_by_wikidata
    assert article.summary == "The battle took place in 1987 according to nobody."
    assert article.url == "https://en.wikipedia.org/wiki/Battle_of_the_Teutoburg_Forest"


def _fetch(monkeypatch, page_extra, claims=None):
    client = WikipediaClient("test-agent")
    page = {"pageid": 1, "title": "X", "extract": "Happened in 1969.", **page_extra}
    responses = {
        "https://en.wikipedia.org/w/api.php": {"query": {"pages": [page]}},
        "https://www.wikidata.org/w/api.php": {"entities": {"Q1": {"claims": claims or {}}}},
    }
    monkeypatch.setattr(client, "_get", lambda url, params: responses[url])
    return client.fetch_article("X")


@pytest.mark.parametrize("globe", ["moon", "mars"])
def test_article_coordinates_off_earth_are_ignored(monkeypatch, globe):
    article = _fetch(monkeypatch, {"coordinates": [{"lat": 0.67, "lon": 23.47, "globe": globe}]})
    assert article.lat is None and article.lon is None


def test_article_coordinates_on_earth_are_kept(monkeypatch):
    article = _fetch(monkeypatch, {"coordinates": [{"lat": 10, "lon": 20, "globe": "earth"}]})
    assert (article.lat, article.lon) == (10, 20)


def test_article_coordinates_out_of_range_are_ignored(monkeypatch):
    article = _fetch(monkeypatch, {"coordinates": [{"lat": 123, "lon": 20}]})
    assert article.lat is None and article.lon is None


def _coord_claim(lat, lon, globe="http://www.wikidata.org/entity/Q2"):
    return {"P625": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {
        "latitude": lat, "longitude": lon, "globe": globe}}}}]}


def test_wikidata_coordinates_skip_other_globes_and_bad_ranges(monkeypatch):
    props = {"pageprops": {"wikibase_item": "Q1"}}
    moon = _fetch(monkeypatch, props, _coord_claim(0.67, 23.47, "http://www.wikidata.org/entity/Q405"))
    assert moon.lat is None and moon.lon is None
    bad = _fetch(monkeypatch, props, _coord_claim(95, 10))
    assert bad.lat is None and bad.lon is None
    good = _fetch(monkeypatch, props, _coord_claim(48.8, 2.3))
    assert (good.lat, good.lon) == (48.8, 2.3)


def test_title_with_pipe_is_rejected():
    assert title_from_url("https://en.wikipedia.org/wiki/Foo%7CBar") is None
    assert title_from_url("https://en.wikipedia.org/wiki/Foo|Bar") is None


def test_fetch_article_missing(monkeypatch):
    client = WikipediaClient("test-agent")
    monkeypatch.setattr(client, "_get", lambda url, params: {"query": {"pages": [{"missing": True}]}})
    assert client.fetch_article("Nope") is None
