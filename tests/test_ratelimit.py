from haam import ratelimit
from haam.extensions import db
from haam.models import RateLimitHit

from tests.conftest import ADMIN_PASSWORD


def test_limits_are_off_while_testing(client):
    for _ in range(8):
        assert client.post("/admin/login", data={"username": "admin", "password": "x"}).status_code == 200
    assert db.session.scalar(db.select(db.func.count(RateLimitHit.id))) == 0


def test_login_is_limited_to_five_a_minute(app, client):
    app.config["RATELIMIT_ENABLED"] = True
    for _ in range(5):
        assert client.post("/admin/login", data={"username": "admin", "password": "x"}).status_code == 200
    blocked = client.post("/admin/login", data={"username": "admin", "password": ADMIN_PASSWORD})
    assert blocked.status_code == 429
    assert b"Too many requests" in blocked.data
    assert client.get("/admin/login").status_code == 200  # only attempts count, not looking at the page
    # Another client is not affected.
    other = client.post("/admin/login", data={"username": "admin", "password": ADMIN_PASSWORD},
                        headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"})
    assert other.status_code == 302


def test_json_clients_get_json(app, client):
    app.config["RATELIMIT_ENABLED"] = True
    for _ in range(60):
        client.get("/api/game/practice")
    response = client.get("/api/game/practice", headers={"Accept": "application/json"})
    assert response.status_code == 429
    assert "error" in response.json


def test_window_resets_and_old_rows_are_pruned(app, monkeypatch):
    with app.test_request_context(headers={"X-Forwarded-For": "198.51.100.7"}):
        assert [ratelimit.hit("demo", 60, now=1000.0) for _ in range(3)] == [1, 2, 3]
        assert ratelimit.hit("demo", 60, now=1060.0) == 1  # the next window
        monkeypatch.setattr(ratelimit, "PRUNE_CHANCE", 1.0)
        ratelimit.hit("demo", 60, now=1060.0 + ratelimit.KEEP_SECONDS + 120)
        assert db.session.scalar(db.select(db.func.count(RateLimitHit.id))) == 1
        row = db.session.scalar(db.select(RateLimitHit))
        assert "198.51.100.7" not in row.client_hash  # only a hash is stored
