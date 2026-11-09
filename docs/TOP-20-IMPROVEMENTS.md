# History As A Map: the 20 best improvements

*Review of `refactor/clean-rewrite` at `a5dd243` (8 Nov 2026). Tested by hand against a
copy of `instance/haam.db` (19,125 approved events, 57 pending) and the live site
https://history-as-a-map.vercel.app. Nothing here is implemented yet.*

## TL;DR

The core is solid. The map, filters, timeline, collections, the Game and the review
queue all work, the code is clean, and the security basics (CSP, CSRF, hashed edit
tokens, no `innerHTML`) are in place. What holds the site back now is **finding things
and coming back**, not bugs:

1. **Search misses most matches.** "napoleon russia" finds 11 events, but 94 summaries
   contain both words (Borodino is missing). "churchill" finds 0 events, against 17
   summaries that mention him.
2. **Exploring and saving are separate.** You cannot add an event to a collection from the map.
3. **Nothing can be shared or found from outside.** There are no event pages, no
   Open Graph previews and no sitemap, so Google sees one page.
4. **The data has holes and mislabels.** 12 of 40 famous events are missing (9/11, the
   Titanic, the Black Death…). "Natural" is 58% fires such as building fires and
   wildfires, and "Other" is mostly massacres.
5. **The phone experience and first load are heavy.** 7.5 MB of JSON (1.6 MB gzipped),
   a 5.2 s cold start on Vercel, filters below the map, and the details sheet hides the
   event you opened.

Do items 1–4 first: each is small and they change the most. Items 5–9 are the next
week. Items 13–18 turn the site into one people come back to (stories, related events,
"on this day").

**Legend:** 🐞 = bug reproduced by hand (steps given) · 📏 = measured · 📖 = found in the code.
Effort: **S** ≤ ½ day, **M** ≤ 2 days, **L** > 2 days.

| # | Improvement | Type | Effort | Risk |
|---|---|---|---|---|
| 1 | Search the full description, not a 140-char excerpt | 🐞📏 fix | S | Low |
| 2 | "Add to collection" button in the event details | 📖 feature | S–M | Low |
| 3 | Real event pages + share previews + sitemap | 📏 feature/SEO | M | Low |
| 4 | Fast first load: smaller payload, CDN caching, static files off the function | 📏 perf | M | Medium |
| 5 | Phone layout: map-first bottom sheet, filters in a drawer | 🐞 UX | M | Medium |
| 6 | Fix the categories (fires ≠ natural, massacres ≠ other) | 📏 data | M | Medium |
| 7 | Importance score + fill the famous gaps | 📏 data/feature | M–L | Medium |
| 8 | Rate limits and a moderation gate for public collections | 📖 security | S–M | Low |
| 9 | "Is this an event?" check on Add event | 🐞 fix | S | Low |
| 10 | Shared `?tag=` links should zoom like a picked tag; search should fit results | 🐞 fix | S | Low |
| 11 | Colour-by-year scale that isn't all purple | 🐞 fix | S | Low |
| 12 | Clusters that say what's inside (category donuts + legend) | 🐞 UX | S–M | Low |
| 13 | "Related events" in the details panel | feature | M | Low |
| 14 | Story mode: play a collection or tag in order | feature | L | Medium |
| 15 | Better tag coverage + a place filter | 📏 data/feature | M | Medium |
| 16 | Collection editor that scales past 20 entries | 📖 UX | M | Low |
| 17 | A front door: intro, "on this day", featured collections | feature | M | Low |
| 18 | Start *and* end dates for events | 🐞 data | M | Medium |
| 19 | Accessibility pass (skip link, tab order, live counts) | 📏 a11y | S–M | Low |
| 20 | Browser end-to-end tests for the JS | 📖 quality | M | Low |

---

## 1. Search the full description, not a 140-character excerpt 🐞📏

