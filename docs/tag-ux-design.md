# Tag UX design: related tags, browse by era, broader / narrower

Design for three improvements to tag selection on the map page (ideas 4, 5 and 6).
This is design only: no app code changes. All numbers come from `seed/wikidata_events.csv`
(19,176 rows, 19,124 approved, which is what `/api/events` serves) and, for the hierarchy,
from the tags' own Wikidata items, fetched on 2026-11-07.

It assumes the features the main session is building now: tag counts that follow the other
filters (tags with no matching events hidden), clickable tags in event details and cards,
several tags at once (chips, *any* / *all*), and `?tag=` in the URL. Names like
That work has since landed in `7214fe1`: `state.tagIds`, `state.tagMode`, `state.tagCounts`, `addTag`, `removeTag` and `setTags` below are its real names.

## 0. Recommendations

- **Build the hierarchy (6) first. Everything else uses it.** Generate it once from the
  Wikidata "part of" (P361) links between the tags' own items, keep only links whose child
  lies within the parent's years and that don't pass through `NO_CLIMB`, review it by hand,
  and merge it with `TAG_PARENTS`. Store it as `haam/data/tag_hierarchy.py` (a single parent
  per tag) and expose it as `parent_id` in `/api/tags`. Make tagging close over the same
  links so that "every Peninsular War event is also a Napoleonic Wars event" is always true.
  Today that adds a parent tag to 77 events. Use co-occurrence (option c) only as a test
  that flags missing links, not as the source.
- **Related tags (4):** a row of up to 6 chips (4 on phones) under both search boxes. They are
  computed in the browser from events that match the search and category (not the year or
  tag filters). Ranked by `k·√(k/size)`, at least `max(2, 2 % of matches)`. A parent is
  dropped when one of its children already covers ≥ 80 % of the parent's matches. Clicking a
  chip **replaces the word with the tag** (with Undo); Shift-click keeps both. "napoleon" →
  **Napoleonic Wars · French Revolution · Peninsular War**.
- **Browse by era (5):** a "Browse tags" dialog that opens from a button beside the tag search,
  styled like the large search window (a full-screen sheet on phones). It lists six eras
  (Ancient < 500, Medieval, Early modern, 1800s, 1900s, Today ≥ 2000) with one row per tag:
  name, years, a count that follows the filters, and a small span bar on the era's own axis.
  Children are nested under their parent. Use the list, not a bar chart: the prototype shows
  that labels on bars are unreadable for short wars.
  **Only 139 of the 340 tags have any events**, so the dialog shows those 139 by default.
- **Broader / narrower (6):** a "tag context" line under the selected tag chips, e.g.
  `Napoleonic Era › Napoleonic Wars › Peninsular War`, with clickable ancestors (clicking one
  replaces the tag) and chips for the narrower tags, with counts. Selecting a tag whose
  ancestor or descendant is already selected replaces it, because in both *any* and *all*
  mode that pair is redundant.
- **Order and cost:** hierarchy → related tags → era browser → tag context. About 4–5 days in
  total. No new event payload: tags gain one field (~5 KB in total).

---

## 1. What the data looks like

| Fact | Value |
|---|---|
| Approved events | 19,124 |
| Events with ≥ 1 tag | 6,812 (36 %) |
| Tags per tagged event | 1: 5,085 · 2: 1,540 · 3: 187 (never more than 3) |
| Curated tags (`TAGS`) | 340 |
| **Tags used by at least one event** | **139** (127 with ≥ 2, 86 with ≥ 10, 24 with ≥ 100) |
| Median size of a used tag | 18 events |
| Largest tags | World War II 1,032 · American Civil War 580 · World War I 523 · Napoleonic Era 484 · Napoleonic Wars 409 · Cold War 328 · French Revolution 288 |
| Tag pairs that ever appear on the same event | 49 |

`setupTagFilter` already hides the 201 unused tags, so the "340 tags readable" problem is
really a **139 tags** problem. That changes the design of idea 5: no paging and no virtual
scrolling, just a well-grouped list.

The skew matters for idea 4: seven tags hold 3,644 of the 8,726 tag assignments (42 %). Plain
frequency always puts them on top.

---

## 2. Idea 4: related tags under the search

### 2.1 What the real searches give

Matching works the way `searchScore` does: substring matching on the title, the 140-character
excerpt and the years, with every word required.

