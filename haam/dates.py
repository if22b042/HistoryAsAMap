"""Year/date helpers.

Years are plain integers; negative numbers are BC (``-44`` = 44 BC). There is no
year 0 in historical numbering, so 1 BC (-1) is directly followed by AD 1 (1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)
_ERA_BC = r"(?:BCE|BC|B\.C\.E\.|B\.C\.)"
_ERA_AD = r"(?:AD|CE|A\.D\.|C\.E\.)"
# Numbers directly followed by these words are quantities, not years.
_NOT_A_YEAR = (
    r"(?!\s*(?:%|per\b|percent|men|soldiers|troops|people|ships|km|kilomet|miles?\b|"
    r"metres|meters|m\b|ft\b|feet|deaths|casualties|killed|wounded|years?\b|"
    r"days?\b|weeks?\b|months?\b|hours?\b|minutes?\b|acres?\b|hectares?\b|ha\b|square\b))"
)


@dataclass(frozen=True)
class ParsedDate:
    year: int
    label: str


def format_year(year: int | None) -> str:
    """``-44`` → ``"44 BC"``, ``1066`` → ``"1066"``, ``9`` → ``"AD 9"``."""
    if year is None:
        return ""
    if year < 0:
        return f"{-year} BC"
    if year < 1000:
        return f"AD {year}"
    return str(year)


def _signed(year: str, era: str | None) -> int:
    value = int(year)
    if era and re.fullmatch(_ERA_BC, era.strip()):
        return -value
    return value


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# Each pattern yields (year, label). They are tried in tiers: explicit dates and
# era-marked years first, bare years next, centuries last. Within a tier the match
# that appears earliest in the text wins.
_DAY_MONTH_YEAR = re.compile(
    rf"\b(?P<day>\d{{1,2}})(?:\s*[–-]\s*\d{{1,2}})?\s+(?P<month>{MONTHS})"
    rf"(?:\s*[–-]\s*\d{{1,2}}\s+(?:{MONTHS}))?,?\s+(?P<era1>{_ERA_AD}\s+)?"
    rf"(?P<year>\d{{1,4}})(?:\s+(?P<era2>{_ERA_BC}|{_ERA_AD}))?\b"
)
_MONTH_DAY_YEAR = re.compile(
    rf"\b(?P<month>{MONTHS})\s+(?P<day>\d{{1,2}}),\s+(?P<year>\d{{1,4}})"
    rf"(?:\s+(?P<era2>{_ERA_BC}|{_ERA_AD}))?\b"
)
_MONTH_YEAR = re.compile(
    rf"\b(?P<month>{MONTHS})\s+(?P<era1>{_ERA_AD}\s+)?(?P<year>\d{{1,4}})"
    rf"(?:\s+(?P<era2>{_ERA_BC}|{_ERA_AD}))?\b(?!,?\s*\d)"
)
_YEAR_RANGE_BC = re.compile(rf"\b(?P<year>\d{{1,5}})\s*[–-]\s*\d{{1,5}}\s*(?P<era2>{_ERA_BC})")
_YEAR_ERA_AFTER = re.compile(rf"\b(?P<year>\d{{1,5}})\s*(?P<era2>{_ERA_BC}|{_ERA_AD})(?![A-Za-z])")
_YEAR_ERA_BEFORE = re.compile(rf"\b(?P<era1>{_ERA_AD})\s*(?P<year>\d{{1,4}})\b")
# "(?![.,]\d)": the start of a larger number such as "104,000 acres" or "1,500.5" is no year.
_BARE_YEAR = re.compile(rf"(?<![\d,.])\b(?P<year>1\d{{3}}|20\d{{2}})\b(?![.,]\d){_NOT_A_YEAR}")
_IN_YEAR = re.compile(rf"\b(?:in|of|from)\s+(?P<year>[1-9]\d{{2}})\b(?![.,]\d){_NOT_A_YEAR}")
_CENTURY = re.compile(
    rf"\b(?P<num>\d{{1,2}})(?:st|nd|rd|th)[\s-]+century(?:\s+(?P<era2>{_ERA_BC}|{_ERA_AD}))?",
    re.IGNORECASE,
)


def _from_full_date(m: re.Match) -> ParsedDate:
    era = m.groupdict().get("era2") or m.groupdict().get("era1")
    year = _signed(m.group("year"), era)
    label = f"{int(m.group('day'))} {m.group('month')} {format_year(year)}"
    return ParsedDate(year, label)


def _from_month_year(m: re.Match) -> ParsedDate | None:
    era = m.group("era2") or m.group("era1")
    if not era and len(m.group("year")) < 3:
        return None  # "May 5" is a day, not a year
    year = _signed(m.group("year"), era)
    return ParsedDate(year, f"{m.group('month')} {format_year(year)}")


def _from_year(m: re.Match) -> ParsedDate:
    groups = m.groupdict()
    year = _signed(m.group("year"), groups.get("era2") or groups.get("era1"))
    return ParsedDate(year, format_year(year))


def _from_century(m: re.Match) -> ParsedDate:
    n = int(m.group("num"))
    bc = bool(m.group("era2")) and bool(re.fullmatch(_ERA_BC, m.group("era2")))
    # Use the first year of the century so it sorts correctly on the timeline.
    year = -(n * 100) if bc else (n - 1) * 100 + 1
    label = f"{_ordinal(n)} century" + (" BC" if bc else "")
    return ParsedDate(year, label)


_TIERS = (
    (
        (_DAY_MONTH_YEAR, _from_full_date),
        (_MONTH_DAY_YEAR, _from_full_date),
        (_MONTH_YEAR, _from_month_year),
        (_YEAR_RANGE_BC, _from_year),
        (_YEAR_ERA_AFTER, _from_year),
        (_YEAR_ERA_BEFORE, _from_year),
    ),
    ((_BARE_YEAR, _from_year), (_IN_YEAR, _from_year)),
    ((_CENTURY, _from_century),),
)


def _earliest_match(text: str, patterns) -> tuple[int, ParsedDate] | None:
    best: tuple[int, ParsedDate] | None = None
    for pattern, build in patterns:
        for m in pattern.finditer(text):
            if best is not None and m.start() >= best[0]:
                break
            parsed = build(m)
            if parsed is not None:
                best = (m.start(), parsed)
                break
    return best


def _earliest(text: str, patterns) -> ParsedDate | None:
    best = _earliest_match(text, patterns)
    return best[1] if best else None


def extract_date(text: str) -> ParsedDate | None:
    """Find the most likely event date in a Wikipedia intro.

    The first paragraph is searched before the rest of the intro, because that
    is where Wikipedia states when the event happened.
    """
    if not text:
        return None
    paragraphs = [p for p in text.split("\n") if p.strip()]
    candidates = [paragraphs[0], text] if paragraphs else [text]
    for chunk in candidates:
        for tier in _TIERS:
            found = _earliest(chunk, tier)
            if found and found.year != 0:
                return found
    return None


def explicit_date(text: str) -> ParsedDate | None:
    """A date stated in the first paragraph: a full date, month and year, or a year.

    Stricter than :func:`extract_date`: only the first paragraph is read and
    centuries ("17th century") are not accepted. Used when Wikidata has no date.
    """
    paragraphs = [p for p in (text or "").split("\n") if p.strip()]
    if not paragraphs:
        return None
    first = paragraphs[0]
    for tier in _TIERS[:2]:
        best = _earliest_match(first, tier)
        if best and best[1].year != 0:
            start, found = best
            # "from 17 September to 16 December 1658": the match is the end of a
            # range, so only its year is certain to be the event's.
            if _RANGE_END.search(first[max(0, start - 12):start]):
                return ParsedDate(found.year, format_year(found.year))
            return found
    return None


_RANGE_END = re.compile(r"(?:\bto|\band|\buntil|\btill|[–-])\s*$")


# "Battle of Tripoli (2018)", "Siege of Kandahar (1652–1653)", "Battle of X (44 BC)",
# "1906 San Francisco earthquake", "2018 Russia–United States summit".
_TITLE_YEAR_IN_BRACKETS = re.compile(
    rf"\((?P<year>\d{{1,4}})(?:\s*(?P<era2>{_ERA_BC}|{_ERA_AD}))?(?:\s*[–-]\s*\d{{1,4}}(?:\s*{_ERA_BC})?)?\)\s*$")
_TITLE_LEADING_YEAR = re.compile(r"^(?P<year>1\d{3}|20\d{2})(?=[\s–-])")


def date_from_title(title: str) -> ParsedDate | None:
    """The year an article title states, e.g. "Battle of Tripoli (2018)"."""
    m = _TITLE_YEAR_IN_BRACKETS.search(title or "")
    if m and (len(m.group("year")) >= 3 or m.group("era2")):
        year = _signed(m.group("year"), m.group("era2"))
        if not m.group("era2") and re.search(rf"[–-]\s*\d{{1,4}}\s*{_ERA_BC}\)", title):
            year = -year  # "(218–201 BC)": the era applies to both years
        return ParsedDate(year, format_year(year)) if year else None
    m = _TITLE_LEADING_YEAR.match(title or "")
    if m:
        year = int(m.group("year"))
        return ParsedDate(year, format_year(year))
    return None


def article_date(title: str, intro: str) -> tuple[ParsedDate, str] | None:
    """Date of an event from its Wikipedia article, with where it was found.

    A year in the title wins (it names the event); the first paragraph's date is
    used when it agrees with the title's year (it is more precise) or when the
    title has no year.
    """
    from_title, from_intro = date_from_title(title), explicit_date(intro)
    if from_title and from_intro and from_intro.year == from_title.year:
        return from_intro, "Wikipedia title and intro"
    if from_title:
        return from_title, "Wikipedia title"
    if from_intro:
        return from_intro, "Wikipedia intro"
    return None


_YEAR_INPUT = re.compile(
    rf"^\s*(?:(?P<pre>{_ERA_AD})\s*)?(?P<sign>-)?(?P<num>\d{{1,5}})\s*(?P<post>{_ERA_BC}|{_ERA_AD})?\s*$",
    re.IGNORECASE,
)


def parse_year_input(value: str) -> int | None:
    """Parse a year typed by a person: ``"1066"``, ``"-44"``, ``"44 BC"``, ``"AD 9"``, ``"9 CE"``."""
    m = _YEAR_INPUT.match(value or "")
    if not m or (m.group("sign") and (m.group("pre") or m.group("post"))):
        return None
    year = int(m.group("num"))
    post = (m.group("post") or "").upper()
    if m.group("sign") or post in {"BC", "BCE", "B.C.", "B.C.E."}:
        year = -year
    return year or None


# Wikidata time precision codes: https://www.wikidata.org/wiki/Help:Dates
_PRECISION_DAY, _PRECISION_MONTH, _PRECISION_YEAR = 11, 10, 9
_MONTH_NAMES = MONTHS.split("|")


def parse_wikidata_time(value: dict) -> ParsedDate | None:
    """Convert a Wikidata time datavalue (``{"time": "-0480-08-01T00:00:00Z", ...}``)."""
    m = re.fullmatch(r"([+-])(\d+)-(\d\d)-(\d\d)T.*", value.get("time", ""))
    if not m:
        return None
    sign, year_s, month_s, day_s = m.groups()
    year = int(year_s) * (-1 if sign == "-" else 1)
    if year == 0:
        return None
    precision = value.get("precision", _PRECISION_YEAR)
    month, day = int(month_s), int(day_s)
    if precision >= _PRECISION_DAY and month and day:
        label = f"{day} {_MONTH_NAMES[month - 1]} {format_year(year)}"
    elif precision == _PRECISION_MONTH and month:
        label = f"{_MONTH_NAMES[month - 1]} {format_year(year)}"
    else:
        label = format_year(year)
    return ParsedDate(year, label)
