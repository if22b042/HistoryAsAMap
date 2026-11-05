import pytest
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from haam import create_app
from haam.extensions import db as _db
from haam.models import Category, Event, Status, Tag
from haam.wikipedia import Article, canonical_url

ADMIN_PASSWORD = "correct horse battery staple"


class FakeWikipedia:
    """Stands in for WikipediaClient so tests never touch the network."""

    def __init__(self):
        self.articles: dict[str, Article] = {}
        self.geo_titles: list[str] = []

    def add(self, title, *, year=1066, lat=50.9, lon=0.49, summary=None, date_label=None,
            page_id=None, dated_by_wikidata=True):
        article = Article(
            page_id=page_id or (len(self.articles) + 100),
            title=title,
            url=canonical_url(title),
            summary=summary or f"The {title} was an event.",
            lat=lat,
            lon=lon,
            year=year,
            date_label=date_label if date_label is not None else str(year or ""),
            dated_by_wikidata=dated_by_wikidata,
        )
        self.articles[title] = article
        return article

    def fetch_article(self, title):
        return self.articles.get(title)

    def geosearch(self, lat, lon, radius=10000, limit=500):
        return list(self.geo_titles)


@pytest.fixture
def app():
    app = create_app("testing")
    app.config["ADMIN_PASSWORD_HASH"] = generate_password_hash(ADMIN_PASSWORD)
    app.extensions["haam_wikipedia"] = FakeWikipedia()
    with app.app_context():
        _db.create_all()
        _db.session.add_all([
            Tag(name="Norman Conquest of England", start_year=1066, end_year=1075),
            Tag(name="World War II", start_year=1939, end_year=1945),
        ])
        _db.session.commit()
        yield app
        _db.session.remove()
        _db.drop_all()
        # Tables some tests create by hand (legacy schema); matters on PostgreSQL.
        with _db.engine.begin() as conn:
            for table in ("locations", "entries"):
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))


@pytest.fixture
def wiki(app) -> FakeWikipedia:
    return app.extensions["haam_wikipedia"]


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_client(client):
    client.post("/admin/login", data={"username": "admin", "password": ADMIN_PASSWORD})
    return client


@pytest.fixture
def make_event(app):
    def _make(title="Battle of Hastings", status=Status.APPROVED, year=1066, **kwargs):
        event = Event(
            title=title,
            year=year,
            date_label=kwargs.pop("date_label", "14 October 1066"),
            summary=kwargs.pop("summary", "A battle."),
            wiki_url=canonical_url(title),
            lat=kwargs.pop("lat", 50.9),
            lon=kwargs.pop("lon", 0.49),
            category=kwargs.pop("category", Category.MILITARY),
            status=status,
            **kwargs,
        )
        _db.session.add(event)
        _db.session.commit()
        return event

    return _make