**What.** Client search only looks at `title` plus `excerpt` (`map.js:478–484`). The
excerpt is cut at 140 characters, but the average summary is 418 characters. Make
search cover the whole summary: either ship a search index or call a server-side
`/api/search` (Postgres `tsvector`, SQLite FTS5 locally). Add Wikidata participants
and commanders as hidden keywords (another session is already discussing this).

**Why (evidence).** I counted matches on the same DB:

| Query | Found now (title + excerpt) | Matches in the full summary |
|---|---|---|
| napoleon russia | 11 | 94 (Borodino missing) |
| hannibal | 17 | 44 (Zama missing) |
| caesar | 36 | 61 |
| genghis | 4 | 15 |
| churchill | **0** | 17 |

Steps: open `/?q=hannibal`. The slider fits to 218–203 BC with 17 events, and the
Battle of Zama (202 BC) is not among them. A student researching a war gets a
silently incomplete answer and has no way to know it. This is the most common task on
the site.

**Effort** S for server-side search (one endpoint plus FTS) or for shipping
summaries in a separate lazy-loaded file. **Risk** low. With a server endpoint the
filters must still combine with the result ids, so keep the client filtering and
intersect with the ids the server returns.

**Done when** the five queries above return the right-hand numbers (or more, with
keywords), and a test pins "hannibal" → contains Battle of Zama.

## 2. "Add to collection" in the event details 📖

**What.** Add a button in the details panel ("Add to collection ▾") listing the
collections this browser can edit (`collections_service.my_collections()` already
exists), plus "New collection with this event". Include the same action in search
results.

**Why.** Today the only way to add a main-map event is the event picker at the bottom
of the collection's manage page (`/collections/<token>/manage`, under 54 entry rows in
my test). The README promises "Add confirmed events from the main map", but the map
has no such control (`grep -i collection map.js` finds only the collection-view code).
A teacher or student browsing the map has to note the title, open the collection,
scroll down and search again. Collections are the strongest feature for teachers, and
this is their main workflow.

**Effort** S–M (a small JSON POST endpoint behind the same `can_edit` check, plus a
menu). **Risk** low.

**Done when** you can open an event on the map, add it to an existing collection in
two clicks without leaving the map, and the details panel shows "In: Hannibal's war –
class 8B".

## 3. Real event pages, share previews and a sitemap 📏

**What.** Server-render `/event/<id>-<slug>` with the title, date, summary, a static
mini-map, a Wikipedia link and "Open on the map". Add Open Graph and Twitter meta
tags (title, description, image) on event, collection and game pages. Add
`/sitemap.xml`, `/robots.txt`, `<link rel="canonical">` and a favicon.

**Why (evidence).**
- `curl /?event=7` returns the same `<title>Map · History As A Map</title>` and generic
  description for every event, with no `og:*` tags. A link pasted into WhatsApp, Slack
  or a school LMS shows no title or picture.
- `/sitemap.xml`, `/robots.txt` and `/favicon.ico` all return **404** (live site too).
- 19,125 events are invisible to search engines, which only see the one map page.
  Event pages are the cheapest way to get visitors who search for "Battle of X map".
- The Game's share text and collection share links would also get previews.

**Effort** M (one template, one route, one sitemap generator; an OG image can start
as a static branded card and later become a rendered map tile). **Risk** low. Keep
collection pages `noindex` as they are now.

**Done when** `/event/7-battle-of-zama` renders without JS, the Facebook/LinkedIn
debugger shows a title and image, and Search Console accepts the sitemap.

## 4. Fast first load: smaller payload, CDN caching, static files off the function 📏

**What.**
1. Make `/api/events` compact: send it as columns (or arrays) instead of 19k objects
   with repeated keys. Drop `display_year` (derivable), send the wiki *title* instead of
   the full URL, and shorten or lazy-load excerpts. Today the payload is 7.5 MB decoded
   and 1.6 MB gzipped. Excerpts take 2.9 MB, `wiki_url` 1.0 MB and keys about 2 MB, so
   about 0.5 MB gzipped is realistic.
2. Cache it properly: a versioned URL (`/api/events?v=<last-change>`) with
   `Cache-Control: public, s-maxage=31536000, immutable` and an ETag. Better still,
   write a static JSON file whenever an event is approved or edited.
