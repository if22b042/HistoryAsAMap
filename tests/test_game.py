import json
from datetime import date, timedelta

import pytest

from haam import game
from haam.events import public_id
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
                   summary=f"The {title} took place in {country or 'the Pacific'}. {LONG}",
                   wiki_page_id=60_000 + n)  # page ids, as in the real data: they differ from the row ids
        for n, (title, year, lat, lon, category, country) in enumerate(PLACES)
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
    assert game.score_distance(game.HALF_KM) == pytest.approx(game.MAX_POINTS / 2, abs=75)
    assert game.score_distance(game.ZERO_KM) == 0
    assert game.score_distance(15000) == 0
    assert game.score_distance(500) > 0.65 * game.MAX_POINTS
    scores = [game.score_distance(km) for km in range(0, 6200, 50)]
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
    assert data["answer"]["id"] == public_id(event)
    assert data["answer"]["lat"] == event.lat and data["answer"]["wiki_url"] == event.wiki_url
    assert data["answer"]["map_url"] == f"/?event={public_id(event)}"


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
    assert "France" not in text and "[Western Europe]" in text
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
    # Words with a known region name it; compounds without one stay a plain blank.
    assert "[Southern Europe] port" in text and "[Mediterranean]" in text and game.HIDDEN in text


def test_game_tiles_are_allowed_by_csp(client):
    assert "https://server.arcgisonline.com" in client.get("/game").headers["Content-Security-Policy"]


def test_all_base_map_tiles_are_allowed_by_csp(client):
    csp = client.get("/").headers["Content-Security-Policy"]
    for host in ("https://tile.openstreetmap.org", "https://*.tile.opentopomap.org",
                 "https://server.arcgisonline.com"):
        assert host in csp


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


# ---------------------------------------------------------------- titles

@pytest.mark.parametrize("title, country, expected", [
    ("Siege of Malta (1429)", None, True),
    ("Battle of the Gulf of Oman", None, True),
    ("Ottoman Empire–Persia treaty", None, True),
    ("Siege of Mons", "Kingdom of the Netherlands", False),
    ("Battle of Saint-Denis", "Kingdom of France", False),
    ("Battle of Spain Hill", "Kingdom of Spain", True),
    ("German bombardment of Monrovia", "Liberia", False),
    ("Ottoman conquest of Lesbos", None, False),
    ("Battle of Hastings", "United Kingdom", False),
    ("Siege of Hastings", "Hastings Republic", False),
])
def test_names_a_country(title, country, expected):
    assert game.names_a_country(title, country) is expected


def test_titles_naming_a_country_are_never_picked(app, events, make_event):
    for title, lat, lon in [("Siege of Malta", 35.9, 14.5), ("1755 Portugal earthquake", 38.7, -9.1)]:
        make_event(title, year=1500, lat=lat, lon=lon, summary=LONG)
    days = [date(2026, 11, 1) + timedelta(days=d) for d in range(15)]
    titles = {e.title for day in days for e in game.daily_events(day)}
    titles |= {e.title for _ in range(10) for e in game.practice_events(game.new_practice_seed(), era=2)}
    assert "Siege of Malta" not in titles and "1755 Portugal earthquake" not in titles


# ---------------------------------------------------------------- hard mode

@pytest.mark.parametrize("text, expected", [
    ("fought on Sunday 18 June 1815, near Waterloo", "fought on Sunday 18 June ____, near Waterloo"),
    ("the American Revolutionary War (1775–1783)", "the American Revolutionary War (____)"),
    ("in the 5th century BC", "in ____"),
    ("in the late nineteenth century", "in ____"),
    ("in 424 BC between", "in ____ between"),
    ("circa AD 60–61 in", "circa ____ in"),
    ("in the 1640s", "in ____"),
    ("dated to 232 CE ± 10", "dated to ____ ± 10"),
    ("on February 5, 1918.", "on February 5, ____."),
    ("in 960 the", "in ____ the"),
    ("between 1309 and 1310", "between ____"),
    # Not years: quantities, names, small numbers.
    ("SM U-154 attacked", "SM U-154 attacked"),
    ("killing 53 to 62 prisoners", "killing 53 to 62 prisoners"),
    ("1,500 men and 2.5 km", "1,500 men and 2.5 km"),
])
def test_hide_years(text, expected):
    assert game.hide_years(text) == expected


