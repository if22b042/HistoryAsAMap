# Search the full summaries without flooding the map

*25 Nov 2026, branch `claude/curated-collections` at `2249408`. Analysis only: nothing is built and no app code was touched.*

This follows up item 1 of `docs/TOP-30-FEATURES.md` ("Search the full summaries"). The
question from the user: if a WWII battle's summary says the general used a tactic similar
to Hannibal's, does it get added to a "hannibal" search? What is the plan against that?
And could the full text be used only for the side search, not for the map?

## 0. Short answer

- **The worry is right, but the example is not the real problem.** In the data, a modern
  event comparing itself to Hannibal does not exist: "hannibal" appears in **0 events from
  the 1900s**. Only 168 of 19,125 summaries (0.9 %) use a comparison phrase at all, and
  most of those are "named after a place". What does add noise is a **same word with another
  meaning** (HMS *Hannibal*, *Churchill* tanks, Operation *Crusader*, Benjamin *Lincoln*,
  the town of Lincoln, *Caesarea*, "*plagued* by") and **places named in passing**
  ("the army retreated to Constantinople").
- **Measured:** the 376 events that only the full summary adds (12 queries) are about
  **73 % relevant** (estimated from 114 hand labels). Today's title + 300 characters are **78 % relevant**. So the full text is not
  much dirtier than what the map already shows, but it is much worse for place names
  (Constantinople: 13 % of the added events are relevant, and the map's precision would
  fall from 75 % to 54 %) and for namesakes.
- **Yes, the user's idea works, and it is the safest design.** Keep the map on title +
  excerpt exactly as now. Show the full-text matches only in the big search list, in a
  separate group "Also mentioned in N events", each with the sentence that mentions the
  word. The counter, the markers, the timeline and `?q=` links then do not change at all.
- **Recommendation: design B with a "show on map" switch** (section 7). Add the automatic
  promotion of strong matches (design C) only later, if wanted: it kept precision at
  today's level and raised recall from 70 % to 78 % in the macro average, but it adds
  rules to maintain.

## 1. How search works today (read in the code)

- `map.js:927` `search` holds the terms and the options: `in` ("all" = title + description,
  "title" = title only), `match` ("all" words / "any"), `whole` (whole words only, **off by
  default**, so matching is a plain substring) and `sort`.
- `searchText` (`map.js:990`) builds the text per event: `excerpt + display_year + date + year`.
  `excerpt` is the first 300 characters cut at a word (`make_excerpt` in `models.py:23`,
  `EXCERPT_LENGTH = 300`), loaded in the "text" chunks (`feed.py` `text_chunk`).
- `searchScore` (`map.js:1000`): a title hit scores 3 (4 if the title starts with it), a
  description hit 1, 0 = no match.
- `matchesBase` (`map.js:1376`) and `matchesIgnoringYears` (`map.js:1585`) use
  `searchScore(event) > 0`. `applyFilters` (`map.js:1404`) puts the result in
  `state.filtered`.
- **Everything reads `state.filtered`:** the markers, the timeline, the counter
  ("37 of 19,125 events", `finishRender` `map.js:1447`), the list below the map and the big
  search window (`sortedResults` `map.js:1870` starts with `state.filtered.slice()`). So
  today the map and the big search list are always the same set. Design B has to split them.
- The full summary is only fetched when one event is opened (`/api/events/<id>`).
- A shared link carries `?q=` (`URL_KEYS`, `map.js:1045`); on load the map applies it and
  flies to the results (`zoomToSearchResults`, `map.js:2590`).

## 2. Measurements

Source: `instance/haam.db`, opened read-only (`?mode=ro`), 19,125 approved events. Matching
is the map's own rule: case-insensitive substring, one word. The excerpt is cut with the
same rule as `make_excerpt`. The scripts are listed in section 9.

### 2.1 Match counts: title, title + 300 characters (today), title + full summary

| Query | Title only | Title + 300 (today) | Title + full | Added by the full text | × today |
|---|---:|---:|---:|---:|---:|
| hannibal | 3 | 35 | 44 | 9 | 1.26 |
| napoleon | 1 | 202 | 305 | 103 | 1.51 |
| churchill | 0 | 7 | 17 | 10 | 2.43 |
| caesar | 13 | 58 | 61 | 3 | 1.05 |
| genghis | 0 | 10 | 15 | 5 | 1.50 |
| lincoln | 7 | 22 | 31 | 9 | 1.41 |
| plague | 2 | 6 | 14 | 8 | 2.33 |
| crusade | 5 | 174 | 192 | 18 | 1.10 |
| revolution | 28 | 627 | 798 | 171 | 1.27 |
| carthage | 8 | 51 | 58 | 7 | 1.14 |
| verdun | 4 | 7 | 10 | 3 | 1.43 |
| constantinople | 36 | 57 | 87 | 30 | 1.53 |
| **12 queries** | 107 | **1,256** | **1,632** | **376** | 1.30 |

