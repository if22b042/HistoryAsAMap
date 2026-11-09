"""Export historical events from Wikidata to a CSV that fills the Event model.

Pipeline (``flask haam export-wikidata``):

1. **Discover** candidates per event type with SPARQL: items that are an
   instance of the type or a subclass, have an English Wikipedia article and a
   date, and are not fictional.
2. **Fetch** their full data in batches of 50 (``wbgetentities``) plus, in
   batches, the coordinates of their locations, labels for countries and
   "part of" items, and the article introductions (20 per request).
3. **Validate** every candidate with :func:`validate` – the single place that
   decides "is this an event we can map?" – and write accepted rows to the
   events CSV and rejected ones, with the reason, to a second CSV.
"""

from __future__ import annotations

import csv
import logging
import re
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from haam.data.event_types import (AREA_ROOTS, CATEGORY_CLASS_EXCLUSIONS, CATEGORY_CLASSES, EARTH, EVENT_TYPES, NOT_EVENT_ROOTS,
                                   NOT_EVENTS, ORGANISATION_ROOTS, ORGANISATION_TYPES, PLACE_ROOTS,
                                   REFINED_CATEGORIES)
from haam.dates import ParsedDate, article_date, parse_wikidata_time
from haam.tagging import Tagger
from haam.wikipedia import canonical_url

logger = logging.getLogger(__name__)

SPARQL_URL = "https://query.wikidata.org/sparql"
API_URL = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

P_INSTANCE_OF, P_POINT_IN_TIME, P_START_TIME = "P31", "P585", "P580"
P_END_TIME, P_INCEPTION = "P582", "P571"
WIKIDATA_DATE_PROPS = (P_POINT_IN_TIME, P_START_TIME, P_END_TIME, P_INCEPTION)
P_COORDINATES, P_COUNTRY, P_PART_OF = "P625", "P17", "P361"
P_HAS_CAUSE, P_IMMEDIATE_CAUSE = "P828", "P1478"
LOCATION_PROPS = ("P276", "P1071", "P740")  # location, location of creation, location of formation
MIN_PRECISION = 9  # Wikidata time precision: 9 = year, 10 = month, 11 = day

EVENT_COLUMNS = [
    "wikidata_id", "wiki_page_id", "url", "title", "year", "date", "lat", "lon", "country",
    "category", "status", "tags", "summary", "event_type", "date_source", "coord_source",
]
REJECT_COLUMNS = ["wikidata_id", "title", "event_type", "reason"]

Reporter = Callable[[str], None]


# --------------------------------------------------------------- validation

@dataclass
class Candidate:
    """Everything the validator needs about one Wikidata item."""

    qid: str
    event_type: str  # Wikidata ID of the matched EVENT_TYPES entry
    title: str | None = None  # English Wikipedia article title
    claims: dict = field(default_factory=dict)
    # Coordinates of locations that are specific places (towns, buildings...).
    location_coords: dict[str, tuple[float, float]] = field(default_factory=dict)
    # Locations that are countries, regions or seas: never used, only named in the reason.
    area_locations: dict[str, str] = field(default_factory=dict)
    # Date from the Wikipedia article, used only when Wikidata has none.
    text_date: ParsedDate | None = None
    text_date_source: str = ""


@dataclass
class Verdict:
    ok: bool
    reason: str = ""
    year: int | None = None
    date_label: str = ""
    date_source: str = ""
    lat: float | None = None
    lon: float | None = None
    coord_source: str = ""


def _best_claims(claims: dict, prop: str) -> list[dict]:
    """Claims of a property with a value, preferred rank first, deprecated dropped."""
    usable = [c for c in claims.get(prop, [])
              if c.get("rank") != "deprecated" and c.get("mainsnak", {}).get("snaktype") == "value"]
    preferred = [c for c in usable if c.get("rank") == "preferred"]
    return preferred or usable


def _values(claims: dict, prop: str) -> list:
    return [c["mainsnak"]["datavalue"]["value"] for c in _best_claims(claims, prop)]


def item_ids(claims: dict, prop: str) -> list[str]:
    return [v["id"] for v in _values(claims, prop) if isinstance(v, dict) and "id" in v]


def _earth_coordinates(value: dict) -> tuple[float, float] | None:
    if value.get("globe", EARTH) != EARTH:
        return None  # e.g. the Moon landing site
    lat, lon = value.get("latitude"), value.get("longitude")
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return float(lat), float(lon)