@pytest.mark.parametrize("title, expected", [
    ("Siege of London (1471)", "Siege of London"),
    ("Siege of Algeciras (1309–1310)", "Siege of Algeciras"),
    ("1755 Lisbon earthquake", "____ Lisbon earthquake"),
    ("Action of 13 March 1806", "Action of 13 March ____"),
    ("Battle of Hastings", "Battle of Hastings"),
])
def test_hard_title(title, expected):
    assert game.hard_title(title) == expected


@pytest.mark.parametrize("error, share", [
    (0, 1), (50, 1 / 2), (100, 1 / 3), (200, 1 / 5), (500, 0), (2000, 0),
    # Linear between the anchors.
    (25, 3 / 4), (150, (1 / 3 + 1 / 5) / 2), (350, 1 / 10),
])
def test_year_share_anchors(error, share):
    assert game.year_share(error) == pytest.approx(share)


def test_year_scoring():
    full = game.HARD_YEAR_POINTS
    assert game.score_year(1813, 1813) == full
    assert game.score_year(1863, 1813) == full / 2
    assert game.score_year(1713, 1813) == round(full / 3)
    assert game.score_year(2013, 1813) == round(full / 5)
    assert game.score_year(1313, 1813) == 0
    # Years, not ages: the same error scores the same in any era.
    assert game.score_year(-1050, -1000) == game.score_year(1863, 1813)
    scores = [game.score_year(1813 + d, 1813) for d in range(0, 600, 10)]
    assert scores == sorted(scores, reverse=True)
    # There is no year 0: 1 BC and AD 1 are one year apart.
    assert game.year_error(-1, 1) == 1 and game.year_error(-44, 1) == 44


def test_hard_location_points_are_half():
    assert game.score_hard_location(0) == game.HARD_LOCATION_POINTS
    assert game.score_hard_location(500) == round(game.score_distance(500) / 2)


def test_hard_puzzle_hides_the_years(client, events):
    normal = client.get("/api/game/today").json
    hard = client.get("/api/game/today?hard=1").json
    assert hard["hard"] and not normal["hard"]
    assert len(hard["rounds"]) == len(normal["rounds"])
    for round_ in hard["rounds"]:
        assert round_["year"] is None and round_["date"] is None
    raw = json.dumps(hard["rounds"])
    for event in events:
        assert str(abs(event.year)) not in raw


def test_hard_daily_events_differ_from_normal(app, events):
    for d in range(10):
        day = date(2026, 11, 1) + timedelta(days=d)
        normal, hard = game.daily_event_ids(day), game.daily_event_ids(day, hard=True)
        assert len(hard) == game.EVENTS_PER_DAY and not set(normal) & set(hard)
        app.extensions["haam_game_cache"].clear()
        assert game.daily_event_ids(day, hard=True) == hard  # still deterministic


def test_hard_check_uses_the_hard_events(client, events):
    normal = game.daily_events(game.today_utc())[0]
    hard = game.daily_events(game.today_utc(), hard=True)[0]
    body = {"date": "today", "index": 0, "lat": hard.lat, "lon": hard.lon}
    assert client.post("/api/game/check", json={**body, "hard": True, "year": hard.year}).json["answer"]["id"] == public_id(hard)
    assert client.post("/api/game/check", json=body).json["answer"]["id"] == public_id(normal)


def test_hard_check_scores_place_and_year(client, events):
    event = game.daily_events(game.today_utc(), hard=True)[0]
    body = {"date": "today", "index": 0, "lat": event.lat, "lon": event.lon, "hard": True}
    assert client.post("/api/game/check", json=body).status_code == 400  # year missing
    result = client.post("/api/game/check", json={**body, "year": event.year}).json
    assert result["points"] == game.MAX_POINTS
    assert result["location_points"] == game.HARD_LOCATION_POINTS
    assert result["year_points"] == game.HARD_YEAR_POINTS and result["year_error"] == 0
    assert result["answer"]["year"] == event.year
    off = client.post("/api/game/check", json={**body, "year": event.year - 200}).json
    assert off["location_points"] == game.HARD_LOCATION_POINTS
    assert off["year_points"] < game.HARD_YEAR_POINTS and off["year_error"] == 200


