"""Browser tests: the real app on a free port, a small offline database, Chromium.

Every test fails if the page logs a console error or throws. Requests to other
sites are blocked, except the CDNs the pages load Leaflet and friends from (their
responses are cached for the whole run); map tiles get a blank image, so the
tests never depend on a tile server.
"""

import logging
import threading
from pathlib import Path
from urllib.parse import urlparse

import pytest
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

from haam import create_app
from haam.config import CONFIGS, TestingConfig
from haam.extensions import db
from tests.conftest import FakeWikipedia
from tests.e2e import seed_data

ADMIN_PASSWORD = "e2e admin password"

E2E_DIR = Path(__file__).parent
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
CDN_HOSTS = {"unpkg.com", "cdnjs.cloudflare.com"}
TILE_HOSTS = ("tile.openstreetmap.org", "server.arcgisonline.com")
# A 1×1 transparent PNG.
BLANK_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


# ------------------------------------------------------------ collection

def _chromium_installed() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists() or _headless_shell_installed(p)
    except Exception:
        return False


def _headless_shell_installed(p) -> bool:
    # `playwright install --only-shell chromium` installs only the headless shell,
    # which is what headless runs use; executable_path names the full browser.
    browsers = Path(p.chromium.executable_path).parents
    root = next((d for d in browsers if d.name.startswith("chromium-")), None)
    return root is not None and any(root.parent.glob("chromium_headless_shell-*"))


def pytest_collection_modifyitems(config, items):
    e2e_items = [item for item in items if E2E_DIR in Path(str(item.fspath)).parents]
    for item in e2e_items:
        item.add_marker(pytest.mark.e2e)
    if e2e_items and not _chromium_installed():
        skip = pytest.mark.skip(reason="Chromium for Playwright is not installed: "
                                       "python -m playwright install chromium")
        for item in e2e_items:
            item.add_marker(skip)


# ---------------------------------------------------------------- server

class E2EConfig(TestingConfig):
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # replaced in live_server
    WTF_CSRF_ENABLED = True  # the real forms, tokens included
    ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """The app with a fresh SQLite file, served from a background thread."""
    db_path = tmp_path_factory.mktemp("e2e") / "haam.db"
    E2EConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.as_posix()}"
    CONFIGS["e2e"] = E2EConfig
    try:
        app = create_app("e2e")
    finally:
        CONFIGS.pop("e2e")
    app.extensions["haam_wikipedia"] = FakeWikipedia()  # never fetch anything
    with app.app_context():
        db.create_all()
        seed = seed_data.build()

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.url = f"http://127.0.0.1:{server.server_port}"
    server.seed = seed
    yield server
    server.shutdown()
    thread.join(timeout=5)
    with app.app_context():
        db.engine.dispose()


@pytest.fixture(scope="session")
def base_url(live_server):
    return live_server.url


@pytest.fixture(scope="session")
def seed(live_server) -> seed_data.Seed:
    return live_server.seed


# ------------------------------------------------------- network and console

_cdn_cache: dict[str, tuple[int, dict, bytes]] = {}


def _route(route):
    url = route.request.url
    host = urlparse(url).hostname or ""
    if host in LOCAL_HOSTS or url.startswith("data:"):
        route.continue_()
    elif host.endswith(TILE_HOSTS):
        route.fulfill(status=200, content_type="image/png", body=BLANK_PNG,
                      headers={"Access-Control-Allow-Origin": "*"})
    elif host in CDN_HOSTS:
        if url not in _cdn_cache:
            response = route.fetch()
            _cdn_cache[url] = (response.status, response.headers, response.body())
        status, headers, body = _cdn_cache[url]
        route.fulfill(status=status, headers=headers, body=body)
    else:
        route.abort()  # shows up as a console error, so the test fails


class ConsoleErrors:
    def __init__(self):
        self.errors: list[str] = []

    def watch(self, context):
        context.route("**/*", _route)
        context.on("console", self._on_console)
        context.on("weberror", lambda error: self.errors.append(f"uncaught: {error.error}"))
        return context

    def _on_console(self, message):
        if message.type == "error":
            location = message.location or {}
            self.errors.append(f"{message.text} ({location.get('url', '?')}:{location.get('lineNumber', '?')})")


@pytest.fixture
def console_errors():
    errors = ConsoleErrors()
    yield errors
    assert not errors.errors, "Browser console errors:\n" + "\n".join(errors.errors)


@pytest.fixture
def context(new_context, console_errors):
    return console_errors.watch(new_context())


@pytest.fixture
def fresh_context(new_context, console_errors):
    """Another browser context (no cookies, no storage), e.g. someone opening a shared link."""
    return lambda: console_errors.watch(new_context())


@pytest.fixture(autouse=True)
def _timeouts(context):
    context.set_default_timeout(10_000)