def is_specific_place(types: Iterable[str], place_classes: set[str], area_classes: set[str]) -> bool:
    """True for towns, buildings, streets...; False for countries, regions and seas."""
    types = set(types)
    if types & place_classes:
        return True
    return not types & area_classes


def validate(candidate: Candidate, *, today: date | None = None,
             blocked_types: dict[str, str] | None = None,
             organisation_types: dict[str, str] | None = None) -> Verdict:
    """Decide whether a Wikidata item is a historical event we can put on the map.

    Rules, in order (the first failing rule is the rejection reason):

    1. it has an English Wikipedia article;
    2. it is an instance of an accepted event type (guaranteed by discovery,
       re-checked here: ``event_type`` must be one of EVENT_TYPES);
    3. it is not also directly typed as a non-event (settlement, building,
       battlefield, list, category, recurring event, ...) or as any subclass
       of fictional entity (``blocked_types``, fetched once per export);
       and, if it has no point in time or start time, it is not typed as a
       military unit, state or organisation (``organisation_types`` plus
       ORGANISATION_TYPES);
    4. it has a date precise to at least a year, not in the future and not
       year 0: on Wikidata its point in time (P585), start time (P580), end
       time (P582) or inception (P571), in that order; failing those, a year
       in the article's title or a date in its first paragraph
       (``text_date``, see :func:`haam.dates.article_date`);
    5. it has Earth coordinates – its own (P625) or those of its location /
       place of creation / place of formation, if that location is a specific
       place (a town, a building...) and not a country, region or sea.

    Two more rules need the Wikipedia article and are applied in the export:
    the article the link leads to (after redirects) must belong to the same
    Wikidata item (6), and must not be a list, timeline or disambiguation
    page (7).
    """
    today = today or date.today()
    if not candidate.title:
        return Verdict(False, "no English Wikipedia article")
    if candidate.event_type not in {qid for qid, _, _ in EVENT_TYPES}:
        return Verdict(False, f"type {candidate.event_type} is not an accepted event type")

    types = set(item_ids(candidate.claims, P_INSTANCE_OF))
    not_events = {**(blocked_types or {}), **NOT_EVENTS}
    blocked = sorted({not_events[t] for t in types & not_events.keys()})
    if blocked:
        return Verdict(False, f"also an instance of: {', '.join(blocked)}")

    # 3b. Without a point in time or start time, an item typed as a military unit,
    # state or organisation is an organisation (founded, not happened).
    own_date = any(_values(candidate.claims, prop) for prop in (P_POINT_IN_TIME, P_START_TIME))
    if not own_date:
        organisations = {**(organisation_types or {}), **ORGANISATION_TYPES}
        kinds = sorted({organisations[t] for t in types & organisations.keys()})
        if kinds:
            return Verdict(False, f"an organisation or state, not an event: {', '.join(kinds)}")

    parsed, source, vague = None, "", False
    for prop in WIKIDATA_DATE_PROPS:
        for value in _values(candidate.claims, prop):
            if value.get("precision", 0) < MIN_PRECISION:
                vague = True
                continue
            parsed = parse_wikidata_time(value)
            if parsed:
                source = prop
                break
        if parsed:
            break
    if parsed is None and candidate.text_date is not None:
        parsed, source = candidate.text_date, candidate.text_date_source
    if parsed is None:
        return Verdict(False, "date less precise than a year" if vague else "no usable date on Wikidata or Wikipedia")
    if parsed.year > today.year:
        return Verdict(False, f"date in the future ({parsed.year})")

    coords, coord_source = None, ""
    for value in _values(candidate.claims, P_COORDINATES):
        coords = _earth_coordinates(value)
        if coords:
            coord_source = P_COORDINATES
            break
    if coords is None:
        for prop in LOCATION_PROPS:
            for location in item_ids(candidate.claims, prop):
                if location in candidate.location_coords:
                    coords, coord_source = candidate.location_coords[location], f"{prop}:{location}"
                    break
            if coords:
                break
    if coords is None:
        areas = [candidate.area_locations[loc] for prop in LOCATION_PROPS
                 for loc in item_ids(candidate.claims, prop) if loc in candidate.area_locations]
        if areas:
            return Verdict(False, f"location is a country or region, not a specific place: {areas[0]}")
        return Verdict(False, "no coordinates (P625) on the item or its location")

    return Verdict(True, year=parsed.year, date_label=parsed.label, date_source=source,
                   lat=round(coords[0], 6), lon=round(coords[1], 6), coord_source=coord_source)