| Query | Matches | Tagged | Tags among the matches (count among matches / tag size) |
|---|---|---|---|
| napoleon | 94 | 73 | Napoleonic Era 62/484 · Napoleonic Wars 55/409 · French Revolution 16/288 · Peninsular War 5/157 |
| japan | 449 | 175 | World War II 143/1032 · Pacific War 104/215 · Second Sino-Japanese War 16/45 · Russo-Japanese War 14/18 · First Sino-Japanese War 9/9 |
| crusade | 127 | 117 | Crusades 108/175 · Albigensian Crusade 12/15 · First Crusade 8/9 · Second Crusade 8/10 · Northern Crusades 6/21 · Reconquista 6/182 |
| civil war | 666 | 457 | American Civil War 261/580 · English Civil War 54/78 · Spanish Civil War 38/73 · Arab Spring 31/69 · Syrian Civil War 28/173 |
| french | 1,095 | 713 | Napoleonic Era 210 · Napoleonic Wars 168 · French Revolution 166 · Peninsular War 73 · World War I 62 · Seven Years' War 43 |
| siege | 2,227 | 849 | Eighty Years' War 80 · Crusades 69 · Reconquista 61 · Napoleonic Era 59 · Napoleonic Wars 50 |
| ottoman | 450 | 89 | World War I 38 · Greek War of Independence 16 · Great Turkish War 15 (then counts of 4 or less) |
| hitler | 2 | 0 | none |

The feature pays off: for "napoleon", 73 of the 94 matches (78 %) have a tag, and two tags
cover most of them. The table also shows the two failure modes that ranking has to handle:

1. **Near-duplicate parents.** Napoleonic Era (62) and Napoleonic Wars (55) are almost the same
   set: all 409 Napoleonic Wars events are tagged Napoleonic Era. The same goes for American
   Revolution (111) and American Revolutionary War (110) under "revolution". Showing both
   wastes a chip.
2. **Broad tags drowning out specific ones.** For "japan", World War II (143) comes first by
   frequency, but Pacific War (104 of its 215 events match) is the better filter.

### 2.2 Ranking

Candidates are the tags on events that match the **search and category**, ignoring the year
and tag filters:

- *Tags are ignored* because otherwise, once a tag is selected, every match has that tag and
  the chips only repeat it.
- *Years are ignored* because `rescaleYears()` resets the slider to the fitted span whenever
  the tag or search changes. A chip computed under the current years would therefore count
  differently from what it shows once clicked. It also keeps the chips from jumping around
  while someone drags the slider.

Rules:

1. **Floor:** a tag must have `k ≥ max(2, ⌈2 % of matches⌉)` matching events. This removes
   one-off noise such as World War II 2/63 for "rome".
2. **Parent suppression:** using the hierarchy (idea 6), drop a parent when one of its
   candidate children has ≥ 80 % of the parent's `k`. Napoleonic Era (62) gives way to
   Napoleonic Wars (55, which is 89 %), but World War II (143) stays next to Pacific War
   (104, which is 73 %) because the war in China and Europe is a real difference. The
   dropped parent is one click away in the tag context (§4).
3. **Score** `k · √(k / size)`: matching count times the square root of the share of the tag
   that matches. I compared three formulas on 11 queries:

| Query | Frequency `k` | tf-idf `k·log(N/size)` | **`k·√(k/size)` + suppression** |
|---|---|---|---|
| napoleon | Era, Wars, French Rev., Peninsular | same | **Wars, French Rev., Peninsular** |
| japan | WWII, Pacific War, 2nd Sino-Jap., Russo-Jap. | Pacific, WWII, Russo-Jap., 2nd Sino-Jap. | **Pacific, WWII, Russo-Jap., 2nd Sino-Jap.** |
| french | Era, Wars, French Rev., Peninsular, WWI, Seven Years' | Era, French Rev., Wars, … | **French Rev., Wars, Peninsular, Seven Years', WWI, French Wars of Religion** |
| revolution | Am. Revolution, Am. Rev. War, French Rev., … | same | **Am. Rev. War, French Rev., Haitian Rev., Greek WoI, 1848, Mexican Rev.** |
| 1812 | Era, Wars, Peninsular, Lat. Am. WoI, Mexican WoI | Wars, Era, … | **Wars, Peninsular, Mexican WoI, Lat. Am. WoI** |
| crusade | Crusades, Albigensian, 1st, 2nd, Northern, *Reconquista* | … 3rd Crusade instead of Reconquista | **Crusades, Albigensian, 1st, 2nd, 3rd, Northern** |

   tf-idf barely changes the order because `log(N/size)` is flat across tags of 200–1,000
   events. The square-root form is just as cheap to compute and fixes both failure modes.
   Most of the gain comes from suppression; the score mainly lifts small specific tags such as
   French Wars of Religion (22/34) and Haitian Revolution (11/18).
4. **Tie-break:** higher `k` first, then the name.
5. **How many:** 6 on desktop and 4 on phones, plus "+N more" when more pass the floor. That
   chip opens the era browser (§3) filtered to those candidates.

### 2.3 UI

- **Where:** directly under the search input in the filter panel (one line, wrapping to at most
  two), and in the large search window between the status line ("94 events match") and the
  results. Both show the same row.
- **What a chip looks like:** the existing `.tag` style, plus the count of events the click
  will give: the tag's size under the current category, e.g. `Napoleonic Wars 409`. The
  tooltip and `aria-label` say "55 of your 94 results · 409 events with this tag". The row
  starts with a muted label "Tags:" and, when useful, coverage text: "73 of 94 results have a
  tag".
