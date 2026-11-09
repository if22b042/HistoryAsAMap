# History As A Map (HAAM) — Findings

> **TL;DR**
> The codebase holds **two half-merged applications** (a live Flask + Jinja app and an unfinished REST API + Vite SPA) sharing **two incompatible database models** for the same tables. The most urgent problems:
> 1. **Production database passwords and a Vercel token are committed** in `.env.production` and pushed to GitHub → rotate them now.
> 2. **No access control in the live app:** anyone can edit any event, and nothing is moderated (the README's approval workflow is not wired in).
> 3. **Stored XSS:** event titles/descriptions are injected into the page with `innerHTML`.
> 4. **The REST backend doesn't start** with the current uncommitted `backend/app.py` (verified: `RuntimeError: ... not registered with this 'SQLAlchemy' instance`).
> 5. **Every new entry gets two Location rows**, and search on the map throws a JS error on each keystroke.
> 6. Year extraction misses all years 1–999 AD (the `ToDo` "Teutoburg Forest" bug) and often picks the wrong year.
>
> Counts: **6 critical, 13 high, 18 medium, 15 low/hygiene.** Each finding has an ID (F-nn), location, impact and a fix pointer; fixes are expanded in `IMPROVEMENTS.md`.

Severity scale: 🔴 Critical (security or data loss/corruption now) · 🟠 High (feature broken / wrong data) · 🟡 Medium (bug in edge cases, risk) · ⚪ Low (hygiene, dead code).

Method: every tracked file (77) plus the untracked `import_wikipedia_geosearch.py` and the uncommitted diffs were read; the local SQLite schema was inspected read-only; backend startup was run once against an in-memory DB. Environment-file **values were not read**, only the variable names.

---

## 1. Architecture overview (as found)

```
                 ┌──────────── Implementation A (live on Vercel) ────────────┐
api/index.py ──► frontend/app.py ──► backend/controllers/{CheckNewEntry,SaveEntry,LocationInfoRetriever}
                 │                   backend/api/WikiApi.py
                 │                   backend/models/model.py  (db #1, Location.coordinates "lat,lon")
                 └── frontend/templates/*.html  (Leaflet, noUiSlider, Tailwind CDN, inline JS)

                 ┌──────────── Implementation B (unfinished) ────────────────┐
backend/app.py ─► backend/routes/{events,admin}.py ─► backend/services/{events,wikipedia,geocoding}.py
                 │                                    backend/models/event.py (db #2 = extensions.db, Location.lat/lon, status)
                 └── frontend/src/js/*.js via Vite  (HTML entry files missing)
```

Both write to the same table names (`entries`, `locations`) with different columns. The local DB at `instance/yourdb.db` (93 entries) has drifted into a third shape: `entries` has `used`, `tag_ids`, `tags` but **no `status`**; `locations` has `coordinates NOT NULL` **and** `lat`, `lon`; stale `tags` and `entry_tags` tables remain from an earlier design.

---

## 2. 🔴 Critical

### F-01 Production secrets committed to Git
- **Where:** `.env.production` (tracked since commit `3972cab`, remote `github.com/if22b042/HistoryAsAMap`).
- **What:** contains `PGPASSWORD`, `POSTGRES_PASSWORD`, several `POSTGRES_URL*`/`DATABASE_URL*` connection strings, `VERCEL_OIDC_TOKEN`, Neon project id. `.gitignore` only excludes `.env`, `.env.local`, `.env.*.local`.
- **Impact:** anyone with repo access (public, if the repo is public) can read, modify or drop the production database.
- **Fix:** rotate the Neon/Postgres password and revoke the token *first*, then `git rm --cached .env.production`, add `.env*` (except `.env.example`) to `.gitignore`, and purge history (`git filter-repo`) if the repo was ever public.

### F-02 No authorisation on editing — anyone can overwrite any event
- **Where:** `frontend/app.py:262` (`/edit/<id>`), `frontend/app.py:341` (`/create_new_entry` with `existing_id`), `backend/controllers/SaveEntry.py:16-52`; Edit button rendered for everyone in `index.html:404`.
- **Impact:** vandalism of the whole dataset with a single form POST; `existing_id` is a hidden field, so any id can be targeted even without the UI. No history to roll back.
- **Fix:** require an admin session for edits; or route edits through a pending-revision queue.

### F-03 Moderation workflow not implemented in the live app
- **Where:** `backend/models/model.py` has no `status`; `frontend/app.py:247` shows `Entry.query.all()`.
- **Impact:** README/About promise "submitted for admin approval", but every submission is public instantly — combined with F-04 this is a direct XSS vector to all visitors.
- **Fix:** add `status` to the single model and filter the map to `approved` (see Improvements §1).

### F-04 Stored XSS through `innerHTML`
- **Where:** `index.html:374-381` (popup), `index.html:402-417` (sidebar: `${event.title}`, `${event.description}`, `href="${event.link}"`), `frontend/static/js/map.js:31-35`, `frontend/src/js/admin.js:37-52` (admin page — attacker reaches the admin's browser and the admin key in `localStorage`), `frontend/src/js/map.js:100,136`.
- **Impact:** a submitted/edited title such as `<img src=x onerror=...>` runs script for every visitor. Jinja autoescaping protects the cards, not these JS template strings.
- **Fix:** build DOM nodes with `textContent`, or escape before interpolation; validate links server-side to `https://en.wikipedia.org/wiki/…`; add a CSP.

### F-05 Uncommitted `backend/app.py` crashes on startup (REST API dead)
- **Where:** `backend/app.py:14` imports `Entry` from `backend.models.model` (its own unbound `SQLAlchemy()` instance) while the app initialises `backend.extensions.db`; `backend/app.py:224` calls `Entry.query.count()`.
- **Verified:** `RuntimeError: The current Flask app is not registered with this 'SQLAlchemy' instance`.
- **Impact:** implementation B, `scripts/reset_db.py`, `scripts/clear_database.py`, `scripts/display_db.py` all fail. Even if it started, `auto_import_wikipedia_entries` runs in a thread **without an app context** and builds `Location(coordinates=…)`, which doesn't exist in `event.py`.
- **Fix:** revert the diff or import from `backend.models.event`; push the import to a CLI command.

### F-06 Script named "display" drops the whole database
- **Where:** `displaydb.py:6-7` — `db.drop_all(); db.create_all()` before "displaying".
- **Impact:** running it (or with `DATABASE_URL` pointing at prod) deletes all data. Also `clear_database.py` and `scripts/clear_database.py` delete everything with no confirmation or environment check.
- **Fix:** delete `displaydb.py`; add `--yes` + environment guards to destructive scripts.

---

## 3. 🟠 High

### F-07 Every new entry gets two Location rows
- **Where:** `SaveEntry.py:76-92` already adds a `Location`; `frontend/app.py:411-419` adds a second one for new entries. Since `model.py:61` declares `entry_id unique=False` and the relationship is `uselist=False`, SQLAlchemy silently returns one of them.
- **Also:** if `SaveEntry` returns an *existing* entry (duplicate link, `SaveEntry.py:55-57`), the route still appends another Location to it.
- **Fix:** create the location in one place; make `entry_id` unique; dedupe existing rows.

### F-08 Map search throws on every keystroke
- **Where:** `index.html:618` — `(event.year || '').toLowerCase()`; `year` is emitted as a number by `tojson` (`index.html:242`).
- **Impact:** `TypeError: event.year.toLowerCase is not a function`; `applyAllFilters` aborts before updating markers and cards — search does nothing (cards don't filter either, the exception happens first).
- **Fix:** `String(event.year ?? '')`.

### F-09 Wrong event opened from popups and cards
- **Where:** `index.html:380` passes `index` from `filteredEvents` but `showEvent` (`:398`) reads `eventsData[index]`; cards call `showEventFromList({{ loop.index0 }})` (`:135`) where the loop index is over *all* entries, while `eventsData` skips entries without location (`:233-236`).
- **Impact:** after any filter, or if any entry lacks coordinates, "View Full Details" shows a different event.
- **Fix:** pass `event.id` and look it up in a `Map`.

### F-10 Year extraction misses years 1–999 AD and often picks the wrong year
- **Where:** `WikiApi.py:94` (and the copy in `services/wikipedia.py:63`): AD alternative only matches `1[0-9]\d{2}|20\d{2}` (1000–2099); the **first** match anywhere in the intro wins.
- **Examples:** *Battle of the Teutoburg Forest* (AD 9) → no year (the `ToDo` FIX 1); an intro mentioning "…the 1066 Norman conquest…" before the event year → wrong; "AD 9", "9 CE", "c. 300", "3rd century BC" unsupported; a number like "1500 soldiers" counts as a year; "BC" prefix-free articles like "In 480 BC" work, but "480–479 BC" yields −480 only by luck.
- **Fix:** see Improvements §3 (use Wikidata `P585`/`P580` point-in-time/start-time first, regex as fallback).

### F-11 Date-range parsing attaches an unrelated year
- **Where:** `WikiApi.py:76-82` — after matching "23 August – 2 February 1943", the year is taken from the first 4-digit number in the whole extract, not from the range; `\w+` also matches non-month words.
- **Fix:** capture the year inside the same regex; validate month names.

### F-12 Missing coordinates crash the save
- **Where:** `CheckNewEntry.py:62` only rejects when *both* coordinates **and** year are missing; preview renders empty lat/lon; `frontend/app.py:364` `float(request.form.get("lat"))` → `ValueError`/`TypeError` → HTTP 500. Same for a non-numeric year: stored as text in SQLite, error in PostgreSQL.
- **Fix:** reject when either is missing (as B does) and validate the form server-side with friendly errors.

### F-13 Preview form loses or corrupts data while editing
- **Where:** `submit_entry.html:696` clears the year when the user clicks Edit; `:701` switches *date* to `type="date"`, which (a) drops existing values like "23 August 1942", (b) cannot represent BC or years < 1000 in most browsers, (c) overwrites the date with `YYYY-01-01`. Title and description have no Edit button even though the info card says "You can edit any field".
- **Also:** hidden `wikiLink` (`:37`) uses `wiki_link`, which the route never passes.
- **Fix:** keep text inputs, add validation; add edit buttons for title/description.

### F-14 Two diverging data models on the same tables
- **Where:** `backend/models/model.py` vs `backend/models/event.py`.
- **Impact:** A writes `coordinates` (NOT NULL) and no `status`; B writes `lat`/`lon` and `status`. Against the current local DB, B fails with *no such column entries.status* and inserting a B `Location` violates `coordinates NOT NULL`. `index.html:234-235` contains Jinja workarounds to read either shape. `import_entries_from_csv.py` uses B, `import_wikipedia_geosearch.py` uses A.
- **Fix:** one model, with Alembic migrations (Improvements §1–2).

### F-15 Background import thread starts on every app import
- **Where:** `frontend/app.py:231-243` (module import time), duplicated in `backend/app.py:220-231`.
- **Impact:**
  - On Vercel each cold start of a function with < 100 rows spawns a thread that is frozen/killed mid-request; it never completes and burns Wikipedia/Neon quota.
  - Every script that does `from frontend.app import app` (≈10 scripts) also starts the import.
  - Several gunicorn workers race on the unique `wikiLink` → unhandled `IntegrityError` kills the thread (no rollback).
  - It ignores the moderation model and stores everything as `OTHER`, untagged.
- **Fix:** move to an explicit CLI command / scheduled job (Improvements §4).

### F-16 "Historical event" heuristic is both too strict and too loose
- **Where:** `is_historical_event` (three copies: `frontend/app.py:74`, `backend/app.py:22`, `import_wikipedia_geosearch.py:15`).
- **Too strict:** plain substring match rejects any intro containing "town", "city", "district", "residents", "located in the" — most battle articles ("fought near the town of…") are discarded.
- **Too loose:** "war" matches *Warsaw*, *toward*, *award*; "empire", "kingdom", "state", "peace", "strike", "creation" match buildings, schools, bridges, stadiums.
- **Fix:** use Wikidata `instance of` (P31) — battle (Q178561), siege, treaty, etc. — instead of keywords.

### F-17 No CSRF protection, no rate limiting
- **Where:** all POST routes in `frontend/app.py`; no `SECRET_KEY` set at all (so `flash()`, used by `new_entry.html:29`, can't work either).
- **Impact:** a third-party page can make visitors' browsers submit/overwrite entries; the preview endpoint triggers 1–3 outbound API calls per request with no throttling (abuse amplifies to Wikipedia/Nominatim).
- **Fix:** Flask-WTF CSRF, `SECRET_KEY` from env, Flask-Limiter.

### F-18 Hard-coded weak admin key and permissive CORS (B)
- **Where:** `backend/config.py:13` default `dev-admin-key` (also printed in README); `config.py:14-17` defaults CORS to `*`; key compared with `!=` (timing) and stored in `localStorage` (`admin.js:22-27`) where F-04 can read it.
- **Fix:** no default (fail fast), `hmac.compare_digest`, real session auth.

### F-19 Vite frontend (B) cannot build
- **Where:** `vite.config.js:9-13` references `index.html`, `add-event.html`, `preview.html`, `admin.html`, `about.html` — none exist; `admin.js:3` imports missing `../css/admin.css`; `preview.js:97` sends `tag_ids` (ids are list positions) but the API stores `payload["tags"]` (names).
- **Impact:** `npm run build` fails; admin UI unusable.

---

## 4. 🟡 Medium

| ID | Finding | Location |
|---|---|---|
| F-20 | Year slider crashes with zero events (`Math.min()` = `Infinity`) and noUiSlider throws when `minYear == maxYear` (a single event). | `index.html:452-466` |
| F-21 | Events at latitude or longitude exactly 0 are hidden (`{% if lat and lon %}`); same truthiness bug in `WikiApi.py:104,110`, `frontend/app.py`/`backend/app.py` auto-import (`not wiki_data.get("lat")`). | `index.html:236` |
| F-22 | Duplicate detection uses the raw URL string: `Battle_of_Verdun`, `Battle of Verdun`, percent-encoded, `#History`, `?oldid=`, `en.m.wikipedia.org`, redirects all create separate entries. | `CheckNewEntry.py:26`, `services/events.py:26` |
| F-23 | Inconsistent URL validation: `WIKIPEDIA_REGEX` in `frontend/app.py:14` accepts any language, then `CheckEntry` rejects non-English; also accepts `http`/query strings/anchors. | `frontend/app.py:14,305` |
| F-24 | Every Wikipedia call sleeps 1 s inside the request (`time.sleep(1)`), then Nominatim + onwater are called synchronously (10 s timeout each) → a submission can take ~20 s and block a worker; on Vercel this risks function timeouts. | `WikiApi.py:40`, `frontend/app.py:395-396` |
| F-25 | onwater.io v1 endpoint now requires an API key; errors silently produce `on_water=False`. Nominatim UA `"YourApp/1.0"` violates its usage policy and may get blocked. | `LocationInfoRetriever.py:12,26` |
| F-26 | Wikipedia User-Agent uses placeholder contact (`yourusername`, `your.email@example.com`) — violates the Wikimedia UA policy; risk of being blocked. | `WikiApi.py:33`, `frontend/app.py:60`, `backend/app.py:92` |
| F-27 | Verbose DEBUG logging configured globally on import (`logging.basicConfig(level=DEBUG)` in two modules) logs full request headers, response headers and page payloads; `print("DEBUG …")` dumps full form data. | `WikiApi.py:10,49,60,117`, `CheckNewEntry.py:9`, `frontend/app.py:301-303,347-355` |
| F-28 | `sys.stdout.reconfigure()` at import time in a library module; fails/misbehaves under some WSGI servers where stdout isn't a TextIOWrapper. | `WikiApi.py:7` |
| F-29 | Unhandled `IntegrityError` races: duplicate check then insert is not atomic (two users submitting the same link → 500). | `SaveEntry.py`, `services/events.py:61-118` |
| F-30 | `Entry.year` is `nullable=False`, but the CSV importer sets `None` when empty → crash; auto-import also converts failures to `None`. | `import_entries_from_csv.py:52`, `frontend/app.py:190-193` |
| F-31 | `entries_template.csv` is malformed: header has 11 columns, rows have 13 (unquoted commas in tags and dates), category column contains "19th century". | `entries_template.csv` |
| F-32 | `/api/tags` re-imports Python source on each call by mutating `sys.path` (adds a path each request); tag "ids" are list indices that change when the list is edited; tags stored on entries are free-text names with no referential integrity; duplicate "Yuan Dynasty". | `frontend/app.py:424-467`, `routes/events.py:78-119`, `add_tags.py` |
| F-33 | `scripts/populate_tags.py` stores BC periods as **positive** years (e.g. Egyptian New Kingdom 1550→1077, start > end) and imports a `Tag` model that no longer exists; same for `check_tags.py`, `test_tags_api.py`, `scripts/check_tags.py`, `scripts/add_tag_dates_columns.py`. | `scripts/populate_tags.py:10-…` |
| F-34 | Migration endpoint `/run-migration` would allow unauthenticated DDL if registered; uses `information_schema` (Postgres-only). `scripts/migrate_production_db.py` needs `psycopg2` and `python-dotenv`, neither in `requirements.txt` (which has `psycopg` v3). | `routes/migration.py`, `scripts/migrate_production_db.py:6-8` |
| F-35 | Heatmap: first toggle ignores search/tag filters; `btn.textContent = …` removes the icon; mobile slider updates the desktop one, not vice versa (desktop changes leave mobile stale). | `index.html:300-350,496-503` |
| F-36 | All events are serialised into the HTML on every page view and the whole marker cluster is rebuilt on every slider "update" tick (fires continuously while dragging) → slow with thousands of events. | `index.html:231-252,471-477,637` |
| F-37 | Category `select` is disabled on load when pre-selected; works only because the submit handler re-enables it — fragile; if JS fails, the field is not submitted and the server returns "category is required" with the user's work lost. | `submit_entry.html:794`, `frontend/app.py:357-362` |

---

## 5. ⚪ Low / hygiene

| ID | Finding | Location |
|---|---|---|
| F-38 | Dead or broken modules: `backend/controllers/add_new_entry.py` (imports non-existent `web_scrape`, reads stdin), `backend/test.py` and its copy `backend/tempCodeRunnerFile.py`, `backend/package.json` (Express/Mongoose — unused Node backend), `temp_endblock.txt` (UTF-16 junk), `debug_form.py`, `fix_category_column.py` (points at `frontend/instance/yourdb.db`). | various |
| F-39 | Code duplication: `get_wikipedia_data` ×2, `reverse_geocode`/`check_on_water` ×2, `is_historical_event`/`geosearch_wikipedia`/`auto_import_*` ×3, `format_year` ×7 (Python + JS), tags endpoint ×2, clear/display scripts ×2. | repo-wide |
| F-40 | `new_entry.html:543-545` has a `<script>` after `{% endblock %}` — never rendered. | `new_entry.html` |
| F-41 | `base.html` loads the **Tailwind Play CDN** (`cdn.tailwindcss.com`), which Tailwind says is not for production (runtime JIT, large, no purge); combined with ~3,000 lines of hand-written CSS doing the same job (`global.css`, `map.css`, per-template `<style>` blocks). Five unpinned CDNs, no SRI hashes. | `base.html:8-9`, `index.html:191-199` |
| F-42 | `base.html:304-306` hides **every** `<nav>` element globally ("Remove old nav styles") — the menu works only because it's styled via `.nav-menu`; any future `<nav>` vanishes. | `base.html` |
| F-43 | `dark-mode.js` prints ~10 `console.log`s per page; theme applied after first paint (flash of light theme) because the script is at end of `<body>`. | `dark-mode.js` |
| F-44 | Accessibility: event cards and tag pills are clickable `div`s (no keyboard focus), hamburger is a `div`, dark-mode button has no accessible name besides `title`, gradient text with `text-transparent` fails contrast in some themes. | `index.html`, `base.html`, `submit_entry.html` |
| F-45 | Footer claims "© 2025 … All rights reserved." while content is CC BY-SA Wikipedia text; no CC BY-SA attribution/licence notice. | `base.html:117` |
| F-46 | `debug=True` in both `app.run()` calls; harmless on Vercel but dangerous if someone runs it on a server (Werkzeug debugger = RCE). | `frontend/app.py:471`, `backend/app.py:238` |
| F-47 | `Entry.query.get()` is deprecated in SQLAlchemy 2.x (`db.session.get`). | `SaveEntry.py:17`, `services/events.py:151,168,181`, `frontend/app.py:264` |
| F-48 | `tags: Mapped[dict]` but stores a list; `Location` columns typed loosely; no `created_at`/`updated_at`, no submitter or audit trail. | models |
| F-49 | `requirements.txt` uses only lower bounds (`>=`), no lockfile; `package-lock.json` is git-ignored → non-reproducible builds. | `requirements.txt`, `.gitignore:45` |
| F-50 | No tests at all (no pytest, no JS tests, no CI). README's "Database Migration" section says "create a script" — there is none that works against the current model. | repo |
| F-51 | Git hygiene: commit messages like "Did a lot of stuff", author `Your Name <youremail@example.com>`, `ToDo` ends with "asdf", `__pycache__`/`instance` dirs inside `frontend/`. | history |
| F-52 | README is out of date: says SQLAlchemy + SQLite + Vite dev server architecture and admin workflow, but the deployed app is `frontend/app.py`; endpoints table omits `/api/tags`; `ADMIN_API_KEY` env documented but irrelevant to the live app. | `README.md` |

---

## 6. Things that work well

- Clear product idea and pleasant UI: clustered, colour-coded markers, combined filters, heatmap, dark mode, mobile layout.
- Implementation B's **layering** (routes → services → models, `EventServiceError` with status codes, English-URL validator) is a good foundation; it validates input properly and implements the moderation states.
- Jinja autoescaping is used for card content and `|tojson` for inlined data (prevents the `</script>` breakout).
- Rich curated tag catalogue (341 periods with year ranges) — valuable domain data.
- Rate-limit awareness (sleeps) and timeouts on all outbound HTTP calls.
- BC years are consistently modelled as negative integers, and display formatting handles them.