@pytest.mark.parametrize("year", [0, True, "1066", 99999, 1.5])
def test_hard_check_rejects_bad_years(client, events, year):
    body = {"date": "today", "index": 0, "lat": 0, "lon": 0, "hard": True, "year": year}
    assert client.post("/api/game/check", json=body).status_code == 400


def test_hard_practice(client, events):
    data = client.get("/api/game/practice?hard=1").json
    assert data["hard"] and all(r["year"] is None for r in data["rounds"])
    by_title = {game.hard_title(e.title): e for e in events}
    event = by_title[data["rounds"][0]["title"]]
    result = client.post("/api/game/practice/check", json={
        "seed": data["seed"], "index": 0, "lat": event.lat, "lon": event.lon,
        "hard": True, "year": event.year}).json
    assert result["points"] == game.MAX_POINTS


# ---------------------------------------------------------------- fixed daily game

def test_daily_game_is_stored_and_fixed(app, events, make_event):
    from haam.extensions import db
    from haam.models import DailyGame

    day = date(2026, 11, 10)
    first = game.daily_event_ids(day)
    row = db.session.query(DailyGame).one()
    assert (row.date, row.hard) == (day, False) and len(json.loads(row.refs)) == game.EVENTS_PER_DAY
    # New events and a cold cache (another server instance) do not change the day.
    for i in range(30):
        make_event(f"Another battle {i}", year=100 + i * 60, summary=LONG)
    app.extensions["haam_game_cache"].clear()
    assert game.daily_event_ids(day) == first


def test_daily_game_refs_use_page_id_with_row_id_fallback(app, make_event):
    from haam.extensions import db
    from haam.models import DailyGame

    with_page = make_event("With page", year=1000, summary=LONG, wiki_page_id=4242)
    without = make_event("Without page", year=1900, summary=LONG, lat=-30, lon=150)
    day = date(2026, 11, 11)
    game.daily_event_ids(day)
    refs = json.loads(db.session.query(DailyGame).one().refs)
    assert f"p{with_page.wiki_page_id}" in refs and f"i{without.id}" in refs


def test_daily_game_survives_a_reimport(app, make_event):
    """Row ids change on re-import; the stored page ids still find the events."""
    from haam.extensions import db
    from haam.models import Event

    for i in range(6):
        make_event(f"Event {i}", year=-600 + i * 400, summary=LONG, wiki_page_id=1000 + i,
                   lat=i * 20, lon=i * 40 - 100)
    day = date(2026, 11, 12)
    before = [e.title for e in game.daily_events(day)]
    assert before
    db.session.execute(Event.__table__.update().values(id=Event.id + 500))
    db.session.commit()
    app.extensions["haam_game_cache"].clear()
    assert [e.title for e in game.daily_events(day)] == before


def test_daily_game_skips_a_deleted_event(app, events):
    from haam.extensions import db

    day = date(2026, 11, 10)
    picked = game.daily_events(day)
    titles = [e.title for e in picked]
    db.session.delete(picked[1])
    db.session.commit()
    app.extensions["haam_game_cache"].clear()
    assert [e.title for e in game.daily_events(day)] == [t for i, t in enumerate(titles) if i != 1]


def db_events(ids):
    from haam.extensions import db
    from haam.models import Event
    return [db.session.get(Event, i) for i in ids]


def test_daily_game_race_reads_the_winning_row(app, events, monkeypatch):
    from haam.extensions import db
    from haam.models import DailyGame

    day = date(2026, 11, 10)
    real = game._compute_daily_ids
    winner_ids = real(day, False)[:2]
    winner = [f"p{e.wiki_page_id}" for e in db_events(winner_ids)]

    def racing(day_, hard):
        ids = real(day_, hard)
        db.session.add(DailyGame(date=day_, hard=hard, refs=json.dumps(winner)))  # another instance won
        db.session.commit()
        return ids

    monkeypatch.setattr(game, "_compute_daily_ids", racing)
    assert game.daily_event_ids(day) == winner_ids
    assert db.session.query(DailyGame).count() == 1