These match the figures in `TOP-30-FEATURES.md` (churchill 7 → 17, plague 6 → 14, hannibal
35 → 44). "napoleon" 202 is high because the substring also finds "Napoleonic Wars".

`Battle of Zama` is **already** on the map for "hannibal": "Hannibal" is inside its first
300 characters. So are Cannae and the Trebia. The 9 events that the full text adds for
"hannibal" are the ones in section 4.

### 2.2 Precision per query, from the hand labels (section 3)

*Relevant* = labelled R or W. Precision = relevant / events shown. "Recall of today" =
how many of the relevant events (in the full-text set) the map shows now.

| Query | Today n | Today precision | Added n | Added: relevant / labelled | Union n | Union precision | Recall of today |
|---|---:|---:|---:|---:|---:|---:|---:|
| hannibal | 35 | 85 % | 9 | 4 / 9 (all) | 44 | 77 % | 88 % |
| napoleon | 202 | 100 % | 103 | 13 / 15 | 305 | 95 % | 69 % |
| churchill | 7 | 50 % | 10 | 5 / 10 (all) | 17 | 50 % | 41 % |
| caesar | 58 | 68 % | 3 | 1 / 3 (all) | 61 | 66 % | 98 % |
| genghis | 10 | 67 % | 5 | 4 / 5 (all) | 15 | 71 % | 62 % |
| lincoln | 22 | 5 % | 9 | 2 / 9 (all) | 31 | 10 % | 33 % |
| plague | 6 | 50 % | 8 | 6 / 8 (all) | 14 | 64 % | 33 % |
| crusade | 174 | 99 % | 18 | 10 / 15 | 192 | 96 % | 94 % |
| revolution | 627 | 68 % | 171 | 12 / 15 | 798 | 71 % | 76 % |
| carthage | 51 | 96 % | 7 | 6 / 7 (all) | 58 | 95 % | 89 % |
| verdun | 7 | 86 % | 3 | 3 / 3 (all) | 10 | 90 % | 67 % |
| constantinople | 57 | 75 % | 30 | 2 / 15 | 87 | 54 % | 91 % |
| **Pooled (sums)** | 1,256 | **78 %** | 376 | **73 %** (estimated) | 1,632 | **77 %** | **78 %** |
| **Macro (mean of 12)** | | **71 %** | | | | **70 %** | **70 %** |

Reading it:

- **For most queries the union costs 0 to 8 points of precision.** The map would lose
  precision for "hannibal" (85 → 77 %) and badly for "constantinople" (75 → 54 %).
- **The full text also finds the relevant events that today's search misses.** Today the
  map shows only 41 % of the relevant "churchill" events, 33 % of "plague" and 33 % of
  "lincoln". Yalta, Potsdam and the Quebec conference are in that missing 59 %.
- **Today's search is not clean either.** "lincoln" has 5 % precision now: the 22 hits
  are Lincolnshire, Lincoln Park, Lincoln National Forest, the city of Lincoln and one
  assassination. All the Abraham Lincoln events that matter (Stones River, Hampton Roads)
  are in the tail. This comes from substring matching, not from the full text (9 of the 23
  incidental events in the baseline sample are such accidents: Lincolnshire ×6,
  Caesarea, "plagued" ×2).
- Pooled numbers are dominated by napoleon, revolution and crusade (1,000+ events), so
  the macro line is the fairer one for a user who types a rare name.

## 3. Hand-labelling method

This follows `docs/analysis/hand_labelled_eval.py` (the 140 → 300 analysis): sample events
whose full text contains the word, read each one, give it a label, then count what a search
design would show. Differences: the earlier run asked "does this event involve the
person?" (P/M/X). This run asks the question a map user asks, so the labels are:

| Label | Meaning | Counts as |
|---|---|---|
| **R** | The event is about the term or substantially involves it: a participant, the cause, the setting, an outcome stated in the summary. | relevant |
| **W** | The term appears only inside the name of the war or era the event belongs to ("part of the Napoleonic Wars", "American Revolutionary War"). | relevant |
| **I** | Incidental: a different meaning (HMS Hannibal, Churchill tanks, Operation Crusader, Benjamin Lincoln, Caesarea, "plagued"), a passing mention or comparison, a relative ("aunt of Winston Churchill"), a waypoint or destination, a quote about what someone *would* have done. | incidental |

