"""The daily game: guess where five historical events happened.

Every player gets the same five events on a given (UTC) day. The year is shown;
the player places a pin on the map and scores up to 1,000 points per event
depending on how far the pin is from the real place. The hard game of the day
has five other events, and the year is guessed too.

The pick is deterministic: each candidate gets a rank from a hash of the date and
its id (events with a tag first), and the events are taken in rank order while keeping them apart in time
(one per era), in space (far apart) and in category. Adding an event to the
database rarely changes a day's pick: it would have to outrank the event chosen
for its era. (Filtering by creation date is no option: the whole database may be
re-imported at any time.)
"""

from __future__ import annotations

import hashlib
import json
import math
import hmac
import random
import re
import secrets
from collections.abc import Callable
from functools import lru_cache
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from flask import current_app
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from haam.data.place_words import COUNTRIES, NATIONALITIES
from haam.data.regions import region_at, region_of_word
from haam.dates import MONTHS
from haam.events import public_id
from haam.extensions import db
from haam.models import (
    Category, Collection, CollectionEntry, DailyGame, Event, GameScore, Status, event_tags,
)

EVENTS_PER_DAY = 5
MAX_POINTS = 5000
# A daily game never reuses an event of the last RECENT_DAYS days (if enough others exist).
RECENT_DAYS = 180
# Share of a round's points a hint costs.
# Optional hints, each level in total: 1 = more of the description, 2 = the country.
HINT_PENALTIES = (0.0, 0.2, 0.5)
HINT_MAX_CHARS = 420
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
FULL_KM = 50
HALF_KM = 1000
ZERO_KM = 6000
EARTH_RADIUS_KM = 6371.0

EXCERPT_MIN, EXCERPT_MAX = 160, 320
HIDDEN = "____"

# Hard mode: the year is guessed too. Each event is still worth MAX_POINTS, split
# between the place and the year. The year points follow a piecewise-linear curve
# through these anchors (years off → share of the year points): exact = all,
# 50 years off = 1/2, 100 = 1/3, 200 = 1/5, then down to nothing at 500 years.
HARD_LOCATION_POINTS = 2500
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


def _rank(day: date, event_id: int, salt: str = "haam-game") -> int:
    digest = hashlib.sha256(f"{salt}:{day.isoformat()}:{event_id}".encode()).digest()
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
                category: Category | None = None, only_ids: list[int] | None = None) -> list[_Candidate]:
    tagged = exists().where(event_tags.c.event_id == Event.id).label("tagged")
    stmt = select(Event.id, Event.title, Event.country, Event.year, Event.lat, Event.lon,
                  Event.category, tagged).where(Event.status == Status.APPROVED)
    if only_ids is None:
        stmt = stmt.where(func.length(Event.summary) >= MIN_SUMMARY_LENGTH)
    else:
        # A collection's own events: the owner chose them, so short texts are fine.
        stmt = stmt.where(Event.id.in_(only_ids))
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


# Endings that turn a country into its people or adjective: Tunisia → Tunisian, Chad → Chadian.
_ADJECTIVE_ENDINGS = "ia|ian|ians|an|ans|ese|ish|i|is|ic"


@lru_cache(maxsize=2048)
def _country_regex(country: str) -> re.Pattern:
    """Matches the country's name, without a plural "s" and as an adjective ("Philippine", "Tunisian").

    "Kingdom of Spain" also matches "Spain". The stem (the name without its last
    vowels) is only matched with an ending, so "Tunis" the city is not matched.
    """
    names = {country.strip()}
    if " of " in country:
        names.add(country.rsplit(" of ", 1)[1].removeprefix("the ").strip())
    parts = []
    for name in sorted(filter(None, names), key=len, reverse=True):
        parts.append(re.escape(name))
        if name.endswith("s") and len(name) > 4:
            parts.append(re.escape(name[:-1]))
        stem = re.sub(r"[aeiouy]+$", "", name, flags=re.IGNORECASE)
        if len(stem) >= 4:
            parts.append(rf"{re.escape(stem)}(?:{_ADJECTIVE_ENDINGS})")
    return re.compile(rf"(?<!\w)(?:{'|'.join(parts)})(?!\w)", re.IGNORECASE)


