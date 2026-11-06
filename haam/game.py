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
import hmac
import random
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from flask import current_app
from sqlalchemy import exists, func, select
from sqlalchemy.orm import selectinload

from haam.data.place_words import COUNTRIES, NATIONALITIES
from haam.dates import MONTHS
from haam.extensions import db
from haam.models import Category, Event, Status, event_tags

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

# Hard mode: the year is guessed too. Each event is still worth MAX_POINTS, split
# between the place and the year. The year points follow a piecewise-linear curve
# through these anchors (years off → share of the year points): exact = all,
# 50 years off = 1/2, 100 = 1/3, 200 = 1/5, then down to nothing at 500 years.
HARD_LOCATION_POINTS = 500
HARD_YEAR_POINTS = MAX_POINTS - HARD_LOCATION_POINTS
YEAR_CURVE = ((0, 1.0), (50, 1 / 2), (100, 1 / 3), (200, 1 / 5), (500, 0.0))
MIN_YEAR_GUESS, MAX_YEAR_GUESS = -10000, 2100


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


def _astronomical(year: int) -> int:
    """1 BC (-1) is year 0, so that 1 BC and AD 1 are one year apart."""
    return year + 1 if year < 0 else year


def year_error(guess: int, actual: int) -> int:
    return abs(_astronomical(guess) - _astronomical(actual))


def year_share(error: int) -> float:
    """Share of the year points for an error in years, interpolated linearly on YEAR_CURVE."""
    for (x0, y0), (x1, y1) in zip(YEAR_CURVE, YEAR_CURVE[1:]):
        if error <= x1:
            return y0 + (y1 - y0) * (max(error, x0) - x0) / (x1 - x0)
    return 0.0


def score_year(guess: int, actual: int) -> int:
    """Hard-mode year points: 500 when exact, 250 at 50 years off, 0 from 500 years off."""
    return round(HARD_YEAR_POINTS * year_share(year_error(guess, actual)))


def score_hard_location(km: float) -> int:
    return round(score_distance(km) * HARD_LOCATION_POINTS / MAX_POINTS)


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


def _practice_rank(seed: str, event_id: int) -> int:
    """Keyed with the app's secret: the seed alone does not reveal the events."""
    key = current_app.config["SECRET_KEY"].encode()
    digest = hmac.new(key, f"haam-practice:{seed}:{event_id}".encode(), hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big")


def _era(year: int) -> int:
    for index, (start, end) in enumerate(ERAS):
        if (start is None or year >= start) and (end is None or year < end):
            return index
    return len(ERAS) - 1


def _candidates(rank: Callable[[int], int], era: int | None = None,
                category: Category | None = None) -> list[_Candidate]:
    tagged = exists().where(event_tags.c.event_id == Event.id).label("tagged")
    stmt = select(Event.id, Event.title, Event.country, Event.year, Event.lat, Event.lon,
                  Event.category, tagged).where(
        Event.status == Status.APPROVED,
        func.length(Event.summary) >= MIN_SUMMARY_LENGTH,
    )
    if era is not None:
        start, end = ERAS[era]
        if start is not None:
            stmt = stmt.where(Event.year >= start)
        if end is not None:
            stmt = stmt.where(Event.year < end)
    if category is not None:
        stmt = stmt.where(Event.category == category)
    rows = db.session.execute(stmt).all()
    candidates = [
        _Candidate(r.id, r.year, r.lat, r.lon, r.category.value, bool(r.tagged), rank(r.id))
        for r in rows
        if not names_a_country(r.title, r.country)
    ]
    # Events with a tag (part of a known war or period) come first.
    candidates.sort(key=lambda c: (not c.tagged, c.rank))
    return candidates


_COUNTRY_WORDS = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(w) for w in sorted(set(COUNTRIES), key=len, reverse=True)) + r")(?!\w)"
)


def names_a_country(title: str, country: str | None = None) -> bool:
    """True when the title gives the answer away by naming a country.

    "Siege of Malta" is excluded. Only country names (and historical states)
    count, not nationalities, so "German bombardment of Monrovia" stays
    playable. The event's own country (e.g. "Kingdom of Spain") counts too.
    """
    if _COUNTRY_WORDS.search(title or ""):
        return True
    return bool(country) and re.search(rf"(?<!\w){re.escape(country)}(?!\w)", title or "", re.IGNORECASE) is not None


def _pick(candidates: list[_Candidate], seed: str) -> list[int]:
    """Five events in play order, spread over eras, places and categories.

    With a filter (one era, one category) the rules that cannot be met are
    relaxed, so the set is still filled when enough events match.
    """
    era_order = list(range(len(ERAS)))
    random.Random(seed).shuffle(era_order)
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
        candidates = _candidates(lambda event_id: _rank(day, event_id))
        cache[day] = _pick(candidates, f"haam-game:{day.isoformat()}")
    return cache[day]


def daily_events(day: date) -> list[Event]:
    return _load(daily_event_ids(day))