3. Exclude `/static/*` from the catch-all rewrite in `vercel.json` so Vercel's CDN
   serves it. Use long cache lifetimes plus `?v=` busting.

**Why (evidence).**
- Live: the first `/api/events` took **5.2 s to first byte** (cold start; the function
  runs in `iad1` while the request entered at `fra1`). Repeats took 0.11 s.
  `max-age=60` with no `s-maxage` means the cold path comes back often.
- Live `/static/js/map.js` comes back `Cache-Control: no-cache`, `X-Vercel-Cache: MISS`.
  Every asset is a Python function call and is revalidated on every visit.
- Locally, each filter click (category) took **260–540 ms** of main-thread work with
  19k markers. On a mid-range phone that is 1–2 s per tap. `applyFilters` also
  rebuilds the list, tag options and timeline on every change (`map.js:747–794`).

**Effort** M. **Risk** medium: the data format change touches `map.js`, the collection
map and the Game. Keep the old format behind a flag until all three use the new one.

**Done when** the gzipped payload is under 600 KB, a repeat visit downloads 0 bytes of
events (304 or cache hit), the cold first byte is under 1 s at the edge, and Lighthouse
mobile performance on `/` is at least 80.

## 5. Phone layout: map first, bottom sheet, filters in a drawer 🐞

**What.** At phone width:
- Put the filters in a slide-up drawer behind a "Filters (2)" button over the map,
  not below the map.
- Make the details panel a sheet with a peek state (title only) that the user drags up.
- When flying to an event, offset the map centre so the marker sits *above* the sheet.

**Why (evidence).** At 375×812:
- 🐞 Open `/?event=7` (Battle of Zama). The details sheet covers about 70% of the screen
  and the map centres on Zama, *under* the sheet. You cannot see the event you opened,
  and the selection ring is hidden.
- The whole filter panel sits below the map. Changing a category means scrolling down,
  tapping, then scrolling back up to see the result.
- The "Timeline (max 1000)" button sits on top of a cluster, and the "All events"
  button disappears.

**Effort** M (CSS plus a little JS). **Risk** medium: the map, collection map and Game
share the layout, so check all three.

**Done when** on a 375 px screen you can filter, open an event and see its marker
without scrolling the page, and the sheet can be dismissed by swiping down.

## 6. Fix the categories 📏

**What.** Recategorise from Wikidata `P31` (instance of) instead of keywords. Split the
current buckets into categories people expect:
- **Disaster (human-made)**: fires, explosions, industrial accidents.
- **Natural disaster**: earthquakes, eruptions, storms, floods.
- **Massacre / atrocity**, or **Violence**.
- **Political**: coups, revolts, uprisings, assassinations.
- **Science & exploration**.

Show category counts on the buttons.

