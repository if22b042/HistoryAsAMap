"""The daily game: guess where five historical events happened.

Every player gets the same five events on a given (UTC) day. The year is shown;
the player places a pin on the map and scores up to 1,000 points per event
depending on how far the pin is from the real place.

The pick is deterministic: each candidate gets a rank from a hash of the date and
its id (events with a tag first), and the events are taken in rank order while keeping them apart in time
(one per era), in space (far apart) and in category. Adding an event to the
database rarely changes a day's pick: it would have to outrank the event chosen
for its era. (Filtering by creation date is no option: the whole database may be
re-imported at any time.)
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from flask import current_app
from sqlalchemy import exists, func, select
from sqlalchemy.orm import selectinload

from haam.data.place_words import COUNTRIES, NATIONALITIES
from haam.extensions import db
from haam.models import Event, Status, event_tags

EVENTS_PER_DAY = 5
MAX_POINTS = 1000
# The first daily game; older dates have no game.
EPOCH = date(2026, 11, 1)

# Only events with a real description: short stubs are rarely well known.
MIN_SUMMARY_LENGTH = 300
# Picks are kept at least this far apart, so they are not all in one region.
MIN_KM_APART = 1500
MAX_PER_CATEGORY = 2
# One event per era; the order of the eras changes every day.
ERAS = ((None, 500), (500, 1500), (1500, 1800), (1800, 1914), (1914, None))

# Scoring: full points within FULL_KM, half points at HALF_KM, none from ZERO_KM.
FULL_KM = 25
HALF_KM = 500
ZERO_KM = 3000
EARTH_RADIUS_KM = 6371.0

EXCERPT_MIN, EXCERPT_MAX = 160, 320
HIDDEN = "____"


# ------------------------------------------------------------------ dates

def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def game_number(day: date) -> int:
    return (day - EPOCH).days + 1


def is_playable(day: date) -> bool:
    return EPOCH <= day <= today_utc()


def next_game_at(day: date) -> datetime:
    """When the game after ``day`` starts (midnight UTC)."""
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc)


# ---------------------------------------------------------------- scoring

def normalize_lon(lon: float) -> float:
    """Map longitudes from a wrapped map (e.g. 370) back into [-180, 180)."""
    return ((lon + 180.0) % 360.0) - 180.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


_DECAY_KM = HALF_KM / math.log(2)
_FLOOR = math.exp(-ZERO_KM / _DECAY_KM)


def score_distance(km: float) -> int:
    """Points for a pin ``km`` away: 1,000 when close, ~500 at 500 km, 0 from 3,000 km."""
    if km <= FULL_KM:
        return MAX_POINTS
    if km >= ZERO_KM:
        return 0
    # Exponential decay, shifted so it reaches exactly 0 at ZERO_KM.
    value = (math.exp(-km / _DECAY_KM) - _FLOOR) / (1 - _FLOOR)
    return max(0, min(MAX_POINTS, round(MAX_POINTS * value)))


# ---------------------------------------------------------------- picking

@dataclass(frozen=True)
class _Candidate:
    id: int
    year: int
    lat: float
    lon: float
    category: str
    tagged: bool
    rank: int


def _rank(day: date, event_id: int) -> int:
    digest = hashlib.sha256(f"haam-game:{day.isoformat()}:{event_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _era(year: int) -> int:
    for index, (start, end) in enumerate(ERAS):
        if (start is None or year >= start) and (end is None or year < end):
            return index
    return len(ERAS) - 1


def _candidates(day: date) -> list[_Candidate]:
    tagged = exists().where(event_tags.c.event_id == Event.id).label("tagged")
    stmt = select(Event.id, Event.year, Event.lat, Event.lon, Event.category, tagged).where(
        Event.status == Status.APPROVED,
        func.length(Event.summary) >= MIN_SUMMARY_LENGTH,
    )
    rows = db.session.execute(stmt).all()
    candidates = [
        _Candidate(r.id, r.year, r.lat, r.lon, r.category.value, bool(r.tagged), _rank(day, r.id))
        for r in rows
    ]
    # Events with a tag (part of a known war or period) come first.
    candidates.sort(key=lambda c: (not c.tagged, c.rank))
    return candidates


def _pick(candidates: list[_Candidate], day: date) -> list[int]:
    era_order = list(range(len(ERAS)))
    random.Random(f"haam-game:{day.isoformat()}").shuffle(era_order)
    picked: list[_Candidate] = []

    def fits(c: _Candidate, era: int | None, apart: bool, per_category: bool) -> bool:
        if c in picked or (era is not None and _era(c.year) != era):
            return False
        if per_category and sum(p.category == c.category for p in picked) >= MAX_PER_CATEGORY:
            return False
        if apart and any(haversine_km(c.lat, c.lon, p.lat, p.lon) < MIN_KM_APART for p in picked):
            return False
        return True

    # Ideal first; when an era has nothing that fits, relax the rules one by one.
    relaxations = ((True, True), (False, True), (False, False))
    slots = era_order + [None] * max(0, EVENTS_PER_DAY - len(era_order))
    for era in slots[:EVENTS_PER_DAY]:
        for apart, per_category in relaxations:
            choice = next((c for c in candidates if fits(c, era, apart, per_category)), None)
            if choice:
                picked.append(choice)
                break
    # Eras without any candidate: fill from any era.
    for apart, per_category in relaxations:
        while len(picked) < EVENTS_PER_DAY:
            choice = next((c for c in candidates if fits(c, None, apart, per_category)), None)
            if not choice:
                break
            picked.append(choice)
    return [c.id for c in picked]


def daily_event_ids(day: date) -> list[int]:
    """The ids of ``day``'s events, in play order. Cached per app process."""
    cache: dict[date, list[int]] = current_app.extensions.setdefault("haam_game_cache", {})
    if day not in cache:
        if len(cache) > 64:
            cache.clear()
        cache[day] = _pick(_candidates(day), day)
    return cache[day]


