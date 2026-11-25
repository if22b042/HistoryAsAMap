# Feature decisions

What the project owner decided about every proposed feature or improvement, across all the
review lists. Newest first. When a decision changes, update the row here and note the date.

| Source | Date | File |
|---|---|---|
| 30 ranked features | 25 Nov 2026 | [TOP-30-FEATURES.md](TOP-30-FEATURES.md) |
| Code review: approved and refused new features | 16 Nov 2026 | [REVIEW-2026-11-16.md](REVIEW-2026-11-16.md) §3 |
| The 20 best improvements | 8 Nov 2026 | [TOP-20-IMPROVEMENTS.md](TOP-20-IMPROVEMENTS.md) |
| Original ToDo | 2026 | [../ToDo](../ToDo) |

**Legend:** ✅ approved, implement · 📐 approved, plan first (a session asks questions before
coding) · 📄 good idea, documented, not now · ⏭️ skipped · ⛔ refused · ❔ no answer yet ·
✔️ built.

---

## 25 November 2026: the 30 ranked features

| # | Feature | Decision | Notes |
|---|---|---|---|
| 1 | Search the full summaries | 📐 analysed | The owner worried that passing mentions would flood the map. The analysis ([search-precision.md](search-precision.md)) found that the extra matches are about 73% relevant, against 78% for today's search. Noise comes from namesakes (HMS *Hannibal*, *Churchill* tanks) and places named in passing (Constantinople: 13% relevant). **Recommended: the owner's own idea.** The map keeps title + excerpt; full-text matches appear only in the big search list as "Also mentioned in N events", with a "show on map" switch. Not built yet. |
| 2 | "What happened here": a place over time | 📐 | A planning session asks questions, then implements |
| 3 | Where each date and place came from + `/quality` page | ⏭️ | |
| 4 | Story mode | 📐 | For collections **and tags**. Extra story features are being proposed |
| 5 | Tag landing pages `/tag/<id>-<slug>` | ✅ | Being implemented; extra features are put to the owner first |
| 6 | Importance score (sitelinks) | ✅ careful | **Only** an opt-in "Major events" button next to the heatmap. No change to the default view, search ranking or game picks for now |
| 7 | Region / country filter | ⏭️ | Also closes the ToDo's "Greece" request for now |
| 8 | Related events in the map's details panel | ⏭️ | They stay on the event page only |
| 9 | Category donuts on clusters + legend | ⏭️ | |
| 10 | Keyboard and screen-reader route through the map | ⏭️ | |
| 11 | Tag hierarchy, era browser, related tags | 📐 elaborate | A session works out the design in more depth (from [tag-ux-design.md](tag-ux-design.md)) and asks questions |
| 12 | Import of the missing famous events | ⏭️ | |
| 13 | Game by tag | ✅ | Practice mode only, not the daily game |
| 14 | Link collection entries to main-map events | ❔ | |
| 15 | Time-lapse with trails and presets | ❔ | |
| 16 | "The world in year X" | ✅ | The owner points out that "On this day" already exists (the welcome card), so this is not a conflict. Region grouping uses `regions.region_at` (no region column, since #7 was skipped). Ranking uses sitelinks once #6 lands |
| 17 | Tag suggestions for untagged events | ⏭️ | |
| 18 | Open dataset (CSV / GeoJSON) | ❔ | |
| 19 | schema.org `Event` data | ❔ | |
| 20 | "Open on HAAM" from Wikipedia | ✅ | |
| 21 | Event pictures | ⏭️ | |
| 22 | Review-queue warnings | ❔ | |
| 23 | Start and end dates | ✅ in depth | The owner asked for it to be done thoroughly and proven by tests: end year from Wikidata, ranges shown, "include ongoing events" in the year filter. A missing end date means unknown |
| 24 | Wikidata fact box | ⏭️ | |
| 25 | Editor audit log with undo | ⏭️ | |
| 26 | Compare two views on one map | 📄 | A good idea; keep it documented and do not implement for now. It needs `map.js`'s global state split into a reusable view first. Comparing two collections is the easier first step |
| 27 | Showing approximate dates | ⏭️ | There are no approximate dates in the data |
| 28 | Collection history and undo | ⏭️ | |
| 29 | Classroom board without accounts | 📄 | Documented, not yet. Blocker: children's data (GDPR). Generated nicknames only, deletion after 30 days, the school as data controller. Revisit once story mode and quizzes show that teachers use the site |
| 30 | Cause and effect links | ⏭️ | Wikidata has causes on 2% and effects on 0% of events |
| – | Playwright smoke tests before the `map.js` features | ❔ | Proposed as a prerequisite; no answer yet |

### Earlier in the same review (first 10 ideas, 25 Nov)

These were the first, shorter list. Its items became #1, #2, #3, #4, #6, #7, #8, #11, #12,
#15 and #26 above; the decisions there apply.

---

## 16 November 2026: new features from the code review

### Approved then, and their state now

| Feature | Decision | State (checked in the code, 25 Nov) |
|---|---|---|
| Wikipedia page id in event addresses | ✅ | ✔️ built |
| Time-lapse | ✅ | ✔️ built (`map.js`, 10-year window) |
| Near here | ✅ | ✔️ built |
| Shareable view + "copy link to this view" | ✅ | ✔️ built (`map.html` `#copy-view`) |
| Embed (`/embed`) | ✅ | ✔️ built |
| Suggest an entry (collections) | ✅ | ✔️ built |
| Copy a collection | ✅ | ✔️ built |
| Collection from a search | ✅ | ✔️ built |
| Quiz from a collection | ✅ | ✔️ built |
| Game additions (scores vs today's average, challenge link, "which came first?") | ✅ | ✔️ built (also an archive calendar and hints) |
| Report a problem with an event | ✅ | ✔️ built |
| Edit link by email | ✅ | ✔️ built (needs SMTP settings) |

### Refused then (still refused)

| Feature | Decision |
|---|---|
| Historical borders overlay | ⛔ |
| Export of collections | ⛔ |
| Bulk import into a collection | ⛔ |
| People filter | ⛔ |
| Year histogram on the slider | ⛔ |
| Offline app | ⛔ |
| "On this day" feed | ⛔ (an "On this day" item on the welcome card exists and is fine) |
| Other languages | ⛔ |

---

## 8 November 2026: the 20 best improvements

| # | Improvement | State (25 Nov) | Later decision |
|---|---|---|---|
| 1 | Search the full description | Half: the excerpt grew from 140 to 300 characters | See #1 of 25 Nov |
| 2 | "Add to collection" from the map | ✔️ built | |
| 3 | Event pages, share previews, sitemap | ✔️ built | |
| 4 | Fast first load (chunks, caching) | ✔️ built | |
| 5 | Phone layout | ✔️ built | |
| 6 | Fix the categories | ✔️ built ("disaster" split off) | |
| 7 | Importance score + famous gaps | Open | Score ✅ careful (#6); famous-event import ⏭️ (#12) |
| 8 | Rate limits + moderation gate | ✔️ built (featured collections by editor flag) | |
| 9 | "Is this an event?" check | ✔️ mostly (refuses articles with no date; no type check) | |
| 10 | Shared tag links zoom; search fits results | ✔️ built for regional tags | |
| 11 | Colour-by-year scale | ✔️ built (follows the slider's breakpoints) | |
| 12 | Clusters that say what's inside | Half: single-category colour only | Donuts ⏭️ (#9) |
| 13 | Related events | Half: on the event page only | Map panel ⏭️ (#8) |
| 14 | Story mode | Open; reorder built | 📐 (#4) |
| 15 | Tag coverage + place filter | Open | Place filter ⏭️ (#7); tag suggestions ⏭️ (#17) |
| 16 | Collection editor that scales | ✔️ built (drag to reorder, bulk remove) | |
| 17 | Front door (intro, on this day, featured collections) | ✔️ built | |
| 18 | Start and end dates | Open | ✅ in depth (#23) |
| 19 | Accessibility pass | Half: live counts done; no skip link or keyboard route | ⏭️ (#10) |
| 20 | Browser end-to-end tests | Open (Playwright installed, unused) | ❔ |

---

## Original ToDo

| Item | State |
|---|---|
| FIX 1: Teutoburg Forest year | ✔️ |
| Fill up the database | ✔️ (about 19,000 events) |
| Mobile version | ✔️ |
| Map collections with notes, share and edit links | ✔️ |
| Delete entries | ✔️ |
| Marker clusters | ✔️ |
| Links to events | ✔️ |
| Create new tags | ✔️ (tag admin: create, rename, merge) |
| More refined tag selection | Covered by #11 of 25 Nov (📐) |
| Keyword filter ("Greece → everything about Greece") | ⏭️ with #7 of 25 Nov |
| Check date order before year 0 | Open |
