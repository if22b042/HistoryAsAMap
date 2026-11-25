"""Browser smoke tests (Playwright): the map's JavaScript in a real browser.

Local only. They skip themselves when Playwright or its Chromium is missing (CI installs
neither): ``pip install pytest-playwright`` and ``playwright install chromium`` to run them.
The map's libraries come from public CDNs, so the browser needs internet access.
"""

import threading

import pytest
from werkzeug.serving import make_server

from haam import create_app
from haam.extensions import db
from haam.models import Category, Event, Status
from haam.wikipedia import canonical_url

try:
    from playwright import sync_api
except ImportError:  # not installed (CI): every test here is skipped
    sync_api = None

# Three events in Jerusalem, one 60 km south of it, one far away.
EVENTS = [
    ("Siege of Jerusalem (587 BC)", -587, 31.778, 35.235),
    ("Siege of Jerusalem (70 CE)", 70, 31.776, 35.234),
    ("Siege of Jerusalem (1187)", 1187, 31.780, 35.230),
    ("Battle south of Jerusalem (1948)", 1948, 31.240, 35.229),
    ("Storming of the Bastille", 1789, 48.853, 2.369),
]


@pytest.fixture(scope="session")
def live_url():
    app = create_app("testing")  # in-memory SQLite, shared by the server's threads
    with app.app_context():
        db.create_all()
        db.session.add_all(Event(
            title=title, year=year, date_label=None, summary=f"{title}.", wiki_url=canonical_url(title),
            lat=lat, lon=lon, category=Category.MILITARY, status=Status.APPROVED,
        ) for title, year, lat, lon in EVENTS)
        db.session.commit()
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="session")
def chromium():
    if sync_api is None:
        pytest.skip("Playwright is not installed")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:  # no browser installed for Playwright
            pytest.skip(f"Chromium for Playwright is not installed: {exc}")
        yield browser
        browser.close()