def names_a_country(title: str, country: str | None = None) -> bool:
    """True when the title gives the answer away by naming a country.

    "Siege of Malta" is excluded. Only country names (and historical states)
    count, not nationalities, so "German bombardment of Monrovia" stays
    playable. The event's own country (e.g. "Kingdom of Spain") counts too.
    """
    if _COUNTRY_WORDS.search(title or ""):
        return True
    return bool(country) and _country_regex(country).search(title or "") is not None


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


def _recent_event_ids(day: date) -> set[int]:
    """Events of the (normal and hard) games stored for the RECENT_DAYS before ``day``.

    Only days that were already stored count, so an archive day opened for the
    first time long after the fact may repeat an event of a day nobody played;
    the result is stored too, so every visitor still sees the same set.
    """
    since = day - timedelta(days=RECENT_DAYS)
    rows = db.session.scalars(
        select(DailyGame.refs).where(DailyGame.date >= since, DailyGame.date < day)).all()
    refs: set[str] = set()
    for raw in rows:
        try:
            parsed = json.loads(raw)
        except ValueError:
            continue
        if isinstance(parsed, list):
            refs.update(r for r in parsed if isinstance(r, str))
    return set(_resolve_refs(sorted(refs))) if refs else set()


def _compute_daily_ids(day: date, hard: bool) -> list[int]:
    """Pick ``day``'s events from the live table.

    The hard game has its own five events, never the ones of that day's normal
    game: it is ranked with another salt and skips the normal picks. Events used
    in the last RECENT_DAYS days are skipped too, so a small pool (old eras have
    few well-described events) does not repeat the same ones all year; when that
    leaves too few events, the rule is dropped.
    """
    salt = "haam-game-hard" if hard else "haam-game"
    candidates = _candidates(lambda event_id: _rank(day, event_id, salt))
    if hard:
        normal = set(daily_event_ids(day))
        candidates = [c for c in candidates if c.id not in normal]
    seed = f"{salt}:{day.isoformat()}"
    recent = _recent_event_ids(day)
    if recent:
        ids = _pick([c for c in candidates if c.id not in recent], seed)
        if len(ids) >= EVENTS_PER_DAY:
            return ids
    return _pick(candidates, seed)


def _ref(page_id: int | None, event_id: int) -> str:
    """How a stored game names an event: its Wikipedia page id ("p123"), else its row id ("i45")."""
    return f"p{page_id}" if page_id is not None else f"i{event_id}"


def _resolve_refs(refs: list[str]) -> list[int]:
    """Row ids of the stored events, in order; events that no longer exist are skipped."""
    pages = [int(r[1:]) for r in refs if r[:1] == "p" and r[1:].isdigit()]
    rows = [int(r[1:]) for r in refs if r[:1] == "i" and r[1:].isdigit()]
    found: dict[str, int] = {}
    stmt = select(Event.id, Event.wiki_page_id).where(
        Event.status == Status.APPROVED,
        Event.wiki_page_id.in_(pages) | (Event.id.in_(rows) & Event.wiki_page_id.is_(None)),
    )
    for row in db.session.execute(stmt):
        found[_ref(row.wiki_page_id, row.id)] = row.id
    return [found[r] for r in refs if r in found]


def _stored_refs(day: date, hard: bool) -> list[str] | None:
    raw = db.session.scalar(select(DailyGame.refs).where(DailyGame.date == day, DailyGame.hard == hard))
    if raw is None:
        return None
    try:
        refs = json.loads(raw)
    except ValueError:
        return None
    return [r for r in refs if isinstance(r, str)] if isinstance(refs, list) else None


def daily_event_ids(day: date, hard: bool = False) -> list[int]:
    """The ids of ``day``'s events, in play order.

    The set is fixed for the day: it is picked from the live table on the first
    request and stored in ``haam_daily_games`` (by Wikipedia page id), so later
    approvals, edits or re-imports cannot change it, and every server instance
    agrees. Two first requests at once: the unique constraint lets one win and
    the other reads its row. Also cached per app process.
    """
    cache: dict[tuple[date, bool], list[int]] = current_app.extensions.setdefault("haam_game_cache", {})
    key = (day, hard)
    if key in cache:
        return cache[key]
    refs = _stored_refs(day, hard)
    if refs is None:
        ids = _compute_daily_ids(day, hard)
        if not ids:
            return ids  # nothing to store without events: try again on the next request
        pages = dict(db.session.execute(select(Event.id, Event.wiki_page_id).where(Event.id.in_(ids))).all())
        refs = [_ref(pages.get(i), i) for i in ids]
        try:
            db.session.add(DailyGame(date=day, hard=hard, refs=json.dumps(refs)))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            refs = _stored_refs(day, hard) or refs
    if len(cache) > 128:
        cache.clear()
    cache[key] = _resolve_refs(refs)
    return cache[key]