def test_hard_game_is_stored_separately(app, events):
    from haam.extensions import db
    from haam.models import DailyGame

    day = date(2026, 11, 10)
    normal, hard = game.daily_event_ids(day), game.daily_event_ids(day, hard=True)
    assert not set(normal) & set(hard)
    assert {r.hard for r in db.session.query(DailyGame)} == {False, True}


# ---------------------------------------------------------------- daily scores

def test_score_is_recorded_and_averaged(client, events):
    day = _today()
    assert client.get("/api/game/today").json["stats"] == {"count": 0, "average": None}
    first = client.post("/api/game/score", json={"date": day, "hard": False, "points": 3000})
    assert first.status_code == 200 and first.json["stats"] == {"count": 1, "average": 3000}
    second = client.post("/api/game/score", json={"date": day, "points": 4000})
    assert second.json["stats"] == {"count": 2, "average": 3500}
    assert client.get("/api/game/today").json["stats"]["count"] == 2
    # The hard game has its own scores.
    assert client.get("/api/game/today?hard=1").json["stats"]["count"] == 0


@pytest.mark.parametrize("body", [
    {"date": "today", "points": 25001},
    {"date": "today", "points": -1},
    {"date": "today", "points": 10.5},
    {"date": "today", "points": True},
    {"date": "today", "points": "100"},
    {"date": "today", "points": 100, "hard": "yes"},
    {"points": 100},
])
def test_score_rejects_bad_input(client, events, body):
    assert client.post("/api/game/score", json=body).status_code == 400


def test_score_for_a_future_day(client, events):
    tomorrow = (game.today_utc() + timedelta(days=1)).isoformat()
    assert client.post("/api/game/score", json={"date": tomorrow, "points": 10}).status_code == 404


# ---------------------------------------------------------------- challenge a friend

def test_practice_with_a_seed_gives_the_same_set(client, events):
    first = client.get("/api/game/practice").json
    again = client.get(f"/api/game/practice?seed={first['seed']}").json
    assert again["seed"] == first["seed"] and again["rounds"] == first["rounds"]


@pytest.mark.parametrize("seed", ["abc", "G" * 32, "0" * 31, ""])
def test_practice_rejects_a_bad_seed(client, events, seed):
    assert client.get(f"/api/game/practice?seed={seed}").status_code == 400


# ---------------------------------------------------------------- quiz from a collection

@pytest.fixture
def quiz_collection(app, events):
    from haam import collections_service as cs

    collection, _ = cs.create_collection("Quiz me", "", True)
    for event in events[:6]:
        cs.add_event(collection, event.id, "")
    return collection


def test_practice_from_a_collection(client, events, quiz_collection):
    data = client.get(f"/api/game/practice?collection={quiz_collection.view_token}").json
    in_collection = {e.title for e in events[:6]}
    assert len(data["rounds"]) == game.EVENTS_PER_DAY
    assert {r["title"] for r in data["rounds"]} <= in_collection
    by_title = {e.title: e for e in events}
    for round_ in data["rounds"]:
        event = by_title[round_["title"]]
        result = client.post("/api/game/practice/check", json={
            "seed": data["seed"], "collection": quiz_collection.view_token,
            "index": round_["index"], "lat": event.lat, "lon": event.lon})
        assert result.status_code == 200 and result.json["answer"]["title"] == event.title


def test_collection_quiz_needs_five_events(client, events, quiz_collection):
    from haam import collections_service as cs

    small, _ = cs.create_collection("Small", "", False)
    for event in events[:4]:
        cs.add_event(small, event.id, "")
    data = client.get(f"/api/game/practice?collection={small.view_token}").json
    assert data["rounds"] == [] and "at least 5" in data["message"]


def test_collection_quiz_counts_only_approved_events(app, client, events):
    from haam import collections_service as cs
    from haam.extensions import db

    collection, _ = cs.create_collection("Mixed", "", True)
    for event in events[:5]:
        cs.add_event(collection, event.id, "")
    assert len(client.get(f"/api/game/practice?collection={collection.view_token}").json["rounds"]) == 5
    events[0].status = Status.PENDING
    db.session.commit()
    assert client.get(f"/api/game/practice?collection={collection.view_token}").json["rounds"] == []


