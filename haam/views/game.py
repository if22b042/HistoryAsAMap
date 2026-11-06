"""The daily game page and its JSON API.

The puzzle endpoint never includes where an event happened (nor its id, which
would let the answer be looked up through /api/events/<id>); the check endpoint
scores a guess and only then reveals the answer.
"""

from datetime import date

from flask import Blueprint, abort, jsonify, render_template, request, url_for

from haam import game
from haam.extensions import csrf

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
    return render_template("game.html")


@bp.get("/api/game/<value>")
def puzzle(value: str):
    day = _day(value)
    today = game.today_utc()
    events = game.daily_events(day)
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
        rounds=[game.round_dict(i, event) for i, event in enumerate(events)],
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


@bp.post("/api/game/check")
@csrf.exempt  # stateless and changes nothing on the server
def check():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("date"), str):
        abort(400)
    day = _day(data["date"])
    index = data.get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        abort(400)
    lat = _number(data, "lat", -90, 90)
    lon = game.normalize_lon(_number(data, "lon", -1e6, 1e6))

    events = game.daily_events(day)
    if not 0 <= index < len(events):
        abort(404)
    event = events[index]
    km = game.haversine_km(lat, lon, event.lat, event.lon)
    answer = game.answer_dict(event)
    answer["map_url"] = url_for("public.index", event=event.id)
    return jsonify(km=round(km, 1), points=game.score_distance(km), answer=answer)