def daily_events(day: date, hard: bool = False) -> list[Event]:
    return _load(daily_event_ids(day, hard))


# ---------------------------------------------------------------- practice

# Practice sets are not stored: the client keeps the seed (and its filters) and
# the server picks the same set again from them to check a guess.
SEED_PATTERN = re.compile(r"[0-9a-f]{32}")
ERA_LABELS = ("Before AD 500", "500–1500", "1500–1800", "1800–1914", "1914 onwards")


def new_practice_seed() -> str:
    return secrets.token_hex(16)


def collection_event_ids(view_token: str) -> list[int] | None:
    """Approved main-map events of a viewable collection; None when there is no such collection."""
    collection = db.session.scalar(select(Collection).where(Collection.view_token == view_token))
    if collection is None or collection.is_hidden:
        return None
    stmt = (select(CollectionEntry.event_id).join(Event, Event.id == CollectionEntry.event_id)
            .where(CollectionEntry.collection_id == collection.id, Event.status == Status.APPROVED))
    return sorted(set(db.session.scalars(stmt)))


MIN_COLLECTION_EVENTS = EVENTS_PER_DAY


def practice_event_ids(seed: str, era: int | None = None, category: Category | None = None,
                       only_ids: list[int] | None = None) -> list[int]:
    cache: dict[tuple, list[int]] = current_app.extensions.setdefault("haam_practice_cache", {})
    key = (seed, era, category)
    # A collection's events can change: its sets are not cached.
    if only_ids is None and key in cache:
        return cache[key]
    candidates = _candidates(lambda event_id: _practice_rank(seed, event_id), era, category, only_ids)
    # Untagged events are fine in practice: no tag-first ordering.
    candidates.sort(key=lambda c: c.rank)
    ids = _pick(candidates, f"haam-practice:{seed}")
    if only_ids is None:
        if len(cache) > 512:
            cache.clear()
        cache[key] = ids
    return ids


def practice_events(seed: str, era: int | None = None, category: Category | None = None,
                    only_ids: list[int] | None = None) -> list[Event]:
    return _load(practice_event_ids(seed, era, category, only_ids))


# ------------------------------------------------------------ which came first

PAIRS_PER_SET = 10
MIN_GAP_YEARS, MAX_GAP_YEARS = 5, 300


def pair_ids(seed: str) -> list[tuple[int, int]]:
    """Ten pairs of events 5 to 300 years apart, from tagged events when possible.

    Deterministic for a seed (keyed ranks, like practice); which event is shown
    first in a pair is a coin flip per index.
    """
    cache: dict[str, list[tuple[int, int]]] = current_app.extensions.setdefault("haam_pairs_cache", {})
    if seed in cache:
        return cache[seed]
    pool = _candidates(lambda event_id: _practice_rank(f"pairs-{seed}", event_id))
    used: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for a in pool:
        if len(pairs) >= PAIRS_PER_SET:
            break
        if a.id in used:
            continue
        for b in pool:
            if b.id == a.id or b.id in used:
                continue
            if MIN_GAP_YEARS <= abs(_astronomical(a.year) - _astronomical(b.year)) <= MAX_GAP_YEARS:
                used.update((a.id, b.id))
                flip = random.Random(f"{seed}:{len(pairs)}").random() < 0.5
                pairs.append((b.id, a.id) if flip else (a.id, b.id))
                break
    if len(cache) > 256:
        cache.clear()
    cache[seed] = pairs
    return pairs


def pair_events(seed: str) -> list[tuple[Event, Event]]:
    pairs = pair_ids(seed)
    by_id = {e.id: e for e in _load([i for pair in pairs for i in pair])}
    return [(by_id[a], by_id[b]) for a, b in pairs if a in by_id and b in by_id]


def pair_clue(event: Event) -> dict:
    """What the player sees of one event of a pair: no year, place or id."""
    return {"title": hard_title(event.title), "excerpt": hide_years(excerpt(event)),
            "category": event.category.value}


def pair_round_dict(index: int, first: Event, second: Event) -> dict:
    return {"index": index, "a": pair_clue(first), "b": pair_clue(second)}