def test_collection_quiz_unknown_or_hidden(client, events, quiz_collection):
    from haam import collections_service as cs

    assert client.get("/api/game/practice?collection=nope").status_code == 404
    cs.set_hidden(quiz_collection, True)
    assert client.get(f"/api/game/practice?collection={quiz_collection.view_token}").status_code == 404


def test_collection_page_links_to_the_quiz(client, quiz_collection):
    html = client.get(f"/collections/{quiz_collection.view_token}").get_data(as_text=True)
    assert f"mode=practice&amp;collection={quiz_collection.view_token}" in html


# ---------------------------------------------------------------- which came first

@pytest.fixture
def many_events(make_event):
    return [
        make_event(f"Event number {i}", year=800 + i * 40, summary=f"Something happened in {800 + i * 40}. " + LONG,
                   lat=i, lon=i, date_label=str(800 + i * 40))
        for i in range(30)
    ]


def test_pairs_hide_the_years_and_ids(client, many_events):
    response = client.get("/api/game/pairs")
    data = response.json
    assert game.SEED_PATTERN.fullmatch(data["seed"]) and len(data["rounds"]) == game.PAIRS_PER_SET
    for round_ in data["rounds"]:
        assert set(round_) == {"index", "a", "b"}
        for side in (round_["a"], round_["b"]):
            assert set(side) == {"title", "excerpt", "category"}
            assert not any(ch.isdigit() for ch in side["excerpt"])
    raw = response.get_data(as_text=True)
    assert '"id"' not in raw and '"lat"' not in raw and '"year"' not in raw


def test_pairs_are_five_to_three_hundred_years_apart(app, many_events):
    pairs = game.pair_events("0" * 32)
    assert len(pairs) == game.PAIRS_PER_SET
    ids = [e.id for pair in pairs for e in pair]
    assert len(ids) == len(set(ids))
    for first, second in pairs:
        assert game.MIN_GAP_YEARS <= abs(first.year - second.year) <= game.MAX_GAP_YEARS


def test_pairs_same_seed_same_pairs(client, many_events):
    seed = client.get("/api/game/pairs").json["seed"]
    assert client.get(f"/api/game/pairs?seed={seed}").json == client.get(f"/api/game/pairs?seed={seed}").json
    assert client.get("/api/game/pairs?seed=zz").status_code == 400


def test_pairs_check_reveals_both_dates(client, many_events):
    data = client.get("/api/game/pairs").json
    seed = data["seed"]
    by_title = {e.title: e for e in many_events}
    for round_ in data["rounds"]:
        a, b = by_title[round_["a"]["title"]], by_title[round_["b"]["title"]]
        earlier = 0 if a.year < b.year else 1
        right = client.post("/api/game/pairs/check", json={"seed": seed, "index": round_["index"], "choice": earlier})
        assert right.status_code == 200 and right.json["correct"] is True and right.json["earlier"] == earlier
        assert right.json["a"]["date"] == a.date_label and right.json["b"]["date"] == b.date_label
        wrong = client.post("/api/game/pairs/check", json={"seed": seed, "index": round_["index"], "choice": 1 - earlier})
        assert wrong.json["correct"] is False


@pytest.mark.parametrize("body", [
    {"index": 0, "choice": 0},
    {"seed": "0" * 32, "index": "0", "choice": 0},
    {"seed": "0" * 32, "index": 0, "choice": 2},
    {"seed": "0" * 32, "index": 0, "choice": True},
])
def test_pairs_check_rejects_bad_input(client, many_events, body):
    assert client.post("/api/game/pairs/check", json=body).status_code == 400


def test_pairs_check_index_out_of_range(client, many_events):
    assert client.post("/api/game/pairs/check", json={"seed": "0" * 32, "index": 10, "choice": 0}).status_code == 404


def test_pairs_without_events(client):
    assert client.get("/api/game/pairs").json["rounds"] == []


# ---------------------------------------------------------------- clues: regions and stems