**What was labelled.** 12 queries: people (hannibal, napoleon, churchill, caesar, genghis,
lincoln), topics (plague, crusade, revolution), places (carthage, verdun, constantinople).

1. **Tail-only events**: the events found in the full summary but not in title + 300
   characters. All of them when there were 15 or fewer (8 of the 12 queries: complete
   counts, no sampling), otherwise 15 at random (`random.seed(7)`) for napoleon (of 103),
   revolution (of 171), crusade (of 18) and constantinople (of 30). **114 events.**
2. **Baseline sample**: 6 random events (`random.seed(11)`) from the group today's search
   finds in the excerpt but not the title, so that the full-text group has something to be
   compared with: 67 events (all of them for plague, 4, and verdun, 3; 6 of 7 for churchill).
3. **Titles**: all 107 title matches were read as titles; 87 are relevant. The 20 others are
   mostly Caesarea (11 of 13 "caesar" titles), places and namesakes (6 of 7 "lincoln"
   titles: the city and county of Lincoln, Operation Lincoln, George Lincoln Rockwell),
   Operation Crusader, Carthage, Missouri and Operation Carthage.

Each event was judged from a window of about 200 characters around the first hit (130
before, 90 after for the tail, a little less for the baseline), with the year, the tags and
the number of hits shown next to it. The labels were written by the assistant that ran the
analysis, in one pass, so they are **one reader's opinion**. The borderline calls are
marked in the appendix; the user should spot-check a few. With 114 labels the added-group
precision of 60 % (pooled, unweighted) has an uncertainty of about ±9 points; the
per-query numbers for the four sampled queries (napoleon, revolution, crusade,
constantinople) are rougher than the others.

**Recall** is measured inside the set of events whose full text contains the word. Events
about Hannibal that never name him are outside this analysis.

## 4. What the incidental events look like

Of the **46 incidental** tail-only events:

| Kind | Count | Examples |
|---|---:|---|
| Same word, other meaning | 21 | *HMS Hannibal* (2 events), Hannibal Gisco, the "Hannibal Feud"; *Churchill* tanks, John Churchill (Marlborough, 2 events); Benjamin Lincoln (3), the town of Lincoln; Operation *Crusader* (4); Caesarea, the title "caesar"; "plagued by civil wars"; "Margaret of Constantinople" |
| Passing mention or background | 25 | Constantinople as a waypoint or destination (12 events); Churchill ordering a fire watch; "following Abraham Lincoln in 1865" (McKinley assassination); "his defeat of Napoleon at Waterloo" (Battle of Assaye); a quote that Napoleon "had he been at Fuentes" |
| **A comparison ("similar to Hannibal")** | **0** | not one in the 114 tail events; the baseline sample has one: Second Battle of Nanawa, "the South American Verdun" |

**The user's scenario was checked directly:**

- "hannibal" occurs in **0 events from 1900 to 1999**; "genghis" in 0; "caesar" in 0
  (the 1793 "Caesar's Camp" is a place); "napoleon" in 1 (Operation Kutuzov, 1943: a
  Soviet operation named after the general who beat Napoleon).
- Only **168 of 19,125 summaries** contain a phrase such as "similar to", "reminiscent of",
  "inspired by", "modelled on", "compared to" or "named after". 56 of those are followed by
  a capitalised name, and almost all of those name a place or a person after whom
  something is named. Wikipedia summaries are the lead paragraph; they say what happened,
  not what it resembled.

So the risk is real but different from the one imagined: it is **namesakes and places
named in passing**.

## 5. Signals that might separate relevant from incidental

Tested on the 114 tail-only events (68 relevant, 46 incidental). "Precision" = relevant
among the events the signal flags. "Recall" = share of the 68 relevant ones it flags.
"Incidental removed" = incidental events that the signal does *not* flag.

