# History As A Map: 30 new features, ranked

*25 Nov 2026, branch `claude/curated-collections` at `2249408`. Nothing here is built yet.*

**The owner's decision on each feature is in [FEATURE-DECISIONS.md](FEATURE-DECISIONS.md).**

## How this was made

Five read-only passes, run as subagents:

1. **Code audit.** For each candidate, checked whether it was built, half built or open.
   Two candidates turned out to be built already and were replaced (see the end).
2. **Data measurements** on `instance/haam.db`: 19,125 approved events, 29 collections.
3. **Wikidata sample.** 400 events stratified by category, plus 100 Siege/War/Campaign
   titles, plus 13 famous events that are missing. 19 public API requests.
4. **Feasibility review in the code**, two passes of 15 features each. They give the
   files, migrations, feed changes, risky areas and traps.
5. **Product review** from three users: a visitor arriving from Google, a teacher or
   student, and a returning game player.

Every feature was checked against the list refused on 16 Nov: borders overlay, export of
collections, bulk import into a collection, people filter, year histogram on the slider,
offline app, "On this day" feed, other languages. None of the 30 is on it. Three come
close; their entries say so.

## Scoring

| Score | Meaning |
|---|---|
| **N**ecessity 1–5 | How strongly the measured data or the code shows a real gap |
| **I**mpact 1–5 | How many users it helps, and how much |
| **T**hesis 1–5 | How well it shows the thesis idea: exploring history in place and time, data quality, trust |
| **F**easibility 1–5 | 5 = small and safe. 1 = blocked by missing data or a large rewrite |
| Effort | S ≤ ½ day · M ≤ 2 days · L > 2 days |

**Priority = (2·N + I + T) × F / 4**, at most 25. Necessity counts double because it
rests on evidence. Feasibility multiplies, because a valuable feature that cannot be
built well is worth little now.

## The ranking

| # | Feature | N | I | T | F | Effort | Priority | Migration | Risky area |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Search the full summaries | 5 | 5 | 4 | 4 | M | **19.0** | no | no |
| 2 | "What happened here": a place over time | 3 | 4 | 5 | 5 | S–M | **18.8** | no | no |
| 3 | Where each date and place came from + `/quality` page | 3 | 3 | 5 | 5 | M | **17.5** | yes (additive) | `models.py` |
| 4 | Story mode for collections and tags | 4 | 5 | 4 | 4 | M | **17.0** | no | no |
| 5 | Tag landing pages (`/tag/<slug>`) | 3 | 4 | 3 | 5 | S–M | **16.3** | no | no |
| 6 | Importance score (sitelinks) | 4 | 4 | 4 | 4 | M–L | **16.0** | yes | `models.py` |
| 7 | Region / country filter | 4 | 4 | 3 | 4 | M | **15.0** | yes | `models.py` |
| 8 | Related events in the map's details panel | 3 | 3 | 3 | 5 | S | **15.0** | no | no |
| 9 | Category donuts on clusters + legend | 3 | 3 | 3 | 5 | S–M | **15.0** | no | no |
| 10 | Keyboard and screen-reader route through the map | 3 | 3 | 3 | 4 | M | **12.0** | no | no |
| 11 | Tag hierarchy, era browser, related tags | 3 | 3 | 3 | 4 | L | **12.0** | no | no |
| 12 | Canon import of missing famous events | 4 | 4 | 3 | 3 | L | **11.3** | no | no |
| 13 | Game by tag | 2 | 3 | 2 | 5 | M | **11.3** | no | no |
| 14 | Link collection entries to main-map events | 3 | 3 | 2 | 4 | M | **11.0** | no | `collections_service.py` |
| 15 | Time-lapse with trails and presets | 2 | 3 | 4 | 4 | M | **11.0** | no | no |
| 16 | "The world in year X" | 2 | 3 | 4 | 4 | S–M | **11.0** | no | no |
| 17 | Tag suggestions for untagged events | 4 | 3 | 3 | 3 | M–L | **10.5** | no | no |
| 18 | Open dataset (CSV / GeoJSON of events) | 2 | 2 | 4 | 4 | M | **10.0** | no | no |
| 19 | schema.org `Event` data on event pages | 2 | 2 | 2 | 5 | S | **10.0** | no | no |
| 20 | "Open on HAAM" from Wikipedia | 2 | 2 | 2 | 5 | S–M | **10.0** | no | no |
| 21 | Lead images on events | 3 | 4 | 2 | 3 | L | **9.0** | yes | `models.py` |
| 22 | Review-queue warnings (duplicates, year not in text) | 2 | 2 | 3 | 4 | M | **9.0** | no | no |
| 23 | Start and end dates | 4 | 4 | 5 | 2 | L | **8.5** | yes | `models.py`, `migrations/` |
| 24 | Wikidata fact box | 2 | 3 | 2 | 3 | M–L | **6.8** | yes | `models.py` |
| 25 | Editor audit log with undo | 2 | 2 | 2 | 3 | L | **6.0** | yes | `models.py` |
| 26 | Compare two views on one map | 2 | 3 | 4 | 2 | L | **5.5** | no | no |
| 27 | Date-precision display | 1 | 2 | 3 | 3 | M | **5.3** | yes | `models.py` |
| 28 | Collection history and undo | 2 | 2 | 1 | 3 | L | **5.3** | yes | `collections_service.py` |
| 29 | Classroom board without accounts | 2 | 3 | 3 | 2 | L | **5.0** | yes | `models.py` |
| 30 | Cause and effect links from Wikidata | 1 | 2 | 3 | 1 | L | **1.8** | yes | `models.py` |

