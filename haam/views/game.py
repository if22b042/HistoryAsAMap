"""The daily game page and its JSON API.

Practice mode serves random sets of five with the same rules; see
:func:`haam.game.practice_event_ids`.

The puzzle endpoints never include where an event happened (nor its id, which
would let the answer be looked up through /api/events/<id>); the check endpoint
scores a guess and only then reveals the answer.
"""

from datetime import date

from flask import Blueprint, abort, jsonify, render_template, request, url_for

from haam import game
from haam.extensions import csrf
from haam.models import Category

bp = Blueprint("game", __name__)


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


def _score(data: dict, events: list):
    """Score the guess in ``data`` against ``events[data["index"]]`` and reveal it."""
    index = data.get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        abort(400)
    lat = _number(data, "lat", -90, 90)
    lon = game.normalize_lon(_number(data, "lon", -1e6, 1e6))
    hard = data.get("hard", False)
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
    answer["map_url"] = url_for("public.index", event=event.id)
    if not hard:
        return jsonify(km=round(km, 1), points=game.score_distance(km), answer=answer)
    location_points = game.score_hard_location(km)
    year_points = game.score_year(year, event.year)
    return jsonify(
        km=round(km, 1),
        points=location_points + year_points,
        location_points=location_points,
        year_points=year_points,
        year_error=game.year_error(year, event.year),
        answer=answer,
    )


@bp.post("/api/game/check")
@csrf.exempt  # stateless and changes nothing on the server
def check():
    data = _json_body()
    if not isinstance(data.get("date"), str):
        abort(400)
    return _score(data, game.daily_events(_day(data["date"]), hard=data.get("hard") is True))


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


@bp.get("/api/game/practice")
def practice():
    """A new random set of five; only its seed is needed to check guesses later."""
    era, category = _filters(request.args)
    hard = _hard_arg()
    seed = game.new_practice_seed()
    events = game.practice_events(seed, era, category)
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
@csrf.exempt  # stateless and changes nothing on the server
def practice_check():
    data = _json_body()
    seed = data.get("seed")
    if not isinstance(seed, str) or not game.SEED_PATTERN.fullmatch(seed):
        abort(400)
    era, category = _filters(data)
    return _score(data, game.practice_events(seed, era, category))