def test_excerpt_names_regions_instead_of_blanks(app, make_event):
    event = make_event("Siege of Somewhere", country="Philippines",
                       summary="Troops of the Philippine National Police and the Armed Forces of the "
                               "Philippines took part. The Ottoman Turks and the British watched. " + LONG)
    text = game.excerpt(event)
    assert "Philippine" not in text
    assert text.count("[Southeast Asia]") == 2
    assert "[Middle East]" in text and "[British Isles]" in text
    assert "[[" not in text  # a label is never matched again by a later pass


def test_excerpt_merges_one_region_and_never_cuts_a_label(app, make_event):
    event = make_event("Siege of Somewhere", summary="The Ottoman Turks marched. " + LONG)
    assert game.excerpt(event).startswith("The [Middle East] marched.")
    long_text = "Word " * 59 + "the Spanish troops of Spain. " + LONG
    text = game.excerpt(make_event("Siege of Elsewhere", summary=long_text))
    assert text.count("[") == text.count("]") and len(text) <= game.EXCERPT_MAX + 1


@pytest.mark.parametrize("country, word", [
    ("Tunisia", "Tunisian"), ("Philippines", "Philippine"), ("Sri Lanka", "Sri Lankan"),
    ("Chad", "Chadian"), ("Kingdom of Spain", "Spain"), ("Iran", "Iranian"),
])
def test_country_stems_are_hidden(app, make_event, country, word):
    event = make_event("Battle of Somewhere", country=country, summary=f"A {word} force attacked. " + LONG)
    assert word not in game.excerpt(event)


def test_country_stem_does_not_hide_the_city_or_other_words(app, make_event):
    event = make_event("Run for Tunis", country="Tunisia", summary="The Run for Tunis began. Chadwick came. " + LONG)
    assert "Run for Tunis" in game.excerpt(event)
    assert game.names_a_country("Tunisian campaign", "Tunisia")
    assert not game.names_a_country("Chadwick fire", "Chad")


def test_hide_years_when_a_calendar_note_touches_the_year():
    assert game.hide_years("on 7 August 1714Greg. during") == "on 7 August ____Greg. during"


def test_hide_years_after_a_bracketed_old_style_date():
    assert game.hide_years("on 27 July [O.S. 7 August] 1714 at Gangut") == "on 27 July [O.S. 7 August] ____ at Gangut"


# ---------------------------------------------------------------- daily: no recent repeats

@pytest.fixture
def many(make_event):
    """Enough events over all eras that a day can avoid the last days' events."""
    for n in range(40):
        make_event(f"Event {n}", year=[-300, 900, 1650, 1850, 1960][n % 5] + n, lat=-60 + n * 3, lon=-170 + n * 8,
                   category=list(Category)[n % 6], country=None, summary=LONG, wiki_page_id=70_000 + n)


def test_daily_game_avoids_the_last_days_events(app, many):
    first = game.daily_event_ids(date(2026, 11, 2))
    assert game._recent_event_ids(date(2026, 11, 3)) == set(first)
    second = game._compute_daily_ids(date(2026, 11, 3), hard=False)
    assert len(second) == game.EVENTS_PER_DAY and not set(second) & set(first)


def test_recent_window_is_bounded(app, many):
    old = game.daily_event_ids(date(2026, 11, 2))
    assert game._recent_event_ids(date(2026, 11, 2) + timedelta(days=game.RECENT_DAYS + 1)) == set()
    assert game._recent_event_ids(date(2026, 11, 2) + timedelta(days=game.RECENT_DAYS)) == set(old)


def test_daily_game_repeats_rather_than_shrinks(app, make_event):
    for n in range(5):
        make_event(f"Only {n}", year=[-300, 900, 1650, 1850, 1960][n], lat=n * 20, lon=n * 50,
                   category=list(Category)[n], country=None, summary=LONG, wiki_page_id=80_000 + n)
    first = game.daily_event_ids(date(2026, 11, 2))
    assert len(first) == 5
    assert sorted(game._compute_daily_ids(date(2026, 11, 3), hard=False)) == sorted(first)


# ---------------------------------------------------------------- hints

def _today_event(index, hard=False):
    from haam.extensions import db
    from haam.models import Event
    return db.session.get(Event, game.daily_event_ids(game.today_utc(), hard=hard)[index])