# --------------------------------------------------------------- categories

def refine_category(base: str, types: Iterable[str], causes: Iterable[str],
                    classes: dict[str, set[str]]) -> str:
    """The category of an item, from its broad category and its P31 classes.

    ``base`` comes from the discovery type (or is the current category);
    ``types`` are the item's P31 classes, ``causes`` its P828 / P1478 values;
    ``classes`` maps each group of ``CATEGORY_CLASSES`` to its classes and all
    their subclasses (see :func:`category_classes`). The rules and their order
    are documented next to ``CATEGORY_CLASSES``.
    """
    if base not in REFINED_CATEGORIES:
        return base
    types = set(types)

    def has(group: str) -> bool:
        return bool(types & classes.get(group, set()))

    if has("violence"):
        return "violence"
    if base == "other":
        return base
    if has("natural"):
        return "natural"
    if has("human_made"):
        return "disaster"
    if has("wildfire"):
        return "disaster" if set(causes) & classes.get("human_cause", set()) else "natural"
    if has("fire"):
        return "disaster"
    return base


def category_classes(client: "WikidataClient") -> dict[str, set[str]]:
    """Every group of ``CATEGORY_CLASSES`` with all subclasses of its classes."""
    result = {}
    for group, roots in CATEGORY_CLASSES.items():
        classes = set().union(*(client.subclasses(root) for root in roots))
        for excluded in CATEGORY_CLASS_EXCLUSIONS.get(group, {}):
            classes -= client.subclasses(excluded)
        result[group] = classes
    return result


def item_causes(claims: dict) -> list[str]:
    return item_ids(claims, P_HAS_CAUSE) + item_ids(claims, P_IMMEDIATE_CAUSE)


# ------------------------------------------------------------------- client

@dataclass
class Location:
    coords: tuple[float, float]
    types: set[str]
    label: str