| Signal | Flags | Relevant among flagged | Precision | Recall | Incidental removed |
|---|---:|---:|---:|---:|---:|
| The term is inside one of the event's tag names ("Napoleonic Wars", "Crusades") | 18 | 17 | **94 %** | 25 % | 45 / 46 |
| The event shares a tag with ≥ 10 % of the strong matches (title/excerpt hits), and ≥ 3 events ("same story") | 29 | 27 | **93 %** | 40 % | 44 / 46 |
| The term appears 2 or more times | 12 | 10 | 83 % | 15 % | 44 / 46 |
| **Tag name OR shared tag OR 2+ times** (the "strong" rule) | 38 | 34 | **89 %** | **50 %** | 42 / 46 |
| The term sits next to a comparison word ("similar to", "like", "compared", "named after", "inspired by") | 1 | 1 | – | 1 % | 46 / 46 |
| Whole word (not part of a longer word) | 82 | 45 | 55 % | 66 % | 9 / 46 |
| First hit after character 600 | 19 | 13 | 68 % | 19 % | 40 / 46 |
| First hit in the last sentence | 49 | 26 | 53 % | 38 % | 23 / 46 |
| First hit in the 3rd sentence or later | 79 | 47 | 59 % | 69 % | 14 / 46 |
| Event year within the person's lifetime ± 30 years (6 people only: 51 events) | 41 | 29 | 71 % | 100 % | 10 / 22 |

What this says:

1. **Where the term appears does not separate anything.** Position, last sentence and
   "after character 600" have precision around 53 to 68 %, no better than the 60 % base
   rate. The same holds across the line the map uses today: events found in the first 300
   characters are 66 % relevant, events found later 60 %. Raising the excerpt to 600
   characters would gain 83 % of the tail matches (95 of 114) at the same precision: not
   a fix.
2. **Comparison words are useless here.** They fire once in 114 events (and that one is
   "known as the French Revolutionary Wars", a relevant event). The thing they were meant to catch
   is almost absent (section 4).
3. **Whole-word matching hurts the tail** (it drops "Napoleonic" and "Crusader", which are
   relevant). It does help in the excerpt group: there 73 % of whole-word hits are
   relevant against 40 % of the others. It is not a fix for the full text.
4. **Tags are the good signal.** The event's own tags say "this is part of the story":
   "Second Punic War" ties the Hannibal battles together; "Napoleonic Wars" ties the
   Napoleonic events. A tag shared with the strong matches keeps 27 relevant and only 2
   incidental events (Battle of Sulci, Hannibal Gisco; Fuentes de Oñoro, the "if Napoleon
   had been here" quote). Its weakness is recall: events with no tags (Yalta, Potsdam, Verdun,
   most places) are never promoted. **64 % of all events carry no tags**, so this signal can only ever cover a third of the events.
5. **The lifetime test is the cleanest, but needs data.** All 10 incidental events
   outside the lifetime window were caught and no relevant one was lost, yet it needs a
   table of birth and death years per person (Wikidata could give it) and only exists
   for people. A version that takes the window from the strong matches' own years (P10
   to P90 ± 30 years) removed only 7 of 46 incidental events and lost 4 relevant ones; do
   not use it.
6. **Count ≥ 2 is a cheap helper**, not a filter: 83 % precision, 15 % recall.

## 6. Designs compared

"Strong" below is the rule from section 5: term in a tag name, or a tag shared with ≥ 10 %
of the title/excerpt matches, or 2+ hits. The numbers use the labels; pooled and macro
average are over the same 12 queries. "Recall" = relevant events shown on the map / all
relevant events whose full text has the word.

