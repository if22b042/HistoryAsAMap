import json
from datetime import date, timedelta

import pytest

from haam import game
from haam.models import Category, Status

LONG = "The event was important. " * 20  # passes MIN_SUMMARY_LENGTH

# Spread in time, space and category, like real data.
PLACES = [
    ("Battle of Marathon", -490, 38.1, 23.97, Category.MILITARY, "Greece"),
    ("Battle of Hastings", 1066, 50.91, 0.49, Category.MILITARY, "United Kingdom"),
    ("Treaty of Tordesillas", 1494, 41.52, -5.0, Category.DIPLOMATIC, "Spain"),
    ("Siege of Malacca", 1511, 2.19, 102.25, Category.MILITARY, "Malaysia"),
    ("Battle of Trafalgar", 1805, 36.18, -6.03, Category.NAVAL, "Spain"),
    ("1906 San Francisco earthquake", 1906, 37.75, -122.55, Category.NATURAL, "United States"),
    ("Battle of Midway", 1942, 28.2, -177.35, Category.NAVAL, None),
    ("Battle of Red Cliffs", 208, 29.88, 113.6, Category.NAVAL, "China"),
    ("Battle of Talas", 751, 42.52, 72.24, Category.MILITARY, "Kazakhstan"),
    ("Great Fire of London", 1666, 51.51, -0.09, Category.NATURAL, "United Kingdom"),
    ("Apollo 11", 1969, 28.57, -80.65, Category.SCIENTIFIC, "United States"),
]


@pytest.fixture
def events(make_event):
    made = [
        make_event(title, year=year, lat=lat, lon=lon, category=category, country=country,
                   summary=f"The {title} took place in {country or 'the Pacific'}. {LONG}")
        for title, year, lat, lon, category, country in PLACES
    ]
    make_event("Too short", year=1500, summary="Short.")
    make_event("Pending one", year=1600, status=Status.PENDING, summary=LONG)
    return made


def _today():
    return game.today_utc().isoformat()


# ---------------------------------------------------------------- picking

def test_same_day_gives_the_same_events(app, events):
    day = date(2026, 11, 10)
    first = game.daily_event_ids(day)
    app.extensions["haam_game_cache"].clear()
    assert game.daily_event_ids(day) == first
    assert len(first) == game.EVENTS_PER_DAY == len(set(first))


def test_different_days_give_different_events(app, events):
    picks = {tuple(game.daily_event_ids(date(2026, 11, 1) + timedelta(days=i))) for i in range(10)}
    assert len(picks) > 1


def test_pick_skips_short_and_unapproved_events(app, events):
    titles = {e.title for d in range(20) for e in game.daily_events(date(2026, 11, 1) + timedelta(days=d))}
    assert "Too short" not in titles and "Pending one" not in titles


def test_pick_spreads_eras_and_categories(app, events):
    for d in range(10):
        picked = game.daily_events(date(2026, 11, 1) + timedelta(days=d))
        assert len({game._era(e.year) for e in picked}) == len(game.ERAS)
        for category in Category:
            assert sum(e.category == category for e in picked) <= game.MAX_PER_CATEGORY


def test_pick_with_few_events(app, make_event):
    assert game.daily_event_ids(date(2026, 11, 10)) == []
    make_event("Only one", summary=LONG)
    app.extensions["haam_game_cache"].clear()
    assert len(game.daily_event_ids(date(2026, 11, 10))) == 1


# ---------------------------------------------------------------- scoring

def test_haversine():
    assert game.haversine_km(0, 0, 0, 0) == 0
    # Paris – London is about 344 km.
    assert game.haversine_km(48.8566, 2.3522, 51.5074, -0.1278) == pytest.approx(344, abs=3)
    # Across the antimeridian.
    assert game.haversine_km(0, 179.5, 0, -179.5) == pytest.approx(111.2, abs=1)