class WikidataClient:
    def __init__(self, user_agent: str, *, pause: float = 0.2, timeout: float = 90):
        self.pause = pause
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        retry = Retry(total=5, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                      respect_retry_after_header=True, allowed_methods=("GET", "POST"))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _get(self, url: str, params: dict) -> dict:
        time.sleep(self.pause)
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def discover(self, type_qid: str, undated: bool = False) -> list[tuple[str, str]]:
        """``(item id, English Wikipedia title)`` of instances of a type or its subclasses.

        By default only items with a point in time or start time; with
        ``undated`` only the items that have neither (their date then comes from
        their end time, inception or Wikipedia article).

        Fictional items are filtered later in :func:`validate`: a per-item
        subclass check in SPARQL makes these queries time out.
        """
        if undated:
            date_filter = "FILTER NOT EXISTS { ?item wdt:P585 [] } FILTER NOT EXISTS { ?item wdt:P580 [] }"
        else:
            date_filter = "{ ?item wdt:P585 [] } UNION { ?item wdt:P580 [] }"
        query = f"""
        SELECT DISTINCT ?item ?title WHERE {{
          ?item wdt:P31/wdt:P279* wd:{type_qid} .
          {date_filter}
          ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title .
        }}"""
        rows = self._sparql(query)
        return [(r["item"]["value"].rsplit("/", 1)[1], r["title"]["value"]) for r in rows]

    def _sparql(self, query: str, attempts: int = 4) -> list[dict]:
        """Run a query; retry when the server cuts a large response off mid-stream.

        The query service sends HTTP 200 and then truncates the JSON when it
        hits its time limit, so a parse error means "try again", not "no data".
        """
        for attempt in range(1, attempts + 1):
            time.sleep(self.pause if attempt == 1 else 15 * attempt)
            response = self.session.post(SPARQL_URL, data={"query": query},
                                         headers={"Accept": "application/sparql-results+json"},
                                         timeout=self.timeout)
            response.raise_for_status()
            try:
                return response.json()["results"]["bindings"]
            except ValueError:
                logger.warning("Truncated SPARQL response (attempt %d of %d)", attempt, attempts)
        raise ValueError(f"SPARQL response still truncated after {attempts} attempts")

    def subclasses(self, root: str) -> set[str]:
        """The class itself and all its subclasses (e.g. every kind of fictional entity)."""
        rows = self._sparql(f"SELECT ?c WHERE {{ ?c wdt:P279* wd:{root} }}")
        return {r["c"]["value"].rsplit("/", 1)[1] for r in rows}

    def statements(self, ids: Iterable[str], props: Iterable[str] = (P_INSTANCE_OF, P_HAS_CAUSE,
                                                                     P_IMMEDIATE_CAUSE)) -> dict[str, dict[str, list[str]]]:
        """``item → property → [item ids]`` for a few item-valued properties, via SPARQL.

        Much lighter than :meth:`entities` when only a couple of properties are needed.
        """
        result: dict[str, dict[str, list[str]]] = {}
        wanted = " ".join(f"wdt:{p}" for p in props)
        for chunk in chunks(sorted(set(ids)), 400):
            values = " ".join(f"wd:{qid}" for qid in chunk)
            rows = self._sparql(f"""
            SELECT ?item ?p ?v WHERE {{
              VALUES ?item {{ {values} }} VALUES ?p {{ {wanted} }}
              ?item ?p ?v . FILTER(isIRI(?v))
            }}""")
            for row in rows:
                item, prop, value = (row[k]["value"].rsplit("/", 1)[1] for k in ("item", "p", "v"))
                result.setdefault(item, {}).setdefault(prop, []).append(value)
        return result

    def entities(self, ids: list[str], props: str = "claims") -> dict:
        result = {}
        for chunk in chunks(ids, 50):
            data = self._get(API_URL, {"action": "wbgetentities", "ids": "|".join(chunk), "props": props,
                                       "languages": "en", "format": "json", "maxlag": 5})
            result.update(data.get("entities", {}))
        return result

    def labels(self, ids: Iterable[str]) -> dict[str, str]:
        entities = self.entities(sorted(set(ids)), props="labels")
        return {qid: e.get("labels", {}).get("en", {}).get("value", "") for qid, e in entities.items()}

    def locations(self, ids: Iterable[str]) -> dict[str, Location]:
        """Coordinates, types and English label of location items that have Earth coordinates."""
        result = {}
        for qid, entity in self.entities(sorted(set(ids)), props="claims|labels").items():
            claims = entity.get("claims", {})
            for value in _values(claims, P_COORDINATES):
                coords = _earth_coordinates(value)
                if coords:
                    label = entity.get("labels", {}).get("en", {}).get("value", "") or qid
                    result[qid] = Location(coords, set(item_ids(claims, P_INSTANCE_OF)), label)
                    break
        return result

    def introductions(self, titles: list[str]) -> dict[str, tuple[int, str, str, str | None]]:
        """``title → (page id, canonical title, first paragraph, the page's Wikidata id)``.

        Follows redirects; the Wikidata id lets the caller detect redirects that
        lead to a different topic (e.g. a battle redirecting to a painter).
        """
        result: dict[str, tuple[int, str, str]] = {}
        for chunk in chunks(titles, 20):  # the API returns at most 20 intro extracts per request
            data = self._get(WIKIPEDIA_API, {
                "action": "query", "format": "json", "formatversion": 2, "redirects": 1,
                "prop": "extracts|pageprops", "ppprop": "wikibase_item",
                "exintro": 1, "explaintext": 1, "exlimit": 20,
                "titles": "|".join(chunk), "maxlag": 5,
            })
            query = data.get("query", {})
            renamed = {r["from"]: r["to"] for r in query.get("normalized", []) + query.get("redirects", [])}
            pages = {p["title"]: p for p in query.get("pages", []) if not p.get("missing")}
            for title in chunk:
                final = renamed.get(renamed.get(title, title), renamed.get(title, title))
                page = pages.get(final)
                if page:
                    summary = pick_introduction(page.get("extract") or "")
                    result[title] = (page["pageid"], page["title"], summary,
                                     page.get("pageprops", {}).get("wikibase_item"))
        return result


_JUNK_LINE = re.compile(
    r"^\s*([|>=*{}#\[\]（(]|edit$)|page is partially a translation|campaignbox", re.IGNORECASE)
_NOT_AN_ARTICLE_TITLE = re.compile(r"^(list|lists|timeline|outline|index) of\b", re.IGNORECASE)


def pick_introduction(extract: str) -> str:
    """First paragraph of an intro extract that reads like prose.

    Plain-text extracts sometimes start with infobox or template leftovers
    ("|campaignbox = ...", "> 600 killed", "Edit"), which must be skipped.
    """
    paragraphs = [p.strip() for p in extract.split("\n") if p.strip()]
    for paragraph in paragraphs:
        if len(paragraph) >= 40 and not _JUNK_LINE.search(paragraph):
            return paragraph
    return ""