| | A. Union on the map (original) | B. Full text in the list only (the user's idea) | C. Tiered: map + strong tail, switch for the rest | D. Everything matches, rank, map shows top N |
|---|---|---|---|---|
| **Map shows** | title + excerpt + all full-text matches | title + excerpt (unchanged) | title + excerpt + strong tail; "Show all mentions" adds the rest | the best N (e.g. 100) of everything |
| **Events on the map (12 queries)** | 1,632 | 1,256 | 1,445 | ≤ 100 per query |
| **Map precision** (pooled / macro) | 77 % / 70 % | 78 % / 71 % (as today) | 80 % / 71 % | not measured; = A for the 9 queries with ≤ 100 matches |
| **Map recall** (pooled / macro) | 100 % / 100 % | 78 % / 70 % (as today) | 92 % / 78 % | cuts relevant events at random for big queries |
| **List precision / recall** | same as map | main group 78 %; with "Also mentioned" 77 % / 100 % | same as map; weak group listed separately | same as map |
| **Worst case measured** | constantinople 75 → 54 %, hannibal 85 → 77 % | none: the map does not change | constantinople 76 %, hannibal 82 % | any query ≤ 100 matches gets A's noise |
| **Counter** | "17 of 19,125" now includes mentions: a count of "mentions" | unchanged: events on the map | counts events on the map; the switch says "+ N mentions" | "100 of 305": cut-off arbitrary |
| **Shared `?q=` link** | map depends on a server answer: markers jump, the fly-to-results (`map.js:2590`) must wait | identical to today, fully deterministic | needs `mentions=1` in the link; async | ranking must be deterministic and loaded |
| **Cost** | M | M, new group in the list | M + 0.5 to 1 day: strong rule, URL key, async map refilter | M + ranking, N setting, "see more" |
| **Server or client data** | endpoint (ids) | endpoint (ids + snippet) | endpoint, or the tail as client data | either |

**Notes on each design**

- **A** is simple and is what `TOP-30-FEATURES.md` proposed. It adds 376 events, 103 of
  them incidental, and it hides the difference between "about" and "mentions". For place
  queries it is the worst option.
- **B** has no noise risk on the map by construction. Its cost is that a relevant
  full-text match (Yalta for "churchill") is only found if the person opens the big
  search, and then it appears below the main group. The "Also mentioned" row carries the
  sentence with the word, so the user can see at a glance that "Churchill tanks" is not
  about Churchill. That turns noise into information.
- **C** is the only design that raises map recall (70 % to 78 %, macro) without lowering
  precision. 95 % of the events it promotes are relevant (179 of 189, estimated). It misses
  untagged one-off mentions (Yalta, Potsdam), which stay in the list. It needs three small
  rules, all computable in the browser from `event.tags` and the strong matches, plus a
  place on the map for the switch. It is built on 114 labels: expect to re-check it
  after the first real use.
- **D** does not address the worry. For 9 of the 12 queries (all with ≤ 100 matches), every
  full-text match is "in the top N", so nothing is filtered. Where it does cut
  (napoleon, revolution, crusade) it drops relevant events by rank, and a ranking built
  from the same signals that fail in section 5 (position, count) is hard to justify.
- **Better options found:**
  - **B plus a "show on the map too" switch.** This is design C's switch without C's
    automatic rule. The map never changes unless the user asks. Recommended (section 7).
  - **Snippets in the "Also mentioned" rows.** Cheap with an endpoint; impossible without
    the text on the client. This is what makes B good, and it gives the list highlighting
    (`highlighted`, `map.js:1847`) the text it needs.
  - **Disambiguation by tag.** For the ambiguous names (Lincoln, Churchill, Hannibal), the
    existing "related tags" idea in `docs/tag-ux-design.md` (chips such as "Second Punic
    War" under the search) removes the namesake problem better than any text rule.
  - **Not worth doing:** a longer excerpt (600 characters = same precision, +1 MB),
    comparison-word filters, position filters, a "whole words" default.

### Payload and speed

| Option | Size | Notes |
|---|---:|---|
| Endpoint `GET /api/search?q=` returning `{id, snippet, n, in_excerpt}` | measured payload for the added events: revolution (171) 31 KB raw / 9 KB gzipped, napoleon (103) 18 / 4, constantinople (30) 5 / 2; the round trip is an estimate of 100 to 400 ms | one SQLite scan over title + summary took **82 ms** per query on this PC (the same for hannibal, napoleon russia and revolution); runs only when the big search is open |
| Client data: the text after the excerpt, as 4 more chunks (`text_tail`) | **1,052 KB gzipped** (113, 271, 322, 375 KB) | loaded the first time someone searches; today's excerpts are about 1,650 KB gzipped |
| Client data: word index (tail-only words → event ids) | 669 KB gzipped | smaller, but no snippets and no whole-word or phrase checks |

## 7. Recommendation and implementation plan

**Build design B, with a switch "Show mentions on the map" (the manual form of C).** Do
not use the automatic strong rule in the first release. The map is unchanged until the
user presses the switch. If after using it the "Also mentioned" group is clearly clean for
the strong events, add the automatic rule as a second step.

Use an **endpoint**, not client data, for this step. It sends under 10 KB gzipped instead of 1 MB, gives
snippets, and keeps accent and phrase logic on one side. The client-data route (a lazily
loaded tail chunk) becomes interesting only if the 100 to 400 ms round trip is a problem
or an offline map is wanted.

### 7.1 Server

- `haam/search.py` (new, about 80 lines): `search_summaries(terms, match, whole, limit)`.
  A SQL prefilter (`func.lower(Event.title + " " + Event.summary).contains(term,
  autoescape=True)` for each word, joined with AND or OR, approved events only; escaping
  keeps `%` and `_` literal, and it works on SQLite and Postgres), then a Python check
  for "whole words" and quoted phrases, then for each hit:
  - `snippet`: about 70 characters each side of the first hit, cut at a word;
  - `n`: number of hits;
  - `in_excerpt`: the word occurs in the title or in `make_excerpt(summary)` (so the
    server states whether the map already has it, with the same rule as the client).
  Results are ordered by `n` (descending), then year, and capped at 400.
- `haam/views/api.py`: `@bp.get("/search")` with `q` (≤ 200 characters, as `filtersFromUrl`
  caps it), `match=all|any`, `whole=0|1`. Minimum 2 characters, otherwise `[]`. Public
  ids (`events.public_id`), as the feed does. `@limit("event-search", 60, 60)` and
  `Cache-Control: public, max-age=300`. Note that `limit` writes a row in
  `haam_rate_limits` per request, so the client must not call it on every keystroke.
- **Known gap**: SQLite's `lower()` and `LIKE` fold only ASCII, so a query with an accent
  can differ from the browser's `toLowerCase()`. The collection search already folds
  accents (`fold` in `collections_service.py:207`); do **not** import from that risky file.
  Copy a six-line helper into `haam/search.py` if accents matter, or accept the gap in the
  first version (the title and excerpt part of the search is unaffected).

### 7.2 Client (`haam/static/js/map.js`, and the template's search panel)

- `state.mentions = { key, ids: Map(id → {snippet, n}), loading, failed }`.
- `fetchMentions()` runs when the big search window is open, `search.in === "all"`, there
  are terms of at least 2 characters, and the query has settled for **400 ms**. It uses
  an `AbortController` (cancel when the query or an option changes) and drops answers whose
  `key` is no longer the current query. Called from `refilter()` and `openSearchPanel()`.
- `mentionResults()`: the entries with `in_excerpt === false` whose event exists in
  `state.eventsById`, filtered with a new `matchesFiltersExceptText(event)` (year, category,
  tags; `matchesIgnoringYears` at `map.js:1585` is the model).
- `renderSearchResults()` (`map.js:1884`): after the main rows, a heading "Also mentioned in
  N events" and the mention rows. Extract the row builder into
  `resultRow(event, text)`; for a mention row `text` is the snippet, so `highlighted()`
  marks it. Status line: "37 events match · 9 more mention it". Same "Show more" paging
  (`RESULTS_PAGE`).
- The switch in the same panel, "Show mentions on the map" (off by default). When on:
  `matchesBase` also accepts `state.mentions.ids.has(event.id)`; the URL gets
  `mentions=1` (add to `URL_KEYS`, `filtersFromUrl`, `syncUrl`); the counter reads
  "46 of 19,125 events (9 mentions)". While the answer is pending the panel says
  "(mentions still loading)", as it already does for descriptions (`state.textsLoading`).
  Failures leave the map on the title + excerpt result and show "Mentions could not be
  loaded".
- Not touched: `searchScore`, `searchText`, `setQuery`, the chunk loading, the collection
  maps (`loadSingle` already has full text), `feed.py`, `models.py`, migrations.

### 7.3 Tests

`tests/test_search_summaries.py` (pytest, uses `client` and `make_event`; no JS test setup
exists in the repo, so the logic that matters lives in Python where it can be pinned):

1. **Pinned: "hannibal → Battle of Zama is on the map, an incidental mention is not".**
   Create *Battle of Zama* with "Hannibal" in its first sentence; *Second Battle of
   Algeciras* with 300+ characters of filler and then "losing the 74-gun ship HMS
   Hannibal"; *Battle of Longstop Hill* (1943) with "Churchill tanks" after character 300.
   `GET /api/search?q=hannibal` returns both Hannibal events, with `in_excerpt: true` for
   Zama and `in_excerpt: false` plus a snippet containing "HMS Hannibal" for Algeciras.
   `q=churchill` returns Longstop Hill with `in_excerpt: false`. The client puts only
   `in_excerpt: false` results under "Also mentioned", so Zama stays on the map and the
   tanks never reach it.
2. Not approved events are never returned; `%` and `_` in `q` are literal; an AND query
   needs every word, `match=any` needs one; `"quoted phrase"` matches the phrase only;
   `whole=1` drops "Hannibalic" or "Lincolnshire".
3. Cap at 400, ordering by `n`; the `q` length limit; a one-letter `q` gives `[]`.
4. The rate limit returns 429 after the 61st call within a minute (copy the pattern in
   `tests/test_ratelimit.py`); the cache header is present.
5. A guard that **the map's text stays as it is**: `Event.EXCERPT_LENGTH == 300` and
   `feed.text_chunk` unchanged (the existing `test_wikidata.py:386` already checks the
   cut).

**Acceptance in the browser** (preview, not CI): `/?q=churchill` shows 7 events on the map
exactly as now; the big search lists them, then "Also mentioned in 10 events" with the
Yalta and Potsdam rows and the "Churchill tanks" row, each showing its sentence. With the
switch on, the counter is 17 and the link gains `mentions=1`; opening that link on another
device gives the same map. `/?q=constantinople` stays at 57; "Also mentioned in 30 events".

**Optional data pin (not CI):** a script over `seed/wikidata_events.csv` that prints, for the
12 queries above, today's count, the "also mentioned" count and the in-excerpt flag of
the pinned titles (Battle of Zama, Second Battle of Algeciras, Battle of Longstop Hill).
It would catch a change in the data or the excerpt length that moves a pinned event across
the line.

### 7.4 Cost and order

| Step | Effort | Risk |
|---|---|---|
| 1. `haam/search.py`, `/api/search`, tests | S–M (about ½ day) | low; no migration, no risky area |
| 2. List group + snippets in the big search | M (about 1 day) | low; the map is unchanged |
| 3. "Show on the map" switch and `mentions=1` | S–M (about ½ day) | medium: async refilter, URL |
| 4. *(later)* automatic strong rule (design C) | S–M | medium: re-measure with more labels first |

## 8. Limits of this analysis

- One reader labelled the events, from a short window around the first hit, in one pass.
  Borderline calls (marked "b" in the appendix) could flip: Battle of Britain, Operation
  Bellicose, Battle of Mantinea, Battle of Kalavrye and a few others.
- The 12 queries are common names and topics. A rare word with one hit has no
  precision problem to measure.
- Four queries were sampled, not counted completely (napoleon, revolution, crusade,
  constantinople); the pooled numbers lean on napoleon and revolution through their sizes.
  The baseline sample is 6 events per query.
- "Relevant" includes W (an event inside a war whose name contains the word). Counting
  only R, the "napoleon" added group falls from 87 % to 33 % and the revolution one from
  80 % to 47 %. Whether "Napoleonic Wars" events belong in a "napoleon" search is a
  product decision.
- The strong rule was found and tested on the same 114 labels. It is not a held-out
  result.
- Time was measured on one PC with SQLite; production is Postgres with network latency.

## 9. Scripts and data

The measurement scripts were written for this analysis and are **not in the repo**
(nothing but this file was created). They are in the shared notes folder
`side-session-notes/local_4d8602ab-6d25-4908-8c54-93c84d0b2980/search-precision-scripts/`:
`counts.py` (table 2.1), `sample.py` and `base.py` (the samples, with the printed
snippets in `sample.txt` and `base.txt`), `labels.py` (the labels), `signals.py`,
`affin.py`, `era.py` and `design_eval.py` (sections 5 and 6), `cmp_scan.py` (the
comparison-phrase scan) and `items.json` (every labelled event with its signals). They
read `instance/haam.db` in read-only mode and use the standard library only. They can be
moved to `docs/analysis/` if wanted.

## Appendix: labels

R = relevant, W = relevant through a war or era name, I = incidental, **b** = borderline.
Tail-only events (found only in the full summary), in the order printed by `sample.py`.

**hannibal** (9, all) — I Battle of Sulci (Hannibal *Gisco*) · I Second Battle of Algeciras (HMS *Hannibal*) · R Battle of Cissa (Hannibal had just subdued the Ebro) · R Battle of Geronium (Hannibal Barca won) · R Battle of Ibera (blocked reinforcements for Hannibal) · I **b** Battle of Mantinea 207 BC (alliance "after Hannibal's victory at Cannae") · R Battle of Canusium (narrow Hannibal's base) · I Battle of Bysjön (the "Hannibal Feud", a Scandinavian nickname) · I Algeciras campaign (HMS *Hannibal*)

**napoleon** (15 of 103) — R Battle of the Nile · W Battle of Baza · R Battle of Arcole · I Battle of Fuentes de Oñoro ("if Napoleon had been at Fuentes") · W Battle of Altafulla · W Battle of Blaauwberg · W Battle of Guttstadt–Deppen · R Battle of Tarvis · I Battle of Assaye ("his defeat of Napoleon at Waterloo") · W Capitulation of Erfurt · R **b** Battle of Neuburg (Napoleon's victories as context) · W Siege of Tarragona · W Second siege of Badajoz · R Dalmatian campaign of 1809 · W Treaty of Schönbrunn

**churchill** (10, all) — R **b** Battle of Britain (named after his speech) · R Yalta Conference · R Potsdam Conference · I Battle of Camaret (John Churchill) · I Battle of Longstop Hill (Churchill *tanks*) · I Siege of Douai (John Churchill, Marlborough) · I Siege of Mafeking (aunt of Winston Churchill) · I Second Great Fire of London (fire watch "at the behest of" him) · R **b** Operation Bellicose (he viewed the photos that triggered it) · R Second Quebec Conference

**caesar** (3, all) — R Battle of Magetobriga (Caesar used it as a pretext for Gaul) · I Siege of Byzantium 324 (the title "caesar") · I 115 Antioch earthquake (Caesarea Maritima)

**genghis** (5, all) — I Battle of Sanfengshan ("son of Genghis Khan") · R Irghiz River skirmish · R Siege of Gurganj · R Otrar Catastrophe · R Battle of Irtysh River

**lincoln** (9, all) — R Battle of Stones River (Emancipation Proclamation) · I Battles of Lexington and Concord (the town of Lincoln) · I Battle of Fredericksburg (a visitor's remark to Lincoln) · I Battle of Bound Brook (Benjamin Lincoln) · I Battle of Monck's Corner (Benjamin Lincoln) · I Siege of Charleston (Benjamin Lincoln) · R Hampton Roads Conference · I Assassination of William McKinley ("following Abraham Lincoln") · I **b** Jones–Imboden Raid (Lincoln signed the statehood proclamation)

**plague** (8, all) — R Siege of Negroponte · R Siege of Lisbon (1384) · I Siege of Limerick (Ireton died of plague) · R Fifth siege of Gibraltar · R Djidjelli expedition · I Treaty of Constantinople 1590 ("*plagued* by civil wars") · R Zurich massacre · R Coronation of James I and Anne (London plague of 1603)

**crusade** (15 of 18) — R Battle of Wiłkomierz · R Battle of Forbie · I Action at Bir el Gubi (Operation *Crusader*) · R Battle of Sırpsındığı · R Battle of Skalice · R Battle of the Blacks · R Siege of Shaizar · I Siege of Sinope (background: Fourth Crusade) · R Kisrawan campaigns · R Treaty of Paris 1229 · R Treaty of Anagni · I Tarapoto massacre ("crusades against vice") · I Twin Pimples raid (Operation *Crusader*) · I Operation Flipper (Operation *Crusader*) · R Battle of Kůzová

**revolution** (15 of 171) — W Battles of Stockach and Engen · R Battle of Mečkin Kamen · W Battle of Fishdam Ford · W Siege of Condé · W Siege of Fort Stanwix · R **b** Russo-Persian Treaty of Friendship (after the Bolshevik Revolution) · I Treaty of Vincennes (land taken in the American Revolutionary War) · R Cry of Asencio · R Easter Rising · I Bahçelievler massacre ("revolutionary" in quotes) · R Shameen Incident · R 1979 U.S. embassy burning in Islamabad (Islamic Revolution) · R **b** Night of the Three Ps · W Burning of Falmouth · I Entebbe raid ("German Revolutionary Cells")

**carthage** (7, all) — R Battle of the Bagradas River · R Battles of Kroton · R Battle of the Crimissus · R Battle of Himera (480 BC) · I **b** Battle of Mantinea 207 BC (alliance with Carthage) · R Battle of the Great Plains · R Battle of Thacia

**verdun** (3, all) — R **b** Battle of Fontenoy (ended by the Treaty of Verdun) · R **b** Battle of Transylvania (Verdun offensive stopped) · R Treaty of Chambord (cedes Verdun)

**constantinople** (15 of 30) — I Battle of Nicopolis · I Battle of Marcellae · R **b** Battle of Kalavrye (revolt threatened Constantinople) · I Battle of Arcadiopolis · I Siege of Plevna · I Battle of Kosturino (rail line) · I Battle of Achelous · I Battle of Lule Burgas · I Siege of Knin · I Druze expedition 1585 · I Germanikeia Campaign · I Treaty of San Stefano (signed near it) · R Partitio terrarum imperii Romaniae (after the sack) · I Treaty of Montreuil ("Margaret of Constantinople") · I Treaty of Küçük Kaynarca (a church in it)

**Baseline sample** (found in the excerpt, not the title; 6 each): hannibal R R R I R R (I: Mago, "brother of Hannibal") · napoleon W R W R R W · churchill I I I R R R (I: cousin; John Churchill ×2) · caesar R R R R I R (I: Caesarea) · genghis R I I R R R (I: son, grandson) · lincoln I I I I I I (Lincolnshire ×3, Royal Lincolnshire Regiment, Lincoln Park, Lincoln National Forest) · plague I R I I (I: "plagued" ×2, Gibraltar background) · crusade R R R R R R · revolution W I W I W W (I: National Revolutionary Army ×2) · carthage R R R R R R · verdun R R I (I: "South American Verdun") · constantinople I R I I I R.