def test_score_distance():
    assert game.score_distance(0) == game.MAX_POINTS
    assert game.score_distance(game.FULL_KM) == game.MAX_POINTS
    assert game.score_distance(500) == pytest.approx(500, abs=15)
    assert game.score_distance(game.ZERO_KM) == 0
    assert game.score_distance(15000) == 0
    scores = [game.score_distance(km) for km in range(0, 3200, 50)]
    assert scores == sorted(scores, reverse=True)


def test_normalize_lon():
    assert game.normalize_lon(370) == pytest.approx(10)
    assert game.normalize_lon(-190) == pytest.approx(170)


# ---------------------------------------------------------------- API

def test_puzzle_hides_the_answers(client, events):
    response = client.get("/api/game/today")
    assert response.status_code == 200
    data = response.json
    assert data["date"] == _today() and data["is_today"]
    assert len(data["rounds"]) == game.EVENTS_PER_DAY
    for round_ in data["rounds"]:
        assert set(round_) == {"index", "title", "date", "year", "excerpt", "category"}
    raw = response.get_data(as_text=True)
    for event in events:
        assert f'"id": {event.id},' not in raw and f'"id":{event.id},' not in raw
        assert event.wiki_url not in raw
        if event.country:
            assert event.country not in json.dumps([r["excerpt"] for r in data["rounds"]])


def test_puzzle_for_a_date_matches_today(client, events):
    assert client.get(f"/api/game/{_today()}").json["rounds"] == client.get("/api/game/today").json["rounds"]


@pytest.mark.parametrize("value", ["2026-10-31", "tomorrow", "2026-13-01"])
def test_puzzle_unknown_days(client, events, value):
    assert client.get(f"/api/game/{value}").status_code == 404


def test_puzzle_future_day(client, events):
    tomorrow = (game.today_utc() + timedelta(days=1)).isoformat()
    assert client.get(f"/api/game/{tomorrow}").status_code == 404


def test_past_day_is_playable(client, events):
    data = client.get(f"/api/game/{game.EPOCH.isoformat()}").json
    assert data["number"] == 1 and data["previous"] is None and not data["is_today"]


def test_check_scores_and_reveals(app, client, events):
    event = game.daily_events(game.today_utc())[0]
    response = client.post("/api/game/check", json={
        "date": _today(), "index": 0, "lat": event.lat, "lon": event.lon + 360})
    assert response.status_code == 200
    data = response.json
    assert data["points"] == game.MAX_POINTS and data["km"] == pytest.approx(0, abs=0.1)
    assert data["answer"]["id"] == event.id
    assert data["answer"]["lat"] == event.lat and data["answer"]["wiki_url"] == event.wiki_url
    assert data["answer"]["map_url"] == f"/?event={event.id}"


def test_check_far_guess(client, events):
    event = game.daily_events(game.today_utc())[1]
    data = client.post("/api/game/check", json={
        "date": _today(), "index": 1, "lat": -event.lat, "lon": game.normalize_lon(event.lon + 180)}).json
    assert data["points"] == 0 and data["km"] > 15000


@pytest.mark.parametrize("body", [
    {"index": 0, "lat": 0, "lon": 0},
    {"date": "today", "index": "0", "lat": 0, "lon": 0},
    {"date": "today", "index": 0, "lat": 95, "lon": 0},
    {"date": "today", "index": 0, "lat": True, "lon": 0},
    {"date": "today", "index": 0, "lat": "1", "lon": 0},
])
def test_check_rejects_bad_input(client, events, body):
    assert client.post("/api/game/check", json=body).status_code == 400


def test_check_index_out_of_range(client, events):
    response = client.post("/api/game/check", json={"date": "today", "index": 5, "lat": 0, "lon": 0})
    assert response.status_code == 404


def test_game_page_and_nav(client):
    html = client.get("/game").get_data(as_text=True)
    assert 'id="game-map"' in html and "js/game.js" in html
    assert 'href="/game"' in client.get("/about").get_data(as_text=True)


# ---------------------------------------------------------------- clues