def test_hint_costs_a_fifth_of_the_points(client, events):
    answer = _today_event(0)
    body = {"date": _today(), "index": 0, "lat": answer.lat, "lon": answer.lon}
    plain = client.post("/api/game/check", json=body).json
    hinted = client.post("/api/game/check", json={**body, "hint": True}).json
    assert plain["points"] == 5000 and plain["hint"] is False and plain["hint_penalty"] == 0
    assert hinted["points"] == 4000 and hinted["hint"] is True and hinted["hint_penalty"] == 1000


def test_hint_in_hard_mode_scales_place_and_year(client, events):
    answer = _today_event(0, hard=True)
    body = {"date": _today(), "hard": True, "index": 0, "lat": answer.lat, "lon": answer.lon, "year": answer.year}
    plain = client.post("/api/game/check", json=body).json
    hinted = client.post("/api/game/check", json={**body, "hint": True}).json
    assert plain["points"] == 5000
    assert (hinted["location_points"], hinted["year_points"], hinted["points"]) == (2000, 2000, 4000)
    assert hinted["hint_penalty"] == 1000


def test_check_rejects_a_bad_hint_flag(client, events):
    body = {"date": _today(), "index": 0, "lat": 0, "lon": 0, "hint": "yes"}
    assert client.post("/api/game/check", json=body).status_code == 400


def test_hint_endpoint_names_the_country_or_the_region(client, events):
    day = game.today_utc()
    for index in range(game.EVENTS_PER_DAY):
        event = _today_event(index)
        data = client.post("/api/game/hint", json={"date": day.isoformat(), "index": index}).json
        assert data == ({"kind": "country", "text": event.country} if event.country
                        else {"kind": "region", "text": game.region_at(event.lat, event.lon)})
        assert set(data) == {"kind", "text"}  # no coordinates, id or title


def test_hint_endpoint_for_practice_and_bad_input(client, events):
    seed = game.new_practice_seed()
    practice = client.post("/api/game/hint", json={"seed": seed, "index": 0})
    assert practice.status_code == 200 and practice.json["text"]
    assert client.post("/api/game/hint", json={"seed": seed, "index": 9}).status_code == 404
    assert client.post("/api/game/hint", json={"seed": "nope", "index": 0}).status_code == 400
    assert client.post("/api/game/hint", json={"index": 0}).status_code == 400
    assert client.post("/api/game/hint", json={"date": _today(), "index": True}).status_code == 400
    assert client.post("/api/game/hint", json={"date": "2020-01-01", "index": 0}).status_code == 404


@pytest.mark.parametrize("lat, lon, region", [
    (48.85, 2.35, "Western Europe"), (35.7, 139.7, "East Asia"), (-33.9, 151.2, "Australia and Oceania"),
    (28.2, -177.35, "the Pacific Ocean"), (30.0, 31.2, "North Africa"), (-13.0, -77.0, "South America"),
])
def test_region_at(lat, lon, region):
    assert game.region_at(lat, lon) == region


# ---------------------------------------------------------------- abuse limits

def test_hint_is_rate_limited(app, client, events):
    app.config["RATELIMIT_ENABLED"] = True
    for _ in range(60):
        assert client.post("/api/game/hint", json={"date": _today(), "index": 0}).status_code == 200
    assert client.post("/api/game/hint", json={"date": _today(), "index": 0}).status_code == 429


def test_a_client_can_report_only_a_few_scores_a_day(app, client, events):
    app.config["RATELIMIT_ENABLED"] = True
    for _ in range(5):
        assert client.post("/api/game/score", json={"date": _today(), "points": 100}).status_code == 200
    assert client.post("/api/game/score", json={"date": _today(), "points": 5000}).status_code == 429
    # The hard game and other clients have their own allowance.
    assert client.post("/api/game/score", json={"date": _today(), "hard": True, "points": 100}).status_code == 200
    other = client.post("/api/game/score", json={"date": _today(), "points": 100},
                        headers={"X-Forwarded-For": "203.0.113.9"})
    assert other.status_code == 200
    assert game.score_stats(game.today_utc(), False)["count"] == 6