Ties are broken by necessity, then by effort.

**Where the formula and my judgement differ.** Start and end dates (#23) rank low only
because they are hard. They are the feature that most changes what the map *means*, and
69% of sieges, wars and campaigns have both dates on Wikidata. If the thesis argues
about time, build #23 anyway, in the reduced form its entry describes, together with #6
and #3 in a single migration.

---

## Facts that shape several features

- **The data is loaded in the browser.** 19k events arrive as versioned chunks
  (`feed.py`, `FORMAT = 3`). A new column in the chunks means a format bump and a new
  fingerprint input (`feed._compute_state`). Data that is only needed on click belongs
  in `/api/events/<id>`, not in the chunks.
- **`map.js` is about 2,400 lines with one global `state` and no JS tests.** Playwright
  is installed in `.venv` but no test uses it, and nothing in CI runs it. Nine of the 30
  features are verifiable only in a browser. A few Playwright smoke tests (load, filter,
  open event, collection map, one game round) should come before the `map.js` features
  #2, #4, #9, #15 and #26.
- **The content security policy has `connect-src 'self'`.** The browser can never call
  Wikidata or Wikipedia itself. Every new piece of Wikidata data is fetched by a CLI
  command, stored, and served by us.
- **`sync-wikidata` deletes imported events that are missing from the CSV**, and it
  updates with bulk `UPDATE` statements that bypass ORM events and triggers. Anything
  that imports outside the CSV (#12) or indexes text (#1) has to allow for both.
- **Wikidata coverage** (sample of 400; the military row is closest to the real mix):

  | Property | All | Military | Siege/War/Campaign titles |
  |---|---|---|---|
  | Start and end (P580 + P582) | 24% | 39% | 69% |
  | Part of (P361) | 52% | 81% | 75% |
  | Image (P18) | 53% | 54% | 54% |
  | Participants (P710) | 28% | 38% | 43% |
  | Deaths (P1120) | 12% (78% of disasters) | 1% | 4% |
  | Country (P17), a single item | 80% | 81% | 85% |
  | Has cause / has effect (P828 / P1542) | 2% / 0% | 0% / 1% | 3% / 2% |
  | Winner (P1346) | 0% | 0% | 0% |

  Sitelinks (Wikipedia language editions): median 6, p90 19, p99 48. Famous events
  score 58–108.

---

## 1. Search the full summaries · Priority 19.0

**What.** Let the text search match the whole summary, not the first 300 characters.

**Necessity 5.** Search is the main task on the site, and it still misses matches. Search
runs in the browser over the title plus the 300-character excerpt
(`map.js:994`, `EXCERPT_LENGTH` in `models.py`). 65% of summaries are longer than that
(median 375, p90 714 characters). Matches on the full text against what the site finds
now:

| Query | Now | Full summary |
|---|---|---|
| churchill | 7 | 17 (+143%) |
| plague | 6 | 14 |
| napoleon russia | 64 | 94 |
| lincoln | 22 | 31 |
| hannibal | 35 | 44 |

People's names and diseases suffer most. The user is not told that the result is
incomplete. `docs/analysis/` already holds relevance scripts for search, so the thesis
can measure the gain.

**Feasibility 4 (simple route).** The feasibility review rated a full-text index (FTS5 on
SQLite, `tsvector` on Postgres) at 3, effort L. It needs two dialect paths, raw-SQL
migrations, and triggers that `sync-wikidata`'s bulk updates bypass. Build a simpler
version first:

- `GET /api/search?q=` in `views/api.py`. One `ILIKE` / `LIKE` condition per word on
  `title || summary` over approved events. On 19k rows that is a sequential scan of a
  few tens of milliseconds, with no index and no migration.
- It returns ids only, capped at about 2,000, with a short cache header.
- The client keeps its own matching for the title, quoted phrases and "whole words". It
  adds the ids from the server and takes the union, so no behaviour is lost
  (`searchScore` `map.js:1000`, `setQuery` 949). Debounce at 250 ms.
- CI already runs the suite on Postgres 16, so both dialects are tested.
- Move to FTS only if the measured latency calls for it.

**Traps.** Results now arrive asynchronously, so a filter change during a fetch must
cancel the fetch. Highlighting (`highlighted`, `map.js:1847`) only sees the excerpt.
Search on collection maps uses entries, not events, so leave it client-only there.
Rate-limit the endpoint (`@limit`).

**Later.** Wikidata aliases as hidden keywords ("Operation Overlord" → Normandy
landings) need `props=aliases` in the export (`wikidata.py:359`) and a column.

## 2. "What happened here": a place over time · Priority 18.8

**What.** Click a point (or use the current centre) and get *everything* within a radius
as one timeline across all eras, ignoring the year slider. Jerusalem over 3,000 years,
Verdun from the Treaty of 843 to 1916.

**Necessity 3.** No feature today reads the map *through time at one place*. "Near
here" (`map.js:2262`) shows only events that pass the current filters, including the
year slider. The data is fully there.

**Thesis 5.** This is the clearest single demonstration of a map read as history: the
same place in every era.

**Feasibility 5.** It is a variant of `nearbyEvents` (`map.js:2292`) over `state.events`
filtered by `matchesIgnoringYears` (1585), not `state.filtered`, rendered in the Near
card (`renderNear`, 2308). It uses the same bounding-box pre-check. No server, no
migration.

**Traps.**
- A plain map click already closes popups and opens markers. Use an explicit "What
  happened here?" control or a long-press instead.
- `renderNear` re-runs on `moveend` while `nearOrigin` is null, so store the clicked
  point there.
- A MutationObserver closes the Near card when the sidebar opens (2402).
- A 50 km radius around Rome or Paris gives hundreds of events. Add a radius control
  (10 / 50 / 100 km) and group the list by century.
- Near here is off on collection maps (`setupNear`, 2386); keep it off there.

**Tests.** Browser only.

## 3. Where each date and place came from + a `/quality` page · Priority 17.5

**What.** Store `date_source` and `coord_source` per event. Show them in the details
panel and on the event page, for example: "Year: Wikidata point in time · Place: from
the location *Waterloo*". Add a public `/quality` page with the numbers: share by
source, events with no country, tag coverage, open and applied reports, recent
corrections.

**Necessity 3.** The CSV already records both sources, but the database drops them:

- Dates: 13,757 from P585, 4,321 from P580, 1,040 from Wikipedia text, 52 from
  inception.
- Places: 13,630 from the item's own coordinates. **5,538 (29%)** are borrowed from a
  location (`P276`), so the pin is the town, not the battlefield.

Nobody can see this today. The site already uses trust marks on collections (★, ✔), and
this extends them to events.

**Thesis 5.** "How reliable is this map?" gets a measured answer on every page.

**Feasibility 5.**
- Two nullable `String(40)` columns: an additive migration in `models.py`.
- Thread them through `_scalar_fields`, `_event_from_row` and sync step 3b in
  `importer.py`.
- No re-export: the CSV already has them.
- Serve them in `/api/events/<id>` (`to_dict`), so there is no feed change.
- `/quality` is a cached aggregate view (the pattern of `welcome`, 300 s).

**Traps.**
- Sync compares a tuple of fields to decide "unchanged" (`importer.py` ~524). Without
  the new fields in that tuple the columns never backfill, so add a one-off
  `backfill-provenance` command.
- `coord_source` is raw (`P276:Q659335`). Turn it into readable labels.
- Events submitted on the website have neither field; show "submitted, checked by an
  editor".

**Tests.** pytest only.

**Feeds into** #12 (centroid-placed events must be labelled) and #27.

## 4. Story mode for collections and tags · Priority 17.0

**What.** A "▶ Play" button on a collection, later on a tag:

- the map flies to each entry in order and shows the entry's note as a caption;
- it draws the path so far;
- Previous/Next, arrow keys and autoplay;
- `?play=1&step=n` links, and the same in an embeddable frame.

**Necessity 4.** Collections are the strongest feature for teachers, and the curated
collections just added are stories ("Hannibal's war", a family's war). Drag-to-reorder
already exists (`manage-entries.js:216`, `POST /entries/order`), but nothing plays the
order: `collection-map.js` only fits the bounds and flies to an entry on click.

**Impact 5.** A teacher can present a collection in class, or send students a link to
step through it on their phones.

**Feasibility 4.**
- A new `story.js` used by `collection-map.js`. Entries already arrive ordered by
  `position`, with `note` in `to_map_dict`.
- The path is an `L.polyline`. `flyToVisible` (`map.js:774`) already allows for the
  phone sheet.
- Embedding needs a `/collections/<view>/embed` route in `views/collections.py`, not
  `collections_service.py`, so it stays out of the risky file. It also needs the endpoint
  added to the frame rule in `__init__.py:135`.

**Traps.**
- On collection maps the ids are entry ids, not event page ids.
- Hidden and unlisted collections must stay 410 / private in the embed, and only the
  view token may appear in a URL.
- A path across the Pacific needs the nearest-copy logic from `game.js:253`.
- A tag has no order except by date, so tag stories use `collections_service.tag_events`.

**Tests.** pytest for the embed route (200, CSP, 410 when hidden). Playback in the
browser.

## 5. Tag landing pages (`/tag/<slug>`) · Priority 16.3

**What.** One server-rendered page per used tag (139 tags), for example "World War I on
the map". It shows the years, a static mini-map of the events, the events in date order
with links to their pages, the tag tree, and "Open on the map" / "Make a collection".
Add the pages to the sitemap.

**Necessity 3.** The only server routes are `/`, `/embed`, `/event/…`, `/about` and
`/submit` (`views/public.py`). People search for "Napoleonic Wars map", and today that
search can only land on a single event page. Teachers also need a stable, readable page
to link to without the filter UI.

**Feasibility 5.** It reuses what exists:

- `seo.tile_map` and the event page's mini-map;
- `collections_service.tag_events` for the ordered list;
- `tag_tree.py` for the parts;
- `seo.py`'s sitemap parts and canonical links.

No migration, no feed change.

**Traps.**
- Hide tags with fewer than about 3 events (`noindex`), so there are no empty pages.
- The mini-map hot-links OSM tiles from the visitor's browser like event pages do. That
  is allowed, but do not render tiles on the server.
- Slugs must stay stable when a tag is renamed in the tag admin: redirect the old slug
  by tag id, as event pages do.

**Tests.** pytest only.

## 6. Importance score from Wikidata sitelinks · Priority 16.0

**What.** Store each event's sitelink count, the number of Wikipedia language editions
with an article about it. Use it to:

- show only the top events at low zoom and the rest as you zoom in;
- rank search results and the list;
- choose the game's daily events;
- choose the candidates for #12 and the ranking for #16.

**Necessity 4.**
- At world zoom, 19k events weigh the same: 930 local building fires count as much as
  Waterloo.
- The game's daily events are picked by hash (`game._rank`).
- The signal exists. The sample median is 6 and p99 48, while Stalingrad has 108,
  Waterloo 95, Hastings 81 and Normandy 74.

**Feasibility 4.**
- `Event.sitelinks` (int, default 0): a migration in a risky area, but additive.
- A CLI `fetch-sitelinks`. SPARQL `wikibase:sitelinks` with VALUES batches of about 400
  is about 50 queries. Add the column to `EVENT_COLUMNS` so sync keeps it.
- Ship it in the chunks as a 0–9 log bucket (about 19 KB). This is a FORMAT bump.
- Hide the major events from the cluster group instead of drawing a second layer on
  top, or they are drawn twice.

**Traps.**
- Practice and pairs games are seeded. Changing the candidate order reshuffles existing
  challenge links. Use the score only for *new* daily games (stored in `DailyGame.refs`,
  so past days do not change), or version the seed.
- Sitelinks favour Europe and recent wars. Use a rank or log scale, not the raw count.

**Tests.** pytest for the CLI (fake client), the feed column and game ranking. Browser
for the zoom layer.

## 7. Region / country filter · Priority 15.0

**What.** Filter by region (Western Europe, East Asia, North Africa…) and, where known,
by modern country. The filter goes in the URL (`?place=…`).

**Necessity 4.** It has been open in `ToDo` since the start: "when I enter Greece all
the things that ever concerned Greece appear". `Event.country` exists but is used only
for display and game hints. It holds **752 different strings** ("Kingdom of Spain",
"Roman Empire") and is empty for **17%** of events.

**Feasibility 4 at region level**, 3 for countries:

- **Region:** `haam/data/regions.py` already has `region_at(lat, lon)`, the nearest
  region centre, used by the game's hints. Compute it offline for every event, which is
  enough for a region filter. Ship it as a small index in the chunks (like `cat`).
- **Country:** Wikidata P17 is a single item for 80% (55–75% for naval, natural and
  diplomatic events). Map those to ISO codes with a reviewed table. Leave the rest
  without a country, never guessed.
- Add a column (`place` / `country_code`): a migration in a risky area. Add it to
  `URL_KEYS` (`map.js:1049`) and to `matchesBase` (1376).

**Traps.**
- Keep `Event.country` untouched: the game reads it (`game.py:607`, `names_a_country`
  247).
- Region centres misplace events near borders. Treat the region as a filter, not as
  stated fact on the event page.
- Naval events often have no country. They need an "at sea" bucket.

**Draw a box** on the map can come later. It overlaps #2.

## 8. Related events in the map's details panel · Priority 15.0

**What.** Under the description in the panel, show three small lists: the previous and
next event in the same tag, events nearby, and events in the same year elsewhere.

**Necessity 3.** They exist on the event page only (`views/public.py` `_related`). A
visitor exploring the *map* opens an event, flies to a lone dot and has nothing to click
next.

**Feasibility 5.** Do it client-side in `showEvent` (`map.js:418`). `state.events` is
already sorted by `compareEvents`, and "nearby" reuses `nearbyEvents`. No server call.

**Traps.**
- 64% of events have no tag, so the tag row is often empty; fall back to nearby.
- Keep the same "most specific tag" rule as `_related`, which has a known bug: an
  ongoing tag counts as a million-year span.
- Turn it off on collection maps, which have no event list.
- The panel can open before all chunks have loaded.

## 9. Category donuts on clusters + a category legend · Priority 15.0

**What.** A mixed cluster shows a ring split by category share around its count. A
legend explains the colours and that size means number of events.

**Necessity 3.**
- Mixed clusters are a flat grey (`.cluster-cat`, `main.css:560`).
- There is a legend only for colour by year (`map.js:303`). With 67% military the map
  looks uniform, and the eye cannot find the diplomatic or natural events.
- Open since TOP-20 #12 (half built).

**Feasibility 5.** `clusterSummary` (`map.js:155`) already loops over every child
marker. Add per-category counts, then draw an inline SVG ring with `stroke-dasharray` in
`iconCreateFunction` (200). The existing cache key stays valid. The legend is an
`L.control` like the year legend and reuses `--cat-*`.

**Traps.**
- Colour by year replaces the donut, so the legend must switch with it.
- Seven categories are hard to tell apart for colour-blind users. Put the counts in the
  cluster's `aria-label`, which also helps #10.
- Draw the ring only above a cluster size, for speed.

## 10. Keyboard and screen-reader route through the map · Priority 12.0

**What.**
- A skip link.
- Markers out of the tab order, with the list and search as the keyboard route.
- Clusters labelled "Cluster of 105 events".
- Focus moves into the details panel when an event opens.

**Necessity 3.**
- There is no skip link (`base.html`).
- Leaflet markers are focusable by default and cluster icons have no label, so a
  keyboard user tabs through hundreds of unlabelled stops.
- The panel opens without moving focus.
- Live counts (`aria-live`) are already done.
- University and public-sector work increasingly has to meet WCAG.

**Feasibility 4.** Set `keyboard: false` on markers and `role="img"` / `aria-label` in
`iconCreateFunction`. Leaflet re-creates icons on every `moveend`, so the attributes
must go in the options, not be patched afterwards. Then add a focus move in
`showEvent`.

**Out of scope here.** The game map is click-only (`game.js:262`). A keyboard way to
guess, by typing a place or with arrow keys, is a separate task.

**Tests.** Playwright + axe. A pytest test can check that the skip link is present.

## 11. Tag hierarchy, era browser, related tags · Priority 12.0

**What.** As designed in `docs/tag-ux-design.md`:

- a parent per tag;
- a "Browse tags" dialog by era;
- up to 6 related-tag chips under search;
- a "Napoleonic Era › Napoleonic Wars › Peninsular War" context line.

**Necessity 3.** 139 tags are in use, in one flat list. The tag tree (built) shows the
*parts* of one tag, not where it sits among the others.

**Feasibility 4.** The design is finished. Generate `haam/data/tag_hierarchy.py` from
`part_of.json` and the P361 chains, review it by hand, and add `parent_id` to `/api/tags`.
No migration.

**Traps.**
- `feed._tag_fingerprint` hashes only id, name and years. Add the parent, or the cached
  `tags.json` stays stale for a year.
- Closing the hierarchy ("every Peninsular War event is a Napoleonic Wars event") retags
  about 77 events.
- The design's search numbers assume the old 140-character excerpt. Re-check them.

**Effort.** L (the design itself estimates 4–5 days).

## 12. Canon import of missing famous events · Priority 11.3

**What.** A reviewed import of well-known events that the export never took in, through
the pending queue.

**Necessity 4.** Missing:

- Chernobyl disaster
- September 11 attacks
- Sinking of the Titanic
- Black Death
- Boston Tea Party
- 1906 San Francisco earthquake
- Russian Revolution
- Partition of India
- Magna Carta
- Defenestrations of Prague
- Columbus's voyages

The Wikidata check shows why. Most of them were **never queried**: their types
(protest, shipwreck, nuclear disaster, pandemic, partition) are not in
`data/event_types.py`. Others were rejected because their place is a country or region
(Russian Revolution, Columbus) or because they have no coordinates (9/11, Black Death).
Meanwhile 67% of events are military and only 76 are scientific.

**Feasibility 3.**
- Add the missing types to `EVENT_TYPES` (Boston Tea Party and the 1906 earthquake have
  a date and coordinates, so they pass at once).
- Add a hand-made Q-id list (`seed/canon.csv`) that may bypass the region and no-coordinates
  rules, with coordinates typed in and marked as such (#3).
- Add a sitelink threshold (#6).
- Import with `import_full_csv(approve=False)`.

**Traps.**
- **Never** route these through `sync-wikidata`: it deletes every imported event missing
  from its CSV. Either add them to that CSV or keep them as website-style rows.
- An event placed at a centroid looks like a precise dot unless #3 labels it.
- Magna Carta has only an inception date, and the Wright Flyer has neither date nor
  place on Wikidata, so these need manual overrides.
- The review cost is the editor's time. Sort the queue by sitelinks.

**Effort.** L, mostly editorial.

## 13. Game by tag · Priority 11.3

**What.** Practice mode with a tag ("Cold War", "Crusades"), a "too few events" message
for small tags, and a best score per tag kept in the browser.

**Necessity 2.** Practice already filters by era, category and collection. A student
revising one war has no way to pick it. Locally the game is barely used (2 daily rows,
1 score); production numbers are unknown.

**Feasibility 5.**
- Server: add `tag` to `views/game.py:_filters` (175) and to the practice, check and
  hint routes, and to `game._candidates` (188) with a join on `event_tags`, including
  descendant tags.
- Client: a tag combobox (`tag-combobox.js` is reusable) in `game.html`.

**Traps.**
- The practice cache key (`game.py:436`) is `(seed, era, category)`. Add the tag, or
  two tags collide.
- `challengeUrl()` (`game.js:836`) must carry the tag.
- Use a minimum like `MIN_COLLECTION_EVENTS`.

## 14. Link collection entries to main-map events · Priority 11.0

**What.** When an own entry matches a confirmed main-map event (by Wikipedia link, else
by title + year + distance), offer "Link to the confirmed event". The entry gets ✔,
tags, the event page and a place in quiz-from-collection.

**Necessity 3.** **285 of 306 collection entries (93%) are own entries**, including
most of the curated collections just added. Quiz-from-collection uses only main-map
events (at least 5), so most collections cannot be played as a quiz.

**Feasibility 4.** `_verify_link` already stores the redirect-resolved URL, so exact URL
matches against `Event.wiki_url` cover most of them.

**Trap: policy.** A script must not change anonymous people's collections without their
edit link. Do it in two ways:

- fix the **seed** data (`seed/collection_entries.csv`, `seed_demo.py`) directly;
- for live collections, offer the link on the manage page only.

**Other traps.**
- `add_event` raises `DuplicateEntry`, so check first.
- `Event` deletion cascades to entries, so linking widens what a delete removes (see
  #25).
- `year_span`, `all_confirmed` and the quiz change meaning as entries become events.

The code sits in `collections_service.py`, a risky area.

## 15. Time-lapse with trails and presets · Priority 11.0

**What.** During the time-lapse, past windows fade out instead of disappearing. Presets
start a lapse for a tag or collection ("Crusades 1095–1291") from a link.

**Necessity 2.** The time-lapse exists (`map.js:2404`). Without trails you only ever see
one 10-year slice, so movement (a campaign's spread) is hard to read.

**Thesis 4.** It shows movement through time.

**Feasibility 4.** Drawing trails as cluster markers is too slow, because markercluster
rebuilds on every step. Draw them as a separate light `L.canvas` circle layer instead.
Presets are a `?lapse=tag:12` parameter, and the tag's years already feed
`timelineRange` (1385).

**Trap.** The locked colour scale (`colorLock`) must cover the trail.

**Tests.** Browser only.

## 16. "The world in year X" · Priority 11.0

**What.** Pick a year and get one card with the main events of that year, grouped by
region: "1492: Granada falls (Iberia) · …". Every entry opens on the map.

**Necessity 2.** The year slider shows *where*; nothing summarises *what else* was
happening at the same time. The refused "On this day" feed is about calendar days and a
daily feed. This is one year, on demand, so it is not that.

**Thesis 4.** It shows one moment across all places.

**Feasibility 4.** Client-side over `state.events`. Group by `region_at` (#7) and rank by
importance (#6) or, without it, by summary length. It reuses the Near card's layout. It
is weak without #6, so build it after #6.

## 17. Tag suggestions for untagged events · Priority 10.5

**What.** An editor page listing untagged events with suggested tags (year within the
tag's years, *and* close to events that already have the tag), with checkboxes and
"confirm selected".

**Necessity 4.**
- **12,309 events (64%) have no tag.**
- **199 of 340 tags are empty.**
- Holocaust has 7 events, Space Race 1, and Black Death and the Mongol invasions have no
  tag.

**Feasibility 3.** Writing the code is easy: a pure scoring module plus a Jinja page
like the bulk review. The hard part is precision. A year-only match would tag a 1942
Hawaiian event "World War II" correctly and a 1942 Brazilian flood wrongly. Combine
year, distance to tagged neighbours and P361 chains, and never apply anything
automatically.

**Trap.** Every confirmed batch changes the feed fingerprint and invalidates the cached
chunks, so commit in batches.

**Depends on.** #11 helps.

## 18. Open dataset (CSV / GeoJSON of events) · Priority 10.0

**What.** A documented download of all approved events with summaries, sources and
licence. It is also the citable dataset behind the thesis.

**Necessity 2. Thesis 4.** Reproducibility: the thesis can point to the exact data,
validated by the rules in the README.

**Feasibility 4.** Vercel responses are capped at about 4.5 MB, and the full set is
larger. Generate static files with a CLI (`export-dataset`) at deploy time. Do not build
them on request.

**Licence.**
- Summaries are Wikipedia text under CC BY-SA 4.0: include the attribution, the article
  URL per row and the share-alike notice.
- Wikidata facts are CC0.

**Close to a refused item.** Collections were refused for export, so this must contain
events only: never collections, notes, tokens or suggestions. A test should pin that.

`robots.txt` blocks `/api/`, so publish under `/data/`.

## 19. schema.org `Event` data on event pages · Priority 10.0

**What.** JSON-LD `Event` (name, start date, `Place` + `GeoCoordinates`, description)
next to the existing breadcrumb data (`event.html:10`).

**Necessity 2.** It is cheap, but Google's Event rich results target ticketed events,
so the search gain is uncertain.

**Feasibility 5.**

**Traps.**
- BC years need a sign and 6 digits (`-000049`), or leave out `startDate` when the date
  is not precise.
- Test the output in `test_seo.py`.

**Not included.** A rendered share image *per event* (feasibility 2). Rendering OSM tiles
on the server for 19k pages breaks OSM's tile policy and needs Pillow on Vercel.

## 20. "Open on HAAM" from Wikipedia · Priority 10.0

**What.** `GET /wiki/<title>` opens the event if it exists, else the Add-event page
pre-filled. A bookmarklet makes this one click from any Wikipedia article.

**Necessity 2.** A small convenience for contributors and curious readers.

**Feasibility 5.**
- Normalise the title with `wikipedia.title_from_url` / `canonical_url` and look it up
  with `events.find_existing`.
- `/submit` only accepts a CSRF-protected POST today. Add a GET prefill that never
  submits on its own.

**Traps.**
- A redirected title won't match `wiki_url`. Fall back to the submit page, which
  resolves redirects.
- No Wikipedia call inside the redirect route.
- Rate-limit it.

## 21. Lead images on events · Priority 9.0

**What.** A thumbnail with credit in the details panel and on event pages.

**Necessity 3. Impact 4.** The site has no pictures at all. 53% of events have a
Wikidata image (P18) and 72% of articles return a page image.

**Feasibility 3.**
- A CLI fetch of P18 first, page image second (about 400 requests). Store file name,
  author and licence: a migration.
- Add `https://upload.wikimedia.org` to `img-src` in the content security policy
  (`__init__.py:23`).

**Licensing is the work.**
- English Wikipedia page images can be non-free (fair use). Use Commons files only and
  check the licence metadata.
- Show the author and licence under every image, as CC BY / BY-SA require.
- Hot-linking shows visitors' IP addresses to Wikimedia. Say so on the About page.

Keep the images out of the chunks and load them with `loading="lazy"`.

## 22. Review-queue warnings · Priority 9.0

**What.** On each review card, warn about likely duplicates (same year, under 20 km,
similar title) and dates that appear nowhere in the text.

**Necessity 2 now, 4 with #12.**
- Only 57 events are pending.
- A rough check on approved events finds 560 "same year, under 20 km, similar title"
  pairs. Most of them are real siblings (First and Second Battle of X), so the warning
  must stay a warning.
- It becomes necessary once a canon import fills the queue.

**Feasibility 4.**
- A pure module `review_checks.py`, called once per page from `views/admin.py:56`: one
  query for the page's years, a box check, then `game.haversine_km` and `difflib`.
- The "year not in text" check gives many false alarms, because Wikidata often supplied
  the date that the intro lacks. Word it as "year not in the introduction".

## 23. Start and end dates · Priority 8.5 (see the note under the ranking)

**What.**
- Store the end year where Wikidata has one, and show ranges ("6 April – 29 May 1453").
- Let the year filter include events *going on* in the chosen years.
- Draw bars on the timeline.

**Necessity 4.**
- 2,313 titles (12%) are Sieges, Wars or Campaigns, shown as one point in time.
- 966 date texts contain a range.
- Filtering 1914–1915 misses events that began earlier and were still going on.

**Thesis 5.** Duration is basic data for a timeline product.

**Feasibility 2.**
- Coverage: only 24% of all events have both dates, 39% of military, and **69% of
  Siege/War/Campaign titles**. Ranges can only be shown where they exist.
- `validate` in `wikidata.py` takes the first of P585/P580/P582/P571 and drops the rest,
  so this needs a **full re-export** (about an hour).
- A column and migration (risky areas), and a feed column (FORMAT bump).
- The rest of the code assumes a single point in time:
  - `date_label` is parsed into month and day;
  - the game scores years against the start;
  - `Tag.covers`, `year_span`, `_related` ordering and the month/day sort key.

**Reduced scope that is worth doing.**
1. Store `end_year` and show the range on event pages and in the panel.
2. Add an "include ongoing events" switch to the year filter.
3. Leave the game and the timeline bars for later.

Decide the semantics first. A missing P582 means *unknown*, not "still going".

**Depends on.** Do it in the same migration as #6 and #3.

## 24. Wikidata fact box · Priority 6.8

**What.** On event pages and in the panel, a small box of facts that depends on the
category: participants for battles (38% of military events, 78% of naval), deaths for
disasters (78%).

**Necessity 2.**
- Winner (P1346) is 0% in the sample, so "who won" cannot be shown.
- Commanders have no single property.
- Death counts carry several conflicting estimates; show "estimates vary" with a range.

**Feasibility 3.** A CLI fetch plus label lookup (50 ids per call), a JSON column (a
migration), served in `/api/events/<id>`.

**Close to a refused item (people filter).** Keep it display-only:

- no facets;
- no chunk field;
- no search by participant;
- no participant link that filters the map;
- no person pages.

## 25. Editor audit log with undo · Priority 6.0

**What.** A log of approve / reject / edit / delete / tag actions with the previous
values, and undo of the last action.

**Necessity 2.** There is one editor account (`auth.py`), so "who" is always "admin".
The risk this addresses is a mistaken bulk action. That is real but rare, and a database
backup covers it.

**Feasibility 3.**
- A table plus a migration.
- Hooks in `events.py`: `set_status` 276, `bulk_set_status` 282, `update_event` 260,
  `delete_event` 299, reports 342/366, tags 416–450.

**Limit.** Undo of a **delete** is only partial, because deleting an event cascades into
every collection that holds it, and those entries cannot be restored. A better first
step is a soft delete (status `deleted`), and that alone removes most of the need for
this feature.

## 26. Compare two views on one map · Priority 5.5

**What.** Two filter sets, tags or collections in two colours on one map with one
shared slider. Example: Rome against Han China.

**Necessity 2. Thesis 4.**

**Feasibility 2.** `map.js` has one global `state`. The filters, URL sync, list,
timeline, clusters and heat layer are all singletons. This needs `map.js` split into a
view object first, and that refactor is the real cost. Comparing two *collections* is
easier, because their data loads separately. Only revisit after #4 and #15, which touch
the same state.

## 27. Date-precision display · Priority 5.3

**What.** Approximate dates shown as such: "c. 450", a hatched marker, a switch to hide
them.

**Necessity 1.** **The database holds no approximate dates.** The export already drops
anything less precise than a year (126 rejected), and every stored date is year-, month-
or day-precise (77% day). Dates are already shown at their own precision through
`date_label`.

**Feasibility 3.** The display is cheap. Admitting decade- and century-precise events is
the real work: lower `MIN_PRECISION` in `wikidata.py:50`, add a precision column, and
change the game's scoring.

**Revisit** only if #12 admits imprecise events. Do it together with #23.

## 28. Collection history and undo · Priority 5.3

**What.** The last ~20 versions of a collection's entries, and "undo" for its owner.

**Necessity 2.** Collections hold at most 18 entries so far, and removal already asks
for confirmation.

**Feasibility 3.**
- Mutations go through 11 functions in `collections_service.py`, a risky area. One
  wrapper around `_touch` could snapshot after each change.
- Restoring re-creates entries with new ids, which breaks references from suggestions
  and the manage page.

**Close to refused items.** Never add "download a version" or "paste to restore". Those
are the refused export and bulk import.

## 29. Classroom board without accounts · Priority 5.0

**What.** A teacher creates a class link for a collection quiz. Students join with a
nickname, and the teacher sees anonymous results.

**Necessity 2. Impact 3.**

**Feasibility 2.**
- Technically it fits the capability-link model: tables, a migration, signed round
  tokens as proof (`game.round_token`).
- Practice checks are stateless and exempt from CSRF, so a student can look up answers.
  That is fine for a class, but not for a competition.
- **The blocker is minors' data.**
  - Free-text nicknames can identify or insult. Use generated names instead.
  - Results must be deleted after about 30 days.
  - The school is the data controller under GDPR Art. 8.
  - It needs wording on the About page, and a moderation burden follows.

Better to wait until #4 and #13 show that teachers use the site.

## 30. Cause and effect links from Wikidata · Priority 1.8

**What.** "Caused by / led to / followed by" links in the panel, drawn as lines.

**Necessity 1. Feasibility 1.** The data is not there:

- has cause (P828): 2%;
- has effect (P1542): 0%;
- follows / followed by (P155/P156): 5% overall, and those are mostly series (seasons,
  test series), not causes.

A causal-chain feature would be empty for 97% of events. The useful relation, *part of*
(81% of military), is already used by tags and the tag tree. **Drop it.**

---

## Dropped because they are already built

- **"Copy link to this view"** exists: `map.html:110` and `setupCopyView` in
  `map.js:2118`. Small polish only: the button is hidden when the filter panel is
  closed, the `window.prompt` fallback is rough, and there is no test.
- **A learning card after each game guess** is mostly built. `drawResult`
  (`game.js:253`) draws the guess, the answer and the line, and the result shows
  distance, country, date, a Wikipedia link and "Show on the map". Still missing: the
  year in easy mode, and a link to the event page.

Two other candidates replaced them: tag landing pages (#5) and "the world in year X"
(#16).

## Suggested build order

1. **A few Playwright smoke tests** for the map, a collection map and one game round,
   before any of the `map.js` features.
2. **Quick wins with no migration:** #2 What happened here, #8 related in panel,
   #9 cluster donuts, #5 tag landing pages, #13 game by tag.
3. **#1 Search** (the simple route) and **#4 Story mode.**
4. **One migration for the data columns:** #3 date and place sources, #6 sitelinks,
   #23 end year (reduced scope), plus the region column for #7. Then #3's `/quality`
   page, the zoom layer from #6, and the #7 filter.
5. **Data work:** #12 canon import with #22 review warnings, #17 tag suggestions,
   #14 entry linking (seed first).
6. **Later, if wanted:** #11, #15, #16, #10, #18–#21. Not now: #24–#30.