def test_excerpt_hides_country(app, make_event):
    event = make_event("Battle of Somewhere", country="France",
                       summary="The battle was fought in northern France in spring. " + LONG)
    text = game.excerpt(event)
    assert "France" not in text and game.HIDDEN in text
    assert len(text) <= game.EXCERPT_MAX + 1


def test_excerpt_hides_nationalities(app, make_event):
    event = make_event(
        "Siege of Tarragona (1813)", year=1813, country="Kingdom of Spain",
        summary="In the siege of Tarragona, an Anglo-Allied force failed to capture the Spanish "
                "port of Tarragona from a small Franco-Italian garrison. The Romans and the "
                "turkey stayed. " + LONG)
    text = game.excerpt(event)
    for word in ("Spanish", "Anglo-Allied", "Franco-Italian", "Romans"):
        assert word not in text
    assert "port of Tarragona" in text and "turkey" in text


def test_game_tiles_are_allowed_by_csp(client):
    assert "https://server.arcgisonline.com" in client.get("/game").headers["Content-Security-Policy"]


# ---------------------------------------------------------------- practice

def test_practice_set_hides_the_answers(client, events):
    data = client.get("/api/game/practice").json
    assert game.SEED_PATTERN.fullmatch(data["seed"])
    assert len(data["rounds"]) == game.EVENTS_PER_DAY
    raw = json.dumps(data)
    for event in events:
        assert event.wiki_url not in raw
    for round_ in data["rounds"]:
        assert set(round_) == {"index", "title", "date", "year", "excerpt", "category"}


def test_practice_sets_are_random(client, events):
    seeds = {client.get("/api/game/practice").json["seed"] for _ in range(3)}
    assert len(seeds) == 3


def test_practice_ranking_needs_the_secret_key(app):
    """The pick is keyed with SECRET_KEY: the seed and the code alone do not give the set."""
    seed = "0" * 32
    ranks = [game._practice_rank(seed, event_id) for event_id in range(1, 50)]
    assert ranks == [game._practice_rank(seed, event_id) for event_id in range(1, 50)]
    app.config["SECRET_KEY"] = "another secret"
    assert ranks != [game._practice_rank(seed, event_id) for event_id in range(1, 50)]


def test_practice_filters(client, events):
    data = client.get("/api/game/practice?category=naval").json
    assert data["rounds"] and {r["category"] for r in data["rounds"]} == {"naval"}
    data = client.get("/api/game/practice?era=0").json
    assert data["rounds"] and all(r["year"] < 500 for r in data["rounds"])
    data = client.get("/api/game/practice?era=0&category=scientific").json
    assert data["rounds"] == []


@pytest.mark.parametrize("query", ["era=9", "era=x", "category=pirates"])
def test_practice_rejects_bad_filters(client, events, query):
    assert client.get(f"/api/game/practice?{query}").status_code == 400


def test_practice_check_scores_the_same_set(client, events):
    data = client.get("/api/game/practice?category=naval").json
    by_title = {e.title: e for e in events}
    for round_ in data["rounds"]:
        event = by_title[round_["title"]]
        result = client.post("/api/game/practice/check", json={
            "seed": data["seed"], "era": None, "category": "naval",
            "index": round_["index"], "lat": event.lat, "lon": event.lon}).json
        assert result["points"] == game.MAX_POINTS
        assert result["answer"]["title"] == round_["title"]


@pytest.mark.parametrize("body", [
    {"index": 0, "lat": 0, "lon": 0},
    {"seed": "not-a-seed", "index": 0, "lat": 0, "lon": 0},
    {"seed": "a" * 32, "era": 7, "index": 0, "lat": 0, "lon": 0},
    {"seed": "a" * 32, "category": "pirates", "index": 0, "lat": 0, "lon": 0},
])
def test_practice_check_rejects_bad_input(client, events, body):
    assert client.post("/api/game/practice/check", json=body).status_code == 400


def test_practice_route_is_not_a_day(client, events):
    assert "seed" in client.get("/api/game/practice").json