# ---------------------------------------------------------------- practice

# Practice sets are not stored: the client keeps the seed (and its filters) and
# the server picks the same set again from them to check a guess.
SEED_PATTERN = re.compile(r"[0-9a-f]{32}")
ERA_LABELS = ("Before AD 500", "500–1500", "1500–1800", "1800–1914", "1914 onwards")


def new_practice_seed() -> str:
    return secrets.token_hex(16)


def practice_event_ids(seed: str, era: int | None = None, category: Category | None = None) -> list[int]:
    cache: dict[tuple, list[int]] = current_app.extensions.setdefault("haam_practice_cache", {})
    key = (seed, era, category)
    if key not in cache:
        if len(cache) > 512:
            cache.clear()
        candidates = _candidates(lambda event_id: _practice_rank(seed, event_id), era, category)
        # Untagged events are fine in practice: no tag-first ordering.
        candidates.sort(key=lambda c: c.rank)
        cache[key] = _pick(candidates, f"haam-practice:{seed}")
    return cache[key]


def practice_events(seed: str, era: int | None = None, category: Category | None = None) -> list[Event]:
    return _load(practice_event_ids(seed, era, category))


def _load(ids: list[int]) -> list[Event]:
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


# Hard mode hides every hint at the year. Applied in this order: years after a
# month, centuries, year ranges, decades, years with an era, any other three- or
# four-digit number, and finally lone era markers (BC, AD).
_ERA = r"(?:BCE|BC|B\.C\.E\.|B\.C\.|AD|CE|A\.D\.|C\.E\.)"
_ORDINAL_WORDS = (
    "first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|"
    "thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|nineteenth|twentieth|"
    "twenty-first"
)
# Not part of a larger number such as "1,500" or "2.5", nor of a name like "U-154".
_NUM_START = r"(?<![\w\-–])(?<!\d[,.])"
_NUM_END = r"(?![\w]|[,.]\d)"
_MONTH_YEAR = re.compile(rf"\b((?:{MONTHS})(?:\s+\d{{1,2}})?,?\s+)\d{{3,4}}{_NUM_END}")
_YEAR_HINTS = (
    re.compile(
        rf"\b(?:the\s+)?(?:(?:early|mid|late)[\s-]+)?(?:\d{{1,2}}(?:st|nd|rd|th)|{_ORDINAL_WORDS})"
        rf"[\s-]+(?:century|centuries|millennium|millennia)(?:\s+{_ERA}(?![A-Za-z]))?",
        re.IGNORECASE,
    ),
    re.compile(rf"{_NUM_START}\d{{1,4}}\s*[–—-]\s*\d{{1,4}}(?:\s*{_ERA}(?![A-Za-z]))?{_NUM_END}"),
    re.compile(rf"{_NUM_START}\d{{3,4}}\s+(?:to|until|and)\s+\d{{3,4}}{_NUM_END}"),
    re.compile(r"\b(?:the\s+)?(?:(?:early|mid|late)[\s-]+)?\d{1,3}0s\b", re.IGNORECASE),
    re.compile(rf"{_NUM_START}\d{{1,5}}\s*{_ERA}(?![A-Za-z])"),
    re.compile(rf"(?<![A-Za-z]){_ERA}\s*\d{{1,4}}\b"),
    re.compile(rf"{_NUM_START}\d{{3,4}}{_NUM_END}"),
    re.compile(rf"(?<![A-Za-z.]){_ERA}(?![A-Za-z])"),
)


def hide_years(text: str) -> str:
    """Blank out years, dates, spans, decades, centuries and BC/AD markers.

    "fought on 18 June 1815" → "fought on 18 June ____", "(1775–1783)" →
    "(____)", "the 5th century BC" → "____".
    """
    text = _MONTH_YEAR.sub(lambda m: m.group(1) + HIDDEN, text or "")
    for pattern in _YEAR_HINTS:
        text = pattern.sub(HIDDEN, text)
    return re.sub(rf"{HIDDEN}(?:[\s,–—-]*{HIDDEN})+", HIDDEN, text)


def hard_title(title: str) -> str:
    """"Siege of London (1471)" → "Siege of London"; "1755 Lisbon earthquake" → "____ Lisbon earthquake"."""
    text = re.sub(rf"\s*\(\s*{HIDDEN}\s*\)", "", hide_years(title))
    return text.strip() or HIDDEN


def round_dict(index: int, event: Event, hard: bool = False) -> dict:
    """What the player sees before guessing: no coordinates, country, id or link.

    In hard mode the year is an answer too, so it is left out and hidden in the
    title and excerpt.
    """
    if hard:
        return {
            "index": index,
            "title": hard_title(event.title),
            "date": None,
            "year": None,
            "excerpt": hide_years(excerpt(event)),
            "category": event.category.value,
        }
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
        "year": event.year,
        "display_year": event.display_year,
        "date": event.date_label or event.display_year,
    }
