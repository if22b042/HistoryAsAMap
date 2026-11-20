"""The daily game page and its JSON API.

Practice mode serves random sets of five with the same rules (optionally from
one collection, or a given seed); see :func:`haam.game.practice_event_ids`.
"Which came first?" serves ten pairs of events checked by seed and index.

The puzzle endpoints never include where an event happened (nor its id, which
would let the answer be looked up through /api/events/<id>); the check endpoint
scores a guess and only then reveals the answer.
"""

from datetime import date

from flask import Blueprint, abort, jsonify, render_template, request, url_for

from haam import game
from haam.events import public_id
from haam.extensions import csrf
from haam.models import Category
from haam.ratelimit import allow, limit

bp = Blueprint("game", __name__)


MAX_SCORES_PER_CLIENT = 5


def _day(value: str) -> date:
    if value == "today":
        return game.today_utc()
    try:
        day = date.fromisoformat(value)
    except ValueError:
        abort(404)
    if not game.is_playable(day):
        abort(404)
    return day


@bp.get("/game")
def page():
    # A shared result links to /game?date=…; its preview names that day's game.
    shared_day = None
    try:
        day = date.fromisoformat(request.args.get("date", ""))
    except ValueError:
        day = None
    if day is not None and game.is_playable(day):
        shared_day = {"date": day, "number": game.game_number(day), "hard": _hard_arg()}
    return render_template("game.html", eras=game.ERA_LABELS, shared_day=shared_day)


def _hard_arg() -> bool:
    return request.args.get("hard") in ("1", "true")


@bp.get("/api/game/<value>")
def puzzle(value: str):
    day = _day(value)
    hard = _hard_arg()
    today = game.today_utc()
    events = game.daily_events(day, hard)
    previous = date.fromordinal(day.toordinal() - 1)
    following = date.fromordinal(day.toordinal() + 1)
    response = jsonify(
        date=day.isoformat(),
        number=game.game_number(day),
        is_today=day == today,
        today=today.isoformat(),
        previous=previous.isoformat() if game.is_playable(previous) else None,
        next=following.isoformat() if game.is_playable(following) else None,
        next_game_at=game.next_game_at(today).isoformat(),
        max_points=game.MAX_POINTS,
        hard=hard,
        stats=game.score_stats(day, hard),
        rounds=[game.round_dict(i, event, hard) for i, event in enumerate(events)],
    )
    response.cache_control.no_store = True
    return response


def _number(data: dict, key: str, low: float, high: float) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        abort(400)
    value = float(value)
    if not low <= value <= high:
        abort(400)
    return value


def _json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400)
    return data


def _hint_level(value) -> int:
    """0 = no hint, 1 = the description, 2 = the country too (true/false from older pages = 1/0)."""
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, int) or not 0 <= value < len(game.HINT_PENALTIES):
        abort(400)
    return value


def _token(day: date | None, hard: bool, index: int, points: int) -> dict:
    """The signed receipt of a daily round (practice games have none)."""
    return {} if day is None else {"token": game.round_token(day, hard, index, points)}


def _score(data: dict, events: list, day: date | None = None):
    """Score the guess in ``data`` against ``events[data["index"]]`` and reveal it."""
    index = data.get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        abort(400)
    lat = _number(data, "lat", -90, 90)
    lon = game.normalize_lon(_number(data, "lon", -1e6, 1e6))
    hard = data.get("hard", False)
    level = _hint_level(data.get("hint", 0))
    if not isinstance(hard, bool):
        abort(400)
    year = None
    if hard:
        year = data.get("year")
        if (isinstance(year, bool) or not isinstance(year, int) or year == 0
                or not game.MIN_YEAR_GUESS <= year <= game.MAX_YEAR_GUESS):
            abort(400)
    if not 0 <= index < len(events):
        abort(404)
    event = events[index]
    km = game.haversine_km(lat, lon, event.lat, event.lon)
    answer = game.answer_dict(event)
    answer["map_url"] = url_for("public.index", event=public_id(event))
    # The hints used cost a share of the round's points (of both parts in hard mode).
    def keep(points: int) -> int:
        return game.apply_hint(points, level)

    if not hard:
        full = game.score_distance(km)
        points = keep(full)
        return jsonify(km=round(km, 1), points=points, hint=level, hint_penalty=full - points, answer=answer,
                       **_token(day, hard, index, points))
    full_location = game.score_hard_location(km)
    full_year = game.score_year(year, event.year)
    location_points, year_points = keep(full_location), keep(full_year)
    return jsonify(
        km=round(km, 1),
        points=location_points + year_points,
        location_points=location_points,
        year_points=year_points,
        year_error=game.year_error(year, event.year),
        hint=level,
        hint_penalty=full_location + full_year - location_points - year_points,
        answer=answer,
        **_token(day, hard, index, location_points + year_points),
    )


@bp.post("/api/game/check")
@limit("game-check", 120, 60)
@csrf.exempt  # changes nothing on the server; the signed token it returns is checked by /score
def check():
    data = _json_body()
    if not isinstance(data.get("date"), str):
        abort(400)
    day = _day(data["date"])
    return _score(data, game.daily_events(day, hard=data.get("hard") is True), day)


# ---------------------------------------------------------------- practice

def _filters(source) -> tuple[int | None, Category | None]:
    """Era index and category from query args or a JSON body; empty means "any"."""
    era, category = source.get("era"), source.get("category")
    if era in (None, ""):
        era = None
    else:
        try:
            era = int(era)
        except (TypeError, ValueError):
            abort(400)
        if isinstance(source.get("era"), bool) or not 0 <= era < len(game.ERAS):
            abort(400)
    if category in (None, ""):
        category = None
    else:
        try:
            category = Category(category)
        except ValueError:
            abort(400)
    return era, category


