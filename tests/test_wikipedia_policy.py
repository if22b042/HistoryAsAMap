from haam import wikipedia
from haam.wikipedia import WikipediaClient

from tests.test_submission import URL

WIKIDATA = "https://www.wikidata.org/w/api.php"
WIKIPEDIA = "https://en.wikipedia.org/w/api.php"


def _claim(year, rank="normal"):
    return {
        "rank": rank,
        "mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": f"+{year:04d}-01-01T00:00:00Z",
                                                                  "precision": 9}}},
    }


def _article_with_claims(monkeypatch, claims):
    client = WikipediaClient("test-agent")
    responses = {
        WIKIPEDIA: {"query": {"pages": [{
            "pageid": 42, "title": "Battle of Hastings", "extract": "A battle.",
            "pageprops": {"wikibase_item": "Q1"},
        }]}},
        WIKIDATA: {"entities": {"Q1": {"claims": {"P585": claims}}}},
    }
    monkeypatch.setattr(client, "_get", lambda url, params: responses[url])
    return client.fetch_article("Battle of Hastings")


def test_deprecated_dates_are_skipped(monkeypatch):
    article = _article_with_claims(monkeypatch, [_claim(1000, rank="deprecated"), _claim(1067)])
    assert article.year == 1067 and article.dated_by_wikidata


def test_preferred_date_wins_over_normal_one(monkeypatch):
    article = _article_with_claims(monkeypatch, [_claim(1067), _claim(1066, rank="preferred")])
    assert article.year == 1066


def test_only_deprecated_dates_mean_no_wikidata_date(monkeypatch):
    article = _article_with_claims(monkeypatch, [_claim(1000, rank="deprecated")])
    assert article.year is None and not article.dated_by_wikidata


def test_web_requests_get_a_short_client_and_imports_a_patient_one(app):
    app.extensions.pop("haam_wikipedia", None)
    web = wikipedia.get_client()
    assert web.timeout == wikipedia.WEB_TIMEOUT == 5.0
    assert web.session.get_adapter("https://").max_retries.total == 1

    app.extensions.pop("haam_wikipedia")
    patient = wikipedia.get_client(patient=True)
    assert patient.timeout == app.config["HTTP_TIMEOUT"]
    assert patient.session.get_adapter("https://").max_retries.total == 3


def test_preview_warns_when_wikidata_gives_no_date(client, wiki):
    wiki.add("Battle of Hastings", dated_by_wikidata=False)
    html = client.post("/submit", data={"url": URL}).get_data(as_text=True)
    assert "This article may not be an event: Wikidata gives it no date. Please check the year." in html


def test_preview_has_no_warning_for_a_dated_article(client, wiki):
    wiki.add("Battle of Hastings", dated_by_wikidata=True)
    html = client.post("/submit", data={"url": URL}).get_data(as_text=True)
    assert "This article may not be an event" not in html