- **Click: replace the word with the tag.** The goal is to get from a vague word to a precise
  filter, and keeping "napoleon" would leave only 55 of the 409 events. So the click selects
  the tag and clears the search. A live line under the row says
  `Search “napoleon” replaced by tag Napoleonic Wars · Undo`. Undo restores both and stays
  until the next filter change.
- **Shift-click** (and a small `+` inside the chip on touch, shown only in the large window)
  **adds the tag and keeps the search**, for "Napoleon battles within the Peninsular War".
- **Already selected tags** are shown pressed (`aria-pressed="true"`). Clicking one removes it.
- **In the large window**, clicking a chip also closes the window, the same way opening a
  result does, because the map with the tag's events is now the answer. Shift-click keeps it
  open.
- **Keyboard:** the chips are a `role="group"` toolbar placed between the input and the
  results. Tab moves from the input into the chip row, and ←/→ moves between chips (roving
  tabindex). In the large window, ↑/↓ keep moving through the results as they do now, and
  Alt+1…6 picks chip n without leaving the input.
- **Phone:** one line that scrolls sideways (`overflow-x: auto`, no wrapping) under the search
  box, so the filter panel doesn't grow.

### 2.4 Edge cases

| Case | Behaviour |
|---|---|
| No search terms | Row hidden. |
| Matches but none tagged ("hitler": 2 matches, 0 tagged) | Row hidden. No "no tags" message: it would only add noise. |
| Only one candidate | Show it. One click to a 1,032-event filter is still useful. |
| Very broad query ("siege": 2,227 matches) | Floor = 45, so 4 chips. The coverage text ("849 of 2,227 have a tag") explains why the chips cover only a small part. |
| One-letter or very short terms | Already handled by the search. The chips follow `search.terms`. |
| *Any word* mode, whole words | Use the same `searchScore > 0` set, so the chips always match the results. |
| Collection map | Works the same over the collection's events, because it is computed from loaded data. |

### 2.5 Data and cost

All of it runs in the browser on the events already loaded. Computed in `applyFilters()` only
when the key `[query, category, search options]` changes, which is the same key
`rescaleYears()` uses. It is one pass over the events that match the search (at most 19k,
each with ≤ 3 tags) into a `Map`, then a sort of at most 139 entries. That is well under 5 ms,
and it reuses `searchScore` results when they are cached for the pass. There is no new API.
The tag sizes per category (`size`) are counted once at startup, 6 × 139 numbers.

---

## 3. Idea 5: browse tags by era

### 3.1 Bars versus a list (prototype)

`docs/prototypes/tag-eras.html` is a throwaway page with the 139 real tags, their counts and
the proposed parents. It has two views:

- **Bars only** (a timeline per era, greedy lanes): it packs into 3–8 lanes per era (32 in
  total), so it is compact, but most labels get cut to two letters ("Fr…", "Na…") because 56
  of the 139 tags last ≤ 5 years. The bars can only be read through tooltips, which phones
  don't have.