def article_problem(title: str, summary: str) -> str | None:
    """Reasons an article is not about a single event, judged from its text."""
    if _NOT_AN_ARTICLE_TITLE.search(title):
        return "Wikipedia article is a list or timeline"
    if re.search(r"\bmay (also )?refer to\b", summary[:200], re.IGNORECASE):
        return "Wikipedia article is a disambiguation page"
    return None


def chunks(items: list, size: int) -> Iterator[list]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


# ------------------------------------------------------------------- export

@dataclass
class ExportStats:
    candidates: int = 0
    accepted: int = 0
    rejected: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    failed_types: list[str] = field(default_factory=list)  # discovery failed: the export is incomplete

    def reject(self, reason: str) -> None:
        self.rejected += 1
        key = reason.split(":")[0].split(" (")[0]
        self.reasons[key] = self.reasons.get(key, 0) + 1


def export(
    client: WikidataClient,
    events_path: str,
    rejected_path: str,
    *,
    type_ids: list[str] | None = None,
    limit_per_type: int | None = None,
    status: str = "approved",
    tag_names: Iterable[str] = (),
    batch_size: int = 500,
    undated: bool | None = None,
    report: Reporter = print,
) -> ExportStats:
    """Run the whole pipeline and write the two CSV files.

    By default both kinds of item are exported: those with a point in time or
    start time, and those without one, dated from their end time, inception or
    Wikipedia article. ``undated=False`` / ``True`` limits it to one kind (see
    :meth:`WikidataClient.discover`).
    """
    stats = ExportStats()
    types = [t for t in EVENT_TYPES if not type_ids or t[0] in type_ids]
    tagger = Tagger(client, tag_names)

    blocked_types: dict[str, str] = {}
    for root, label in NOT_EVENT_ROOTS.items():
        classes = client.subclasses(root)
        blocked_types.update({qid: label for qid in classes})
        report(f"  {len(classes)} kinds of {label} will be rejected")

    organisation_types: dict[str, str] = {}
    for root, label in ORGANISATION_ROOTS.items():
        organisation_types.update({qid: label for qid in client.subclasses(root)})
    report(f"  {len(organisation_types)} kinds of military unit / state rejected when undated")

    place_classes = set().union(*(client.subclasses(root) for root in PLACE_ROOTS))
    area_classes = set().union(*(client.subclasses(root) for root in AREA_ROOTS))
    report(f"  locations: {len(place_classes)} kinds of specific place, {len(area_classes)} kinds of area")
    refine_classes = category_classes(client)

    # 1. discovery – the first type in EVENT_TYPES that finds an item wins
    candidates: dict[str, Candidate] = {}
    kinds = [False, True] if undated is None else [undated]
    for qid, label, _ in types:
        found = []
        try:
            for kind in kinds:
                found += client.discover(qid, undated=kind)
        except (requests.RequestException, ValueError, KeyError) as exc:
            report(f"! {label}: discovery failed ({exc}); skipped")
            stats.failed_types.append(f"{label} ({qid})")
            continue
        new = [(item, title) for item, title in found if item not in candidates]
        if limit_per_type:
            new = new[:limit_per_type]
        for item, title in new:
            candidates[item] = Candidate(item, qid, title)
        report(f"  {label}: {len(found)} found, {len(new)} new")
    stats.candidates = len(candidates)
    report(f"{stats.candidates} candidates in total")

    categories = {qid: category for qid, _, category in EVENT_TYPES}
    labels_by_type = {qid: label for qid, label, _ in EVENT_TYPES}

    with open(events_path, "w", newline="", encoding="utf-8") as events_file, \
            open(rejected_path, "w", newline="", encoding="utf-8") as rejected_file:
        events_csv = csv.DictWriter(events_file, fieldnames=EVENT_COLUMNS)
        rejected_csv = csv.DictWriter(rejected_file, fieldnames=REJECT_COLUMNS)
        events_csv.writeheader()
        rejected_csv.writeheader()

        ids = list(candidates)
        for number, batch in enumerate(chunks(ids, batch_size), start=1):
            _process_batch(client, [candidates[i] for i in batch], events_csv, rejected_csv, stats,
                           categories, labels_by_type, tagger, status, blocked_types,
                           place_classes, area_classes, organisation_types, refine_classes)
            events_file.flush()
            rejected_file.flush()
            done = min(number * batch_size, len(ids))
            report(f"  {done}/{len(ids)} checked: {stats.accepted} accepted, {stats.rejected} rejected")
    return stats