def pair_answer(first: Event, second: Event, choice: int) -> dict:
    """The verdict on a pick (0 = first, 1 = second), with both dates revealed."""
    earlier = 0 if _astronomical(first.year) < _astronomical(second.year) else 1

    def side(event: Event) -> dict:
        return {"title": event.title, "date": event.date_label or event.display_year,
                "year": event.year, "wiki_url": event.wiki_url}

    return {"correct": choice == earlier, "earlier": earlier, "a": side(first), "b": side(second)}


# ------------------------------------------------------------ daily scores

MAX_DAILY_TOTAL = MAX_POINTS * EVENTS_PER_DAY


def round_token(day: date, hard: bool, index: int, points: int) -> str:
    """A signed receipt for one scored daily round: ``<points>.<signature>``.

    Bound to the day, the mode, the round and the points, so /game/score can total a finished
    game without trusting the client. (Answers can still be found by probing /api/game/check.)"""
    key = current_app.config["SECRET_KEY"].encode()
    message = f"haam-score:{day.isoformat()}:{int(hard)}:{index}:{points}".encode()
    return f"{points}.{hmac.new(key, message, hashlib.sha256).hexdigest()[:32]}"


def total_from_tokens(day: date, hard: bool, tokens) -> tuple[int, str] | None:
    """The total and proof hash of exactly one valid token per round, in order; None if not."""
    if not isinstance(tokens, list) or len(tokens) != EVENTS_PER_DAY:
        return None
    total = 0
    for index, token in enumerate(tokens):
        if not isinstance(token, str):
            return None
        head = token.partition(".")[0]
        if not head.isascii() or not head.isdigit() or len(head) > 6:
            return None
        points = int(head)
        if not hmac.compare_digest(token, round_token(day, hard, index, points)):
            return None
        total += points
    proof = hashlib.sha256(f"{day.isoformat()}:{int(hard)}:{'|'.join(tokens)}".encode()).hexdigest()
    return total, proof


def record_score(day: date, hard: bool, points: int, proof: str | None = None) -> bool:
    """Store a total; False (nothing stored) when this proof was already recorded."""
    db.session.add(GameScore(date=day, hard=hard, points=points, proof=proof))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False
    return True


MIN_PERCENTILE_SCORES = 5


def percentile(day: date, hard: bool, points: int) -> int | None:
    """Percent of the day's proven scores that ``points`` beats (ties count half).

    None while fewer than MIN_PERCENTILE_SCORES scores exist: too few to mean anything."""
    # Rows without a proof predate signed tokens and may be self-reported: not compared with.
    where = (GameScore.date == day, GameScore.hard == hard, GameScore.proof.is_not(None))
    count = db.session.scalar(select(func.count(GameScore.id)).where(*where))
    if count < MIN_PERCENTILE_SCORES:
        return None
    below = db.session.scalar(select(func.count(GameScore.id)).where(*where, GameScore.points < points))
    equal = db.session.scalar(select(func.count(GameScore.id)).where(*where, GameScore.points == points))
    return round(100 * (below + equal / 2) / count)


def score_stats(day: date, hard: bool) -> dict:
    """How many finished ``day``'s game and their average total (no user data is kept)."""
    count, average = db.session.execute(
        select(func.count(GameScore.id), func.avg(GameScore.points)).where(
            GameScore.date == day, GameScore.hard == hard)
    ).one()
    return {"count": count, "average": round(float(average)) if average is not None else None}


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


def _country_region(country: str | None) -> str | None:
    """The region of an event's own country ("Kingdom of Spain" → "Southern Europe")."""
    if not country:
        return None
    for name in (country, country.rsplit(" of ", 1)[-1].removeprefix("the "), country.split()[-1]):
        region = region_of_word(name)
        if region:
            return region
    return None


# Private-use characters mark the placeholders of _hide_place.
_OPEN, _CLOSE = chr(0xE000), chr(0xE001)
_PLACEHOLDER = re.compile(rf"{_OPEN}(\d+){_CLOSE}")
_SAME_PLACEHOLDERS = re.compile(rf"({_OPEN}\d+{_CLOSE})(?:[ –-]\1)+")