- **List + span bars:** one row per tag (name, years, count, and a thin bar on the era's axis).
  It stays readable at 375 px, can be searched, and still shows overlap: in the 1800s panel you
  can see the Napoleonic Wars, the Peninsular War and the Latin American Wars of Independence
  stacked on the same years.

**Decision: list + span bars.** A full bar chart could come later as a toggle; it is not needed now.

### 3.2 Eras

| Era | Years | Used tags (start in era) | Events tagged | Notes |
|---|---|---|---|---|
| Ancient | before 500 | 17 | 252 | Axis runs from 800 BC to AD 499. The 3 Bronze Age tags begin before that and show a "◂" at the left edge. |
| Medieval | 500–1499 | 19 | 651 | Reconquista (718–1492) is the long bar. |
| Early modern | 1500–1799 | 33 | 2,354 | The busiest era. Collapsed parents help most here. |
| 1800s | 1800–1899 | 27 | 1,753 | |
| 1900s | 1900–1999 | 38 | 3,085 | Cold War with 5 nested children. |
| Today | 2000 onwards | 5 | 631 | War on Terror, Iraq War, Arab Spring, Syrian Civil War, Russo-Ukrainian War (three of them still ongoing). |

Rules:

- **A tag goes where it starts**, and only there. 18 of the 139 cross a boundary (e.g.
  Napoleonic Era 1799–1815, Scramble for Africa, Dissolution of Yugoslavia 1991–2008). Their
  bar runs to the right edge with a "▸" and the row says "continues into the 1800s". Listing
  them twice would make the counts per era misleading and the keyboard order confusing.
  "Start" is what people know a war by.
- **Ongoing tags** (`end_year = null`: War on Terror, Syrian Civil War, Russo-Ukrainian War)
  are shown as "2014 – present" with a bar that runs to the current year and ends in "▸".
- **Order within an era:** by start year, longer first on ties, so a parent comes before the
  children that start with it.
- **Nesting:** a child is indented under its parent when both are in the same era (Crusades
  with 6 children, Cold War with 5, Punic Wars with 2, Napoleonic Era › Wars › Peninsular).
  With the hierarchy from §4.2, that puts 30 of the 139 tags under a parent, so the top level has 109 rows. A child whose
  parent is in another era stays at the top level with a muted "in Napoleonic Era" note.
  Parents can't be collapsed in v1: there are at most 7 children, so collapsing isn't worth
  the extra interaction.
- **Tiny tags:** 12 tags have exactly 1 event. They stay, with a muted count. Hiding them would
  make the browser disagree with the tag menu.

### 3.3 UI

- **Opening it:** a "Browse tags" button (icon `fa-stream`) inside `#tag-search-box`, next to
  the clear button, and a "Browse all…" link under the tag menu in the filter panel. There is
  no global shortcut, because `/` is taken and one-letter shortcuts collide with typing. Inside
  the tag search, ↓ on an empty box opens the suggestions as it does today, and the last
  suggestion row is "Browse all tags by era…".
- **Shape:** the same layout as the large search window (`.search-panel`, a centred dialog of
  about 760 px on desktop, a full-screen sheet on phones). The header has a filter box (filters
  rows by name, folding accents like `foldText`) and era jump chips with counts
  (`Ancient 17 · Medieval 19 · …`). The era headers stay pinned while scrolling.
- **Rows:** `[name] [years, muted] [count] [span bar]`. On phones the bar moves under the name,
  so the name never gets cut.
- **Counts follow the filters** (the main session's work): the count is the number of events
  that match the category, search and years, with zero-count rows hidden. The footer says, for example, "Showing 74 of 139 tags
  that match your filters · Show all". Opening the browser with no filters shows all 139.
- **Selecting:**
  - In single-tag mode, a click selects the tag and closes the dialog.
  - In multi-tag mode, a click toggles the tag (a check mark appears) and the dialog stays
    open. The footer then shows the chips that are currently selected and the *any / all*
    switch, plus "Done".
- **Keyboard:** the list is a `listbox`. ↑/↓ move, Home/End go to the first and last row,
  PageUp/PageDown jump to the previous or next era, Enter selects, Space toggles in
  multi-select, typing goes into the filter box, and Esc closes and returns focus to the button.
- **Colour by year:** the bars stay neutral. The year colours are scaled to the events shown on
  the map, so they would mean something different in the dialog.

### 3.4 Edge cases

| Case | Behaviour |
|---|---|
| Every tag filtered out (e.g. category Natural, where hardly any events are tagged) | "No tags match the current filters" with a "Show all tags" button that ignores the filters. Clicking a tag then also resets the category. |
| Filter box with no match | "No tag called “xyz”. Search events instead?" Clicking it closes the dialog and runs the large search with that text. |
| Collection map | Lists only the tags among the collection's entries. Often one era, so the other eras disappear. |
| A tag with `start_year = null` | None exist today. Put it in a final group, "Undated". |

### 3.5 Data and cost

Everything is already in `/api/tags` (`start_year`, `end_year`, `display_range`) plus
`parent_id` from idea 6. The rows are built the first time the dialog opens (139 rows, under
10 ms). After that, only the counts and the hidden rows change, and only while the dialog is
open (it listens to the same "filters changed" hook as the event list). There is no new
endpoint. The era boundaries are a small constant in JS.

---

## 4. Idea 6: broader / narrower tags

### 4.1 Three ways to get the hierarchy, measured

**(a) The curated `TAG_PARENTS`** in `haam/tagging.py`: 7 links (American Revolutionary War →
American Revolution, Reign of Terror → French Revolution, Directory → French Revolution,
Peninsular War → Napoleonic Wars, Napoleonic Wars → Napoleonic Era, Congress of Vienna →
Napoleonic Era, First Industrial Revolution → Industrial Revolution).

- *Right:* all 7 are correct, and they are already enforced in tagging.
- *Wrong:* nothing is wrong, but they cover 7 of about 40 real relations, with nothing for the
  Crusades, the Cold War, World War II or the Punic Wars.

**(b) Wikidata P361 between the tags' own items.** I resolved every tag name to an item through
the English Wikipedia (`prop=pageprops`, following redirects; 310 of 340 resolve and the 30
that don't have no events). Then I climbed P361 up to 5 levels from each item and stopped at
the nearest item that is itself a tag. Raw result: **90 links**. Problems found:

| Problem | Count | Real example | Fix |
|---|---|---|---|
| Several tags resolve to one item | 9 items, 20 tags | Early, Middle and Late Bronze Age all redirect to *Bronze Age* (Q11761). Dutch Revolt and Eighty Years' War are the same item. | Ignore shared items. Their links come from (a). |
| The parent fails the year check | 12 | Haitian Revolution → French Revolution (through *French Revolutionary Wars*). Hussite Wars → Crusades (1419 vs. ending in 1291). Syrian Civil War → Arab Spring. Second Sino-Japanese War → World War II (1937 vs. 1939). | Require the child's years to lie within the parent's (±1 year, the tagger's `START_SLACK`). Allow exceptions in an override list. |
| Path through a `NO_CLIMB` item | 2 | Iraq War → Syrian Civil War through *War against the Islamic State*. Lebanese Civil War → Cold War through *Arab Cold War*. | Apply `NO_CLIMB` to tag chains as well. |
| Redirect to a broader article | some | "Feudal Japan" → *History of Japan*, "Boer Wars" → *Military history of South Africa* | Review the redirect-mapped tags and set the item by hand where needed. |

After those filters, **50 links** remain and no tag has two parents. They include 3 of the
7 curated links. The other 4 have no P361 link in Wikidata at all, e.g. Napoleonic Wars has no
"part of" pointing to *Napoleonic era* (Q122204616).

- *Right:* Pacific War → WWII, Gallipoli → WWI (through *Middle Eastern theatre*), Battle of
  Stalingrad → WWII (through Eastern Front › Eastern European theatre › European theatre),
  6 crusades → Crusades, Korean/Vietnam/Algerian/Soviet-Afghan wars → Cold War, Franco-Prussian
  and Second Schleswig War → German Unification, Yugoslav Wars → Dissolution of Yugoslavia,
  Second/Third Punic War → Punic Wars, First/Second Balkan War → Balkan Wars,
  4 Anglo-Mysore wars → Mysore Wars, War of Jenkins' Ear → War of Austrian Succession.
- *Wrong or debatable:* Smolensk War → Thirty Years' War (most accounts treat it as separate;
  drop it). Muromachi/Edo/… → Feudal Japan is right only by accident, through the wrong
  redirect.

**(c) Inference from years plus co-occurrence on events:** A → B if B's years contain A's,
≥ 80 % of A's events also carry B, and B is larger. Then a transitive reduction. Result:
**32 links**. The thresholds hardly matter: 0.5, 0.8 and 0.9 give 32–33 links, because only
49 tag pairs ever share an event.

- *Right:* it finds Napoleonic Wars → Napoleonic Era (409/409) and adds Mexican War of
  Independence → Latin American Wars of Independence (19/19) and First Boer War → Boer Wars
  (9/9). Wikidata links neither of these.
- *Wrong:* it can only see what tagging already produced, which is mostly (b) again through
  the events' chains. It is blind to the 201 unused tags and to links that tagging misses: the
  Second Boer War (42 events) shares **0** events with Boer Wars, because the tag name doesn't
  match the item's label. It invents links between near-duplicates, choosing the direction
  only by size, e.g. Yugoslav Wars (146) → Dissolution of Yugoslavia (148), where 146 of the
  148 overlap. It picks up chance overlaps: Anglo-Spanish War → Eighty Years' War (36/36,
  arguably related, not a part), Late Bronze Age → Bronze Age, which rests on a single event.
  It also changes every time events are imported.

### 4.2 Recommendation: (b) as the source, (a) as overrides, (c) as a test

1. **Generate once** with `scripts/generate_tag_hierarchy.py` (network access, about 20 API
   calls, with the project's User-Agent). Write `haam/data/tag_hierarchy.py`:
   ```python
   TAG_QIDS = {"Napoleonic Wars": "Q78994", ...}       # also useful for tagging by QID later
   TAG_HIERARCHY = {"Peninsular War": "Napoleonic Wars", ...}   # child -> its one parent
   ```
   Apply the filters from §4.1. Merge in `TAG_PARENTS`, plus a small `EXTRA_PARENTS` / `NOT_PARENTS`
   in the generator for the hand-reviewed changes. Proposed changes from this review:
   - add Mexican War of Independence → Latin American Wars of Independence;
   - add First Boer War → Boer Wars;
   - add Late Bronze Age, Middle Bronze Age and Early Bronze Age → Bronze Age;
   - add Second Sino-Japanese War → World War II, as a year exception;
   - drop Smolensk War → Thirty Years' War.

   The file is committed and reviewed like `tags.py`. It is regenerated only when `TAGS`
   changes.
2. **One parent per tag.** After filtering, the data never needs two. Keeping one makes
   breadcrumbs unambiguous and `parent_id` a single field. If a second parent is ever needed,
   the generator fails and forces a decision.
3. **Tagging uses the same links.** `TagMatcher` currently closes over `TAG_PARENTS`. Switch it
   to `TAG_HIERARCHY`, which still passes the year check per tag. Then "narrower" really is a
   subset. Measured effect: 77 events gain a parent tag, e.g. Second Boer War → Boer Wars
   (+42, so Boer Wars grows from 9 to 51), War of Jenkins' Ear → War of Austrian Succession
   (+13, a tag that has **0** events today because the Wikidata label is "War of *the*
   Austrian Succession"), Anglo-Mysore wars → Mysore Wars (+16), Muromachi Period → Feudal
   Japan (+5). Apply it without network access through a new `flask haam apply-tag-parents`
   (it rewrites the CSV and DB tags from the existing tags). That is cheaper than `retag-csv`.
4. **Co-occurrence as a test:** `tests/test_tag_hierarchy.py` fails if a pair of used tags has
   ≥ 90 % co-occurrence and year containment but no link in either direction. That would have
   caught Napoleonic Wars → Era and Mexican WoI → Latin American WoI. Known exceptions are
   listed in the test.

Resulting tree: 32 of the 139 used tags have a used parent (39 once retagging gives Mysore Wars, War of Austrian Succession and Feudal Japan their events). The deepest chain is 3 levels
(Napoleonic Era › Napoleonic Wars › Peninsular War). Across all 340 tags, the parents with the most children are
Crusades 7, Cold War 5, Feudal Japan 5, Mysore Wars 4 and World War I 3. The full list of
generated links is in Appendix A.

### 4.3 UI

- **Tag context line:** under the selected tag chips, both above the event list
  (`#tag-search-box`) and in the filter panel under the tag menu. For the most recently
  selected tag:
  ```
  ↑ Napoleonic Era › Napoleonic Wars › Peninsular War        (157 events · 1807–1814)
    Narrower: —
  ```
  ```
  ↑ Crusades                                                  (175 events · 1096–1291)
    Narrower: First Crusade 9 · Second 10 · Third 7 · Fourth 3 · Albigensian 15 · Northern 21
  ```
  Ancestors are links. Narrower tags are chips with counts that follow the filters, sorted by
  start year, and those with 0 are hidden. The line is hidden for a tag with no parent and no
  children; 107 of the 139 used tags have no parent, but many of those have children.
- **Click on an ancestor or a narrower tag: replace** that tag in the selection. It isn't added,
  because:
  - in *any* mode, parent + child = parent;
  - in *all* mode, parent + child = child.

  So adding is never what someone wants. The same rule applies anywhere a tag gets selected
  (tag menu, card tags, related chips, era browser). If the new tag is an ancestor or a
  descendant of one already selected, it replaces it, and the live region says
  "Replaced Peninsular War by Napoleonic Wars". Ctrl/⌘-click keeps the usual multi-select
  behaviour for anyone who insists.
- **Several tags selected:** the context line follows the chip that was clicked or focused last
  (it shows the tag's name), so there is at most one line.
- **Event details and cards:** tags stay flat (there are at most 3). The tooltip shows the path
  ("Napoleonic Era › Napoleonic Wars › Peninsular War").
- **Tag menu (`<select>`):** children are listed right after their parent and indented with
  ` ` (selects can't contain nested markup). The same ordering is used in `tag-picker.js`
  for collections.
- **Keyboard:** the links and chips are ordinary tab stops. In the tag search input, Alt+↑ goes
  to the broader tag and Alt+↓ opens the first narrower chip. This is cheap and needs no extra
  hint text.
- **Phone:** the context line wraps, and the narrower chips scroll sideways like the related
  tags.

### 4.4 Data and cost

`/api/tags` gains `parent_id` (int or null), computed in `Tag.to_dict()` from `TAG_HIERARCHY`
by name, so no database column or migration is needed (`all_tags()` loads all 340 anyway).
That is about 15 bytes × 340 = 5 KB, before gzip. The client builds `childrenById` once at
startup. Counts reuse the per-filter tag counts the main session is adding.

---

## 5. Interplay with existing features

| Feature | Related tags (4) | Era browser (5) | Broader / narrower (6) |
|---|---|---|---|
| Single / multi tag filter, any / all | A chip click replaces the query and adds the tag, then de-duplicates against ancestors and descendants (§4.3). Selected chips are shown pressed. | Single mode: select and close. Multi mode: toggle, with the *any / all* switch in the footer. | Clicking a link replaces the tag. Adding an ancestor or descendant replaces it everywhere. |
| `?tag=` in the URL | A chip click updates `?tag=` and drops `?q=` (if the main session adds one). Undo restores both. | Same as any tag selection. | Same. A breadcrumb click is a normal `pushState`, so Back goes to the narrower tag. |
| Year slider that fits itself | No change: the tag and query change, so `rescaleYears` refits to the tag. The chips ignore years, so they don't move while someone drags. | Same. Counts with "follow the filters" use the current years. | Going broader widens the slider to the broader tag, e.g. Peninsular 1807–14 → Napoleonic Wars 1803–15. |
| Timeline spans the tag's years | It follows the selected tag. | It follows. With several tags, the union of their spans (main session). | Broader gives a wider span. For ongoing tags `timelineRange` already ends at the current year. |
| Search window (`/`) | The chips sit between the status line and the results. Alt+1…6 picks one, and a click closes the window. | Opened from the tag box, not from `/`. "Search events instead?" hands over to the search window. | Not shown in the search window (no tag context there). |
| Colour by year | Unaffected: it rescales to the shown events in `updateColorRange`. | The bars stay neutral (see 3.3). | Unaffected. |
| Collections (map view, tag-based collections) | Works over the collection's events. | Shows only the collection's tags. | The links are global. Optional link "Make a collection from this tag" in the context line, through the existing tag-based collection form. With tagging closed over the hierarchy, a "Boer Wars" collection now contains the Second Boer War events too. |

---

## 6. Implementation plan

Estimates are for one developer who knows the code. Each step can be committed on its own.

### Step 1: hierarchy data (≈ 1 day)
- `scripts/generate_tag_hierarchy.py`: resolve the tags through `en.wikipedia.org` pageprops,
  read P361 (`wbgetentities`, 50 per call, with `Retry-After` handling; the API returned 429
  during this study), climb up to `MAX_DEPTH`, apply the filters, merge `TAG_PARENTS` and the
  overrides, and print a review diff.
- `haam/data/tag_hierarchy.py` (generated, committed): `TAG_QIDS`, `TAG_HIERARCHY`.
- `haam/tagging.py`: `TagMatcher` default `parents` = `{child: [parent]}` from `TAG_HIERARCHY`.
  Keep `TAG_PARENTS` as the hand-written input to the generator.
- `haam/cli.py`: `flask haam apply-tag-parents [--csv seed/wikidata_events.csv]` closes the
  existing tags over the hierarchy, with the year check, without network access.
- `haam/models.py`: `Tag.to_dict()` adds `parent_id` (a name → id lookup, cached per request).
- Tests (`tests/test_tag_hierarchy.py`):
  - every name in `TAG_HIERARCHY` is in `TAGS`;
  - there are no cycles;
  - one parent per tag;
  - the child's years lie within the parent's, apart from the listed exceptions;
  - the co-occurrence check from §4.2.4 against the seed CSV;
  - `TagMatcher.match(["Peninsular War"], 1810)` gives all three Napoleonic tags;
  - `match(["Second Sino-Japanese War"], 1937)` does not give World War II (year check);
  - `apply-tag-parents` is idempotent;
  - `/api/tags` includes `parent_id`.

### Step 2: related tags (≈ 1 day)
- `haam/static/js/tag-suggest.js` (new): a pure function
  `relatedTags(events, {score, sizes, parentOf, limit})` that can be tested without a DOM.
- `haam/static/js/map.js`: call it from `applyFilters` when the search key changes, render
  `#related-tags` under `#search` and in `#search-panel`, plus chip click (replace and Undo),
  Shift-click and Alt+1…6.
- `haam/templates/map.html`: two `<div class="related-tags" role="group" aria-label="Tags among the results">`.
- `haam/static/css/main.css`: `.related-tags` (wraps on desktop, scrolls sideways under 860 px).
- Tests: `node --test` on `tag-suggest.js` with a fixture built from the CSV. Check that
  "napoleon" → `[Napoleonic Wars, French Revolution, Peninsular War]` (Era suppressed), that
  "japan" puts Pacific War first and keeps WWII, and that "hitler" → `[]`. Check by hand that
  Undo restores the query and the tag.

### Step 3: era browser (≈ 1.5 days)
- `haam/static/js/tag-browser.js` (new): builds the dialog from the tags and `parent_id`. It
  exposes `open()`, `update(counts)` and an `onSelect` callback.
- `map.html`: the `#tag-browser` dialog markup and the "Browse tags" button in
  `#tag-search-box`. `main.css`: rows, span bars and pinned era headers, reusing the
  `.search-panel` layout.
- Tests: era assignment for -1200, 499, 500, 1799, 1800 and 2014-ongoing. Nesting puts
  Peninsular War under Napoleonic Wars under Napoleonic Era. Keyboard checks by hand: ↑/↓,
  PageDown, Enter, Esc returning focus. Check at 375 px and 1280 px.

### Step 4: tag context and de-duplication (≈ 1 day)
- `map.js`: `renderTagContext()` next to `syncTagSearch()`; de-duplicate ancestors and descendants
  inside the existing `setTags()` (which `addTag()` calls), not in a second copy; Alt+↑/↓ in `#tag-search`; indented `<option>`s.
- `tag-picker.js`: the same ordering.
- Tests: selecting Napoleonic Era while Peninsular War is selected leaves only Napoleonic Era in
  both modes. A breadcrumb click updates `?tag=`, and Back restores it.

### Risks
- **Conflicts with the main session's multi-tag work in `map.js`.** Steps 2–4 touch the same
  selection code. That work is now merged (`7214fe1`). Build on it, and add the de-duplication inside its
  `setTags()` instead of next to it.
- **Wikidata drift and rate limits.** The hierarchy is a committed snapshot, so the site never
  depends on Wikidata at runtime. Regenerating it shows a diff for review.
- **Retagging changes tag sizes** (Boer Wars 9 → 51, War of Austrian Succession 0 → 13), and
  through that the tag-based collections created afterwards. Existing collections keep their
  entries. Mention it in the release notes.
- **Replacing the search on a chip click can surprise people.** The Undo line and Shift-click
  cover it. If testers still dislike it, switching to "add, keep the query" is a one-line
  change.
- **Debatable links** (Anglo-Spanish War, Smolensk War, Sengoku Period): the generator's
  override lists make these explicit decisions instead of silent ones.

**Total: about 4.5 days**, plus about half a day of review of the generated hierarchy.

---

## Appendix A: generated links after the filters (option b)

`count` = events with that tag today. Items reached through a redirect are noted. Links that are
also in `TAG_PARENTS` are marked ✓.

| Child | Parent | Child count | Parent count | Note |
|---|---|---|---|---|
| American Revolutionary War | American Revolution | 241 | 244 | ✓ |
| First Balkan War | Balkan Wars | 27 | 33 | |
| Second Balkan War | Balkan Wars | 5 | 33 | |
| Second Boer War | Boer Wars | 42 | 9 | Parent reached through the redirect *Military history of South Africa*. Set the item by hand. |
| Chinese Communist Revolution | Chinese Civil War | 0 | 27 | |
| Algerian War of Independence | Cold War | 12 | 328 | |
| Hungarian Revolution of 1956 | Cold War | 1 | 328 | |
| Korean War | Cold War | 85 | 328 | |
| Soviet-Afghan War | Cold War | 14 | 328 | Wikidata also gives War on Terror, which the year check drops. |
| Vietnam War | Cold War | 100 | 328 | |
| Albigensian / Children's / First / Second / Third / Fourth / Northern Crusade(s) | Crusades | 15 / 0 / 9 / 10 / 7 / 3 / 21 | 175 | |
| Yugoslav Wars | Dissolution of Yugoslavia | 146 | 148 | |
| Azuchi-Momoyama, Edo, Kamakura, Muromachi, Sengoku Period | Feudal Japan | 0, 0, 0, 5, 0 | 0 | "Feudal Japan" redirects to *History of Japan*. Correct only by accident. |
| Reign of Terror | French Revolution | 1 | 288 | ✓ |
| Franco-Prussian War, Second Schleswig War | German Unification | 56, 9 | 93 | |
| Hallstatt Culture, La Tène Culture | Iron Age | 0, 0 | 0 | |
| War of the League of Cambrai | Italian Wars | 18 | 47 | |
| Yuan Dynasty | Mongol Empire | 0 | 0 | |
| First–Fourth Anglo-Mysore War | Mysore Wars | 1, 6, 7, 2 | 0 | Mysore Wars has 0 events because its name doesn't match the label "Anglo-Mysore wars". |
| Peninsular War | Napoleonic Wars | 157 | 409 | ✓ |
| Counter-Reformation, English Reformation | Protestant Reformation | 0, 0 | 2 | |
| Second Punic War, Third Punic War | Punic Wars | 54, 4 | 80 | |
| High Renaissance, Northern Renaissance | Renaissance | 0, 0 | 0 | |
| Early Christianity | Rise of Christianity | 0 | 0 | |
| Smolensk War | Thirty Years' War | 3 | 118 | **Drop** (separate war). |
| War of Jenkins' Ear | War of Austrian Succession | 13 | 0 | Parent has 0 events because of the "the" in the label. |
| Iraq War | War on Terror | 58 | 193 | |
| Eastern Front, Western Front, Gallipoli Campaign | World War I | 0, 0, 14 | 523 | |
| Battle of Stalingrad, Pacific War | World War II | 3, 215 | 1,032 | |

Dropped by the year check: Byzantine Empire → Roman Empire, Carnatic Wars → Seven Years' War,
Haitian Revolution → French Revolution, Heian Period → Feudal Japan, Hellenistic Period → Ancient
Greece, Hussite Wars → Crusades, Neolithic Revolution → Neolithic, Second Sino-Japanese War →
Pacific War / World War II, Sengoku Period → Muromachi Period, Soviet-Afghan War → War on Terror,
Syrian Civil War → Arab Spring. Dropped by `NO_CLIMB`: Iraq War → Syrian Civil War, Lebanese
Civil War → Cold War.

## Appendix B: how the numbers were produced

Throwaway scripts, not committed. They read `seed/wikidata_events.csv` (approved rows only) and
`haam/data/tags.py`, and imitate `searchScore` (substring, all words, title + 140-character
excerpt + years). The Wikidata part used `en.wikipedia.org/w/api.php?prop=pageprops` to resolve
titles and `wikidata.org/w/api.php?action=wbgetentities` (P361, up to 5 levels: 299 tag items and
442 items in total). Step 1's generator does the same, so the figures can be reproduced.