def _collection_ids(source) -> list[int] | None:
    """The approved events of ``collection=<view token>``; None without that parameter."""
    token = source.get("collection")
    if token in (None, ""):
        return None
    if not isinstance(token, str):
        abort(400)
    ids = game.collection_event_ids(token)
    if ids is None:
        abort(404)
    return ids


@bp.get("/api/game/practice")
@limit("game-practice", 60, 60)
def practice():
    """A random set of five (or the one of ``seed``); only the seed is needed to check guesses later."""
    era, category = _filters(request.args)
    hard = _hard_arg()
    only_ids = _collection_ids(request.args)
    seed = request.args.get("seed")
    if seed is None:
        seed = game.new_practice_seed()
    elif not game.SEED_PATTERN.fullmatch(seed):
        abort(400)
    if only_ids is not None and len(only_ids) < game.MIN_COLLECTION_EVENTS:
        response = jsonify(
            seed=seed, era=era, category=category.value if category else None, hard=hard,
            max_points=game.MAX_POINTS, rounds=[],
            message=f"This collection has {len(only_ids)} approved events from the main map; "
                    f"a quiz needs at least {game.MIN_COLLECTION_EVENTS}.",
        )
        response.cache_control.no_store = True
        return response
    events = game.practice_events(seed, era, category, only_ids)
    response = jsonify(
        seed=seed,
        era=era,
        category=category.value if category else None,
        max_points=game.MAX_POINTS,
        hard=hard,
        rounds=[game.round_dict(i, event, hard) for i, event in enumerate(events)],
    )
    response.cache_control.no_store = True
    return response


@bp.post("/api/game/practice/check")
@limit("game-practice", 60, 60)
@csrf.exempt  # stateless and changes nothing on the server
def practice_check():
    data = _json_body()
    seed = data.get("seed")
    if not isinstance(seed, str) or not game.SEED_PATTERN.fullmatch(seed):
        abort(400)
    era, category = _filters(data)
    return _score(data, game.practice_events(seed, era, category, _collection_ids(data)))


# ---------------------------------------------------------------- hints

@bp.post("/api/game/hint")
@limit("game-hint", 60, 60)
@csrf.exempt  # stateless and changes nothing on the server
def hint():
    """The optional hint for one event of a daily or practice game; it costs points when scoring."""
    data = _json_body()
    index = data.get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        abort(400)
    if "seed" in data:
        seed = data["seed"]
        if not isinstance(seed, str) or not game.SEED_PATTERN.fullmatch(seed):
            abort(400)
        era, category = _filters(data)
        events = game.practice_events(seed, era, category, _collection_ids(data))
    elif isinstance(data.get("date"), str):
        events = game.daily_events(_day(data["date"]), hard=data.get("hard") is True)
    else:
        abort(400)
    if not 0 <= index < len(events):
        abort(404)
    level = data.get("level", 1)
    if isinstance(level, bool) or level not in (1, 2):
        abort(400)
    response = jsonify(game.hint_dict(events[index], level, hard=data.get("hard") is True))
    response.cache_control.no_store = True
    return response


# ---------------------------------------------------------------- daily scores

@bp.post("/api/game/score")
@limit("game-score", 30, 60)
@csrf.exempt  # anonymous; the total comes from the signed round tokens, not from the client
def score():
    data = _json_body()
    if not isinstance(data.get("date"), str):
        abort(400)
    day = _day(data["date"])
    hard = data.get("hard", False)
    if not isinstance(hard, bool):
        abort(400)
    # The server adds the tokens /api/game/check handed out: exactly one valid token per round.
    proven = game.total_from_tokens(day, hard, data.get("tokens"))
    if proven is None:
        abort(400)
    points, proof = proven
    # A game is finished once: a few reports per client, game and day (a household or school
    # may share one address).
    if not allow(f"game-score:{day.isoformat()}:{int(hard)}", MAX_SCORES_PER_CLIENT, 86400):
        abort(429)
    recorded = game.record_score(day, hard, points, proof)  # the same tokens count once
    response = jsonify(stats=game.score_stats(day, hard), percentile=game.percentile(day, hard, points),
                       points=points, recorded=recorded)
    return response if recorded else (response, 409)


# ------------------------------------------------------------ which came first

def _seed_arg(value) -> str:
    if value is None:
        return game.new_practice_seed()
    if not isinstance(value, str) or not game.SEED_PATTERN.fullmatch(value):
        abort(400)
    return value


@bp.get("/api/game/pairs")
def pairs():
    """Ten pairs of events with their years hidden: which one came first?"""
    seed = _seed_arg(request.args.get("seed"))
    response = jsonify(
        seed=seed,
        rounds=[game.pair_round_dict(i, a, b) for i, (a, b) in enumerate(game.pair_events(seed))],
    )
    response.cache_control.no_store = True
    return response


@bp.post("/api/game/pairs/check")
@csrf.exempt  # stateless and changes nothing on the server
def pairs_check():
    data = _json_body()
    seed = data.get("seed")
    if not isinstance(seed, str) or not game.SEED_PATTERN.fullmatch(seed):
        abort(400)
    index, choice = data.get("index"), data.get("choice")
    for value in (index, choice):
        if isinstance(value, bool) or not isinstance(value, int):
            abort(400)
    if choice not in (0, 1):
        abort(400)
    pairs_ = game.pair_events(seed)
    if not 0 <= index < len(pairs_):
        abort(404)
    return jsonify(game.pair_answer(*pairs_[index], choice))