def _hide_place(text: str, event: Event) -> str:
    """Replace countries and nationalities by their region, so the clue does not give the answer away.

    "the Spanish port of Tarragona" becomes "the [Southern Europe] port of
    Tarragona": the player still learns roughly where, but not which country.
    Words without a known region become a plain blank. Town names stay: the
    title usually names the town anyway.
    """
    labels: list[str] = []

    def blank(region: str | None) -> str:
        label = f"[{region}]" if region else HIDDEN
        if label not in labels:
            labels.append(label)
        # A placeholder, so that later passes cannot match inside a label ("[British Isles]").
        return f"{_OPEN}{labels.index(label)}{_CLOSE}"

    if event.country:
        own = _country_region(event.country)
        text = _country_regex(event.country).sub(lambda m: blank(region_of_word(m.group(0)) or own), text)
    text = _PLACE_WORDS.sub(lambda m: blank(region_of_word(m.group(0))), text)
    # "Holy Roman" split oddly, or two words of one region, read better as one blank.
    text = _SAME_PLACEHOLDERS.sub(r"\1", text)
    return _PLACEHOLDER.sub(lambda m: labels[int(m.group(1))], text)


def excerpt(event: Event) -> str:
    """The first sentence or two of the summary, with countries and nationalities hidden."""
    paragraph = next((p for p in (event.summary or "").split("\n") if p.strip()), "").strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", paragraph)
    text = ""
    for sentence in sentences:
        text = f"{text} {sentence}".strip()
        if len(text) >= EXCERPT_MIN:
            break
    text = _hide_place(text, event)  # first: the labels are longer than the words they replace
    if len(text) > EXCERPT_MAX:
        text = text[:EXCERPT_MAX].rsplit(" ", 1)[0]
        if text.count("[") > text.count("]"):  # do not cut a label in half
            text = text[:text.rindex("[")].rstrip()
        text += "…"
    return text


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
_MONTH_YEAR = re.compile(rf"\b((?:{MONTHS})(?:\s+\d{{1,2}})?[\])]?,?\s+)\d{{3,4}}(?!\d|[,.]\d)")  # a year after a month may touch a note: "1714Greg."
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


def _sentences(event: Event) -> list[str]:
    """The summary as sentences, paragraph after paragraph."""
    paragraphs = [p.strip() for p in (event.summary or "").split("\n") if p.strip()]
    return [s for p in paragraphs for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", p)]


def _excerpt_length(sentences: list[str]) -> int:
    """How many sentences the excerpt takes: until it is long enough (first paragraph only)."""
    text = ""
    for count, sentence in enumerate(sentences, 1):
        text = f"{text} {sentence}".strip()
        if len(text) >= EXCERPT_MIN:
            return count
    return len(sentences)


def more_description(event: Event, hard: bool = False) -> str:
    """The sentences of the summary that follow the excerpt (countries hidden, years too in hard mode)."""
    sentences = _sentences(event)
    rest = " ".join(sentences[_excerpt_length(sentences):]).strip()
    if not rest:
        return ""
    text = _hide_place(rest, event)
    if hard:
        text = hide_years(text)
    if len(text) > HINT_MAX_CHARS:
        text = text[:HINT_MAX_CHARS].rsplit(" ", 1)[0]
        if text.count("[") > text.count("]"):
            text = text[:text.rindex("[")].rstrip()
        text = text.rstrip(",;:") + "…"
    return text


def hint_dict(event: Event, level: int = 1, hard: bool = False) -> dict:
    """What a hint reveals. Level 1: more of the description (the region when there is none).
    Level 2: the country (the region when it is unknown)."""
    if level == 1:
        text = more_description(event, hard)
        if text:
            return {"level": 1, "kind": "description", "text": text}
        return {"level": 1, "kind": "region", "text": region_at(event.lat, event.lon)}
    if event.country:
        return {"level": 2, "kind": "country", "text": event.country}
    return {"level": 2, "kind": "region", "text": region_at(event.lat, event.lon)}


def apply_hint(points: int, level: int = 1) -> int:
    """A round's points after the penalty of the hints used (level 0 = none)."""
    return round(points * (1 - HINT_PENALTIES[level]))


def answer_dict(event: Event) -> dict:
    return {
        "id": public_id(event),
        "title": event.title,
        "lat": event.lat,
        "lon": event.lon,
        "country": event.country,
        "wiki_url": event.wiki_url,
        "year": event.year,
        "display_year": event.display_year,
        "date": event.date_label or event.display_year,
    }