**Why (evidence)** (approved events):
- "Natural": 1,604 events, of which **930 have "fire" in the title** (e.g. "2024 Nanjing
  building fire", "Burning of the Parliament Buildings in Montreal"), against 448
  earthquakes and 49 eruptions.
- "Other": 2,286 events, of which **1,177 are massacres**. The rest are coups,
  uprisings, funerals ("Death and funeral of Alexei Navalny").
- "Scientific": 76 events, almost all nuclear tests (Trinity, Ivy Mike…). Nothing about
  discoveries or exploration.
- "Military": 12,833 events, 67% of everything, so the category filter barely narrows.

A filter that hides 930 fires behind "Natural" makes the category buttons look broken.

**Effort** M (mapping table from P31 classes, a migration, a CLI re-run). **Risk**
medium: collections and the Game read `category`. Keep old values valid until migrated.

**Done when** no event whose P31 is a fire or explosion is "natural", "Other" is under
10% of events, and every category has at least 300 events or is merged.

## 7. Importance score and filling the famous gaps 📏

**What.** Store a popularity signal per event: Wikidata sitelink count (cheap, one
query) and optionally yearly Wikipedia pageviews. Use it to:
- import the missing "canon": the top few thousand events by sitelinks that have a
  date and coordinates;
- show important events first at low zoom (a top-N layer, the rest when zoomed in);
- rank search results and the event list;
- pick the Game's daily events (today: "Siege of Amiens (1597)" as event 1 of 5);
- build "featured" content (item 17).

**Why (evidence).** I checked 40 well-known events. **12 are missing**: September 11
attacks, Sinking of the Titanic, Black Death, Boston Tea Party, Spanish Armada,
1906 San Francisco earthquake, Columbus's voyages, Coronation of Charlemagne,
Magna Carta, Moon landing (Apollo 11 is there), Wright brothers' flight,
Russian Revolution (only the October Revolution). Meanwhile the DB holds 930 local
fires. The heatmap shows a strong Europe/US bias, and with no ranking every one of the
19k dots weighs the same.

**Effort** M for the score and ranking, L for a reviewed canon import. **Risk**
medium: a bulk import needs the P31 filter and a review sample.

**Done when** at least 38 of the 40 test events exist, the Game's daily events have a
minimum sitelink count, and at zoom 2–3 the map shows the top ~500 events by default.

## 8. Rate limits and a moderation gate for public collections 📖

**What.** Add Flask-Limiter (or a simple DB-backed counter, since serverless has no
shared memory):
- `/submit` preview: about 10 per minute per IP (each preview makes outbound
  Wikipedia/Wikidata calls).
- Admin login: 5 per minute per IP, then a delay.
- Collection create, report and add-entry: modest per-IP limits.

New *public* collections should appear on the public list only after an editor
approves them, or after N hours without reports. Add a honeypot field to the public
forms.

**Why (evidence).**
- Login: 30 wrong passwords in a row → 30× HTTP 200, no lockout (only scrypt's
  ~0.1 s per try slows it down).
- `grep -ri limit haam/` finds no rate limiting anywhere.
- Public collections are "listed on the Collections page right away" (README). The demo
  data already contains a spam collection, "Best deals!!! – Click the links for
  amazing offers", that stayed visible until two reports came in.

**Effort** S–M. **Risk** low. On Vercel, store the counters in Postgres or Upstash,
not in process memory.

**Done when** the 11th preview in a minute gets a 429 with a friendly page, a new
public collection shows "awaiting review" to its owner, and tests cover both.

## 9. "Is this an event?" check on Add event 🐞

**What.** In `events.preview`, fetch the Wikidata `P31` that the importer already uses
and warn, or block, when the article is a city, person, building or other non-event.
When the year was parsed from text rather than Wikidata, mark the year field
"guessed – please check".

**Why (evidence).** 🐞 Go to **Add event**, paste `https://en.wikipedia.org/wiki/Paris`
and click Preview. The preview accepts it with **year 2026, date "January 2026"**
(taken from the population census sentence) and category Other. Suggested tags are
"Syrian Civil War", "War on Terror" and "Russo-Ukrainian War", because suggestions are
based on the year alone. The review queue also shows a mis-dated import: "Shirley
Towers fire" is dated **1967** while its text says 6 April 2010.

**Effort** S (the Wikidata client and the P31 classes exist in `wikidata.py`).
**Risk** low.

**Done when** Paris shows "This article doesn't look like an event (it is a *city*)",
Teutoburg Forest still previews as AD 9, and the review card flags a year that differs
from every year in the text.

## 10. Shared tag links should zoom; search should fit its results 🐞

**What.** Call `zoomToTags()` at the end of `applyUrlFilters` on first load. When a
search narrows the map to under ~200 events, fit the map to them, as tags already do.

**Why (evidence).** 🐞 Picking "Syrian Civil War" in the tag box flies to Syria
(commit `a5dd243`). Opening the shared link `/?tag=338` stays at the world view
(tiles at zoom 3), because `applyUrlFilters` (`map.js:567`) never calls `zoomToTags`
(`map.js:609`). The person who *receives* a link gets the worse view. The same happens
with `/?q=hannibal`: a single cluster of 16 in Italy on a world map.

**Effort** S. **Risk** low.

**Done when** `/?tag=338` opens zoomed to Syria and `/?q=hannibal` opens on Italy and
Tunisia.

## 11. A colour-by-year scale that isn't all purple 🐞

**What.** Map years to colours with the same piecewise scale as the slider
(`sliderRange`: 35% → 0 AD, 65% → 1500, 85% → 1900) or by quantiles, and label the
legend with those stops.

**Why (evidence).** 🐞 Turn on **Colour by year** with no filter. Almost every marker
and cluster is the same violet, because the hue is linear over 4,518 years
(2492 BC → 2026) while 83% of events are after 1500. The colour then tells you nothing
until you narrow the years by hand.

**Effort** S. **Risk** low (the Game and timeline reuse `yearColor`; check them).

**Done when** the default view shows at least four clearly different hues across
Europe, and the legend ticks match the slider's breakpoints.

## 12. Clusters that say what's inside 🐞

**What.** Draw mixed clusters as a donut (category shares around the count) and add a
one-line legend ("● Military ● Diplomatic … size = number of events"). Keep
single-category clusters in their category colour.

**Why (evidence).** 🐞 With the "Second Punic War" tag (54 events, nearly all
military), two of the three clusters are **blue**. Mixed clusters take a default
colour (`map.js:134–144`) that is close to Naval's dark blue, and large clusters are
teal, which looks like a category too. No legend explains it. The ToDo also says
"multiple map icons will look terrible". (The cluster-colours session may already
touch this; check before starting.)

**Effort** S–M (an SVG donut in `iconCreateFunction`, computed from child markers;
cache per cluster). **Risk** low, but measure the cost with 19k markers.

**Done when** a mixed cluster shows its category shares, a legend is visible, and
nobody reads a mixed cluster as "naval".

## 13. "Related events" in the details panel

**What.** Under the description, add three short lists, all computed client-side from
data already loaded:
- **Same war/tag**: previous and next event in time.
- **Nearby**: within 50 km, any time.
- **Same year elsewhere**.

Each entry opens with one click.

**Why.** Opening an event flies to zoom 6+ and shows a single dot. Opening "Lesoreid
uprising" left me looking at an empty corner of the Komi Republic, with nothing that
says what to look at next. "What happened next / nearby / at the same time" is the
whole promise of a history *map*, and it keeps visitors clicking. For a student, "next
battle of the Second Punic War" is the natural reading order.

**Effort** M. **Risk** low.

**Done when** every event with a tag shows previous/next links, and opening Cannae
offers Trasimene (before) and the next battle after it.

## 14. Story mode: play a collection or tag in order

**What.** A "▶ Play" button on collections and on tag selections that steps through the
events in order: fly to each one, show its note and card, draw the path so far, and
offer Next/Previous or autoplay. Collections need a **reorder** control for this (the
`position` column exists, but the UI always sorts by insertion).

**Why.** This is the feature that makes teachers use the site in class and makes
people share it. "Hannibal's route from Saguntum to Zama" or "my grandfather's war,
1943–45" (a demo collection) are stories, and today they are dots on a map. I created
"Hannibal's war – class 8B" from the tag in one step (54 entries), but there is no way
to present it.

**Effort** L (player UI, path layer, reorder UI, a shareable `?play=1` URL).
**Risk** medium (map state management). Build it on the collection map first.

**Done when** a collection can be presented full screen with arrow keys, the order can
be changed by dragging, and a share link opens straight into the story.

## 15. Better tag coverage and a place filter 📏

**What.**
1. Fill the empty tags: for events with no `P361` chain, suggest tags from their year
   and place (e.g. a 1916 battle in France gets "World War I" for an editor to
   confirm). Add an editor screen for bulk tag review.
2. Add a **place filter** (modern country / region). `country` is already filled for
   83% of events, but it holds 752 different values (modern and historical names).
   Normalise it offline from lat/lon to an ISO country plus a continent/region.

**Why (evidence).**
- **12,309 of 19,125 approved events (64%) have no tag.**
- **199 of 340 tags have no events at all.** Big topics are nearly empty: Holocaust 7,
  Battle of Stalingrad 3, Rwandan Genocide 3, Six-Day War 2, Iranian Revolution 2,
  Space Race 1.
- The ToDo asks for "when I enter Greece, everything that ever concerned Greece". Tags
  can't do that, but a place filter can.

**Effort** M. **Risk** medium: wrong automatic tags are worse than none, so keep a
review step (the existing hand-checked NO_CLIMB list shows how).

**Done when** untagged events are under 35%, there are no empty tags in the pickers
(hide them), and `?place=GR` shows events in Greece.

## 16. A collection editor that scales past 20 entries 📖

**What.**
- Put Settings and "Add event" at the *top* of the manage page.
- Remove entries with a fetch call (no page reload) and keep the scroll position.
- Add multi-select remove, drag to reorder (needed for item 14) and a filter box over
  the entries.
- Replace the 141-option tag `<select>` with the same tag search the map uses.

**Why (evidence).** Creating a collection from "Second Punic War" gives 54 entries,
each with its own forms. Settings, "Add an event" and "Add all events of a tag" come
*after* all 54. Every remove is a full POST + redirect to `#entries` (the top of the
list, `views/collections.py:320`), so removing ten entries means ten reloads and
scrolling back down each time. The tag dropdown on "New collection" has 141 options,
with labels like "Space Race (1955 – 1975) – 1 events".

**Effort** M. **Risk** low.

**Done when** removing an entry doesn't reload or move the page, and a teacher can trim
a 54-entry collection to 15 in under a minute.

## 17. A front door: intro, "on this day", featured collections

**What.** On first visit (stored in `localStorage`), show a dismissible strip over the
map:
- one line on what the site is;
- "On this day: 8 November 1592 – Siege of Jinju …" (events whose full date matches
  today);
- "Today's Game";
- two featured public collections.

**Why.** A first-time visitor lands on about 250 clusters covering Europe and Africa,
with an empty-looking filter panel and no hint of where to start. "On this day" and the
Game give a reason to return daily. Collections (the best content) are one menu click
away and never shown on the map page.

**Effort** M. **Risk** low.

**Done when** a new visitor sees the strip once, "on this day" has at least one event
for every day (14,415 events, 75%, have a day-precise date), and clicks on featured collections are
counted.

## 18. Start *and* end dates 🐞

**What.** Store `end_year` and an end date from Wikidata `P582` (end time). Show
ranges ("6 April – 29 May 1453"), and let the year filter include events *ongoing* in
the chosen years.

**Why (evidence).** 🐞 "Fall of Constantinople" is dated **6 April 1453**, the start of
the siege; the city fell on 29 May. "Apollo 11" shows just "1969". "Siege of Syracuse
(213–212 BC)" is listed under 214 BC in the collection. Filtering 1914–1915 misses
events that began earlier and were still going on. For a timeline product, duration is
core data, and the Game's hard mode scores years against the start date only.

**Effort** M (migration, importer, display, filter). **Risk** medium: existing year
semantics are used everywhere.

**Done when** multi-day events show a range, and the timeline draws bars for events
longer than a year.

## 19. Accessibility pass 📏

**What.**
- Add a "Skip to map / Skip to event list" link.
- Take individual markers out of the tab order: offer the list and search as the
  keyboard route, keep clusters focusable with labels like "Cluster of 105 events,
  press Enter to zoom".
- Announce the result count with `aria-live`.
- Check contrast in light mode and give the year pills a text colour that passes AA.

**Why (evidence).** Keyboard only: it takes 25 Tab presses to get through the header
and filters. After that come **~250 tab stops** of markers and clusters in DOM order
(not geographic), each announced only by title or by a bare number. Enter on a marker
does open its popup, which is good. There is no skip link
(`grep -i skip templates` finds nothing), and "19125 events" is not announced when
filters change. The Game already uses `aria-live` well, so copy that.

**Effort** S–M. **Risk** low.

**Done when** axe reports no serious issues on `/`, `/collections` and `/game`, and a
keyboard user reaches the event list in at most 3 Tabs.

## 20. Browser end-to-end tests for the JavaScript 📖

**What.** Add Playwright smoke tests in CI on the seeded demo DB:
- load the map → filter by tag → search → open an event → Back/Forward restores the
  filters;
- create a collection from a tag → remove an entry → open its map;
- play one round of the daily Game;
- approve a pending event as admin.

**Why.** The Python side has 159 tests, but the ~2,750 lines of JS (`map.js` 1,356,
`game.js` 622, `timeline.js` 394) have none. Most of the regressions found here
(items 5, 10, 11) are in JS and would be caught by a smoke test with assertions. Items
1, 4 and 12 also change `map.js` heavily, so this protects them.

**Effort** M. **Risk** low.

**Done when** CI runs the four flows on every push in under 3 minutes and fails on a
console error.

---

## Runners-up

- **OSM tile policy.** Production loads tiles straight from `tile.openstreetmap.org`.
  Heavy traffic can get the site blocked under OSM's usage policy. The base-map
  switcher branch `claude/eager-goldberg-ce34a3` (2 commits ahead, 6 behind) adds
  alternatives; merge it and choose a provider with a free tier and an API key.
- **Unmerged selection ring.** `claude/vigilant-bun-1417c7` (3 ahead, 6 behind) pulses
  the cluster that contains the selected event. Merge or close it so it doesn't rot.
- **Edit tokens in the session cookie.** Raw edit tokens sit in the signed (not
  encrypted) cookie. At about 70 collections the cookie passes 4 KB and browsers drop
  it, and the user silently loses edit access to *all* of them. Store hashed ids
  instead, or a server-side "device" row.
- **Edit token in the URL path.** `/collections/<v>/edit/<token>` lands in Vercel
  request logs and browser history. Consider the `#fragment` + POST approach from the
  old IMPROVEMENTS.md.
- **Back button.** Opening events uses `replaceState`, so after browsing five events
  Back leaves the site. Push a history entry per opened event (or at least per first
  open).
- **Review queue tools.** Add bulk approve/reject, keyboard shortcuts (A/R/E/↓), and a
  "date not found in text" warning (a heuristic found 63 approved events whose year is
  far from every year in their text, about 0.35%: low but worth flagging).
- **Near-duplicates.** "Battle of Zama (109 BC)" and "Siege of Zama" are the same
  109 BC event from two articles. Detect same year + under 20 km + similar title for
  review.
- **Timeline is off above 1,000 events.** Instead of "Timeline (max 1000)", show a
  density histogram that can be brushed to set the years.
- **Unlisted ≠ private.** Editors can read unlisted collections ("My grandfather's war…
  shared with the family only"). Say so in the privacy text on the create form.
- **Global Game stats.** Show "your score vs today's average" and a server-side daily
  distribution, so players have a reason to share.
- **Internationalisation.** Wikidata labels and sitelinks make German/Italian titles
  and summaries cheap. Start with UI strings plus titles.
- **Grammar nits.** "1 events" in the tag dropdowns; "AD 476 – AD 476" ranges.

## How this was tested

- Local: `flask run` (`HAAM_ENV=development`) on a copy of `instance/haam.db`, using
  the Browser pane at 1280×800 and 375×812 (mobile emulation), keyboard-only for the
  map, and a test admin password set through the environment.
- Live: `curl` timings and headers against https://history-as-a-map.vercel.app
  (`/`, `/api/events`, `/static/js/map.js`, `/favicon.ico`).
- Data: SQL over the 19,125 approved events (categories, tags, countries, duplicates,
  year/text mismatches, a list of 40 famous events).
- Code: `haam/` (views, services, models, tagging, config), `haam/static/js/map.js`,
  `game.js`, `vercel.json`, `api/index.py`, tests. Checked for an open redirect in
  `_safe_next` with a `/\example.com` target: Werkzeug escapes the backslash, so it is
  **not** vulnerable.