def daily_events(day: date) -> list[Event]:
    ids = daily_event_ids(day)
    if not ids:
        return []
    stmt = select(Event).where(Event.id.in_(ids)).options(selectinload(Event.tags))
    by_id = {event.id: event for event in db.session.scalars(stmt)}
    return [by_id[i] for i in ids if i in by_id]


# ---------------------------------------------------------------- clues

_PLACE_WORDS = re.compile(
    r"(?<!\w)(?:"
    + "|".join(re.escape(w) for w in sorted(set(COUNTRIES + NATIONALITIES), key=len, reverse=True))
    + r")(?:e?s)?(?!\w)"
)


def _hide_place(text: str, event: Event) -> str:
    """Hide countries and nationalities, so the excerpt does not give the answer away.

    "the Spanish port of Tarragona" becomes "the ____ port of Tarragona". Town
    names stay: the title usually names the town anyway.
    """
    if event.country:
        text = re.sub(rf"(?<!\w){re.escape(event.country)}(?!\w)", HIDDEN, text, flags=re.IGNORECASE)
    text = _PLACE_WORDS.sub(HIDDEN, text)
    # "____ ____" (e.g. "Holy Roman" split oddly) reads better as one blank.
    return re.sub(rf"{HIDDEN}(?:[ –-]{HIDDEN})+", HIDDEN, text)


def excerpt(event: Event) -> str:
    """The first sentence or two of the summary, with countries and nationalities hidden."""
    paragraph = next((p for p in (event.summary or "").split("\n") if p.strip()), "").strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", paragraph)
    text = ""
    for sentence in sentences:
        text = f"{text} {sentence}".strip()
        if len(text) >= EXCERPT_MIN:
            break
    if len(text) > EXCERPT_MAX:
        text = text[:EXCERPT_MAX].rsplit(" ", 1)[0] + "…"
    return _hide_place(text, event)


def round_dict(index: int, event: Event) -> dict:
    """What the player sees before guessing: no coordinates, country, id or link."""
    return {
        "index": index,
        "title": event.title,
        "date": event.date_label or event.display_year,
        "year": event.year,
        "excerpt": excerpt(event),
        "category": event.category.value,
    }


def answer_dict(event: Event) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "lat": event.lat,
        "lon": event.lon,
        "country": event.country,
        "wiki_url": event.wiki_url,
    }