def _has_wikidata_date(claims: dict) -> bool:
    return any(value.get("precision", 0) >= MIN_PRECISION and parse_wikidata_time(value)
               for prop in WIKIDATA_DATE_PROPS for value in _values(claims, prop))


def _process_batch(client, batch, events_csv, rejected_csv, stats, categories, labels_by_type,
                   tagger, status, blocked_types, place_classes, area_classes, organisation_types,
                   refine_classes=None):
    entities = client.entities([c.qid for c in batch])
    for candidate in batch:
        candidate.claims = entities.get(candidate.qid, {}).get("claims", {})

    # Locations only for items without their own coordinates (treaties, conferences...).
    need_location = {loc for c in batch if not _values(c.claims, P_COORDINATES)
                     for prop in LOCATION_PROPS for loc in item_ids(c.claims, prop)}
    locations = client.locations(need_location) if need_location else {}
    location_coords, area_locations = {}, {}
    for qid, location in locations.items():
        if is_specific_place(location.types, place_classes, area_classes):
            location_coords[qid] = location.coords
        else:
            area_locations[qid] = location.label
    for candidate in batch:
        candidate.location_coords = location_coords
        candidate.area_locations = area_locations

    # Items without a usable Wikidata date: read the date from their article first.
    undated = [c for c in batch if c.title and not _has_wikidata_date(c.claims)]
    intros = client.introductions([c.title for c in undated]) if undated else {}
    for candidate in undated:
        intro = intros.get(candidate.title)
        found = article_date(intro[1], intro[2]) if intro else None
        if found:
            candidate.text_date, candidate.text_date_source = found

    verdicts = {c.qid: validate(c, blocked_types=blocked_types, organisation_types=organisation_types)
                for c in batch}
    accepted = [c for c in batch if verdicts[c.qid].ok]
    missing = [c.title for c in accepted if c.title not in intros]
    if missing:
        intros.update(client.introductions(missing))
    label_ids = {i for c in accepted for i in item_ids(c.claims, P_COUNTRY)}
    labels = client.labels(label_ids) if label_ids else {}
    # Tags from the whole "part of" chain (battle → campaign → war → ...), see haam.tagging.
    tags_by_qid = tagger.tags({c.qid: item_ids(c.claims, P_PART_OF) for c in accepted},
                              {c.qid: verdicts[c.qid].year for c in accepted})

    for candidate in batch:
        verdict = verdicts[candidate.qid]
        event_type = labels_by_type[candidate.event_type]
        intro = intros.get(candidate.title) if verdict.ok else None
        if verdict.ok and intro is None:
            verdict = Verdict(False, "Wikipedia article not found")
        elif verdict.ok and intro[3] and intro[3] != candidate.qid:
            # Rule 6: the article we end up on must be about this very item.
            verdict = Verdict(False, f"Wikipedia link leads to another topic: {intro[1]} ({intro[3]})")
        elif verdict.ok and article_problem(intro[1], intro[2]):
            # Rule 7: and it must be a normal article, not a list or disambiguation page.
            verdict = Verdict(False, article_problem(intro[1], intro[2]))
        if not verdict.ok:
            stats.reject(verdict.reason)
            rejected_csv.writerow({"wikidata_id": candidate.qid, "title": candidate.title or "",
                                   "event_type": event_type, "reason": verdict.reason})
            continue

        page_id, title, summary, _ = intro
        countries = [labels.get(i, "") for i in item_ids(candidate.claims, P_COUNTRY)]
        tags = tags_by_qid.get(candidate.qid, [])
        events_csv.writerow({
            "wikidata_id": candidate.qid,
            "wiki_page_id": page_id,
            "url": canonical_url(title),
            "title": title,
            "year": verdict.year,
            "date": verdict.date_label,
            "lat": verdict.lat,
            "lon": verdict.lon,
            "country": next((c for c in countries if c), ""),
            "category": refine_category(categories[candidate.event_type],
                                        item_ids(candidate.claims, P_INSTANCE_OF),
                                        item_causes(candidate.claims), refine_classes or {}),
            # Dated only by "inception": often an organisation or project rather than an
            # event (Project Artichoke, Barents Region), so it waits for review.
            "status": "pending" if verdict.date_source == P_INCEPTION else status,
            "tags": ";".join(tags),
            "summary": summary or title,
            "event_type": event_type,
            "date_source": verdict.date_source,
            "coord_source": verdict.coord_source,
        })
        stats.accepted += 1
