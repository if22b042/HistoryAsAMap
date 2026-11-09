# History As A Map (HAAM) — Improvements

> **TL;DR**
> Work in this order:
> **(0) Today:** rotate the leaked DB password/token and remove `.env.production` from Git; hide the public Edit route; escape all `innerHTML`.
> **(1) Consolidate:** keep *one* backend (the layered REST design in `backend/routes|services`), *one* SQLAlchemy model with `status` and `lat`/`lon`, and *one* frontend; delete the duplicates and dead scripts; add Alembic migrations.
> **(2) Fix data quality:** take dates, coordinates and "is this an event?" from **Wikidata** instead of regexes/keywords; normalise Wikipedia URLs; move tags into the database.
> **(3) Make it production-grade:** real admin auth, CSRF, rate limiting, a CLI/scheduled importer instead of the import thread, server-side filtering with a bbox/time API, tests + CI.
> **(4) Then build features:** delete/restore, revision history, time-lapse playback, smarter tag search, and **map collections** via capability links.
> Each item says which findings (F-nn in `FINDINGS.md`) and requirements (FR/NFR in `REQUIREMENTS.md`) it resolves, plus a rough effort (S ≤ ½ day, M ≤ 2 days, L > 2 days).

---

## Priority 0 — Immediate (security hot-fixes)

| # | Action | Fixes | Effort |
|---|---|---|---|
| 0.1 | **Rotate** the Neon/Postgres password and revoke `VERCEL_OIDC_TOKEN`, *then* `git rm --cached .env.production`, extend `.gitignore` with `.env*` + `!.env.example`, and purge history with `git filter-repo --path .env.production --invert-paths` (force-push; collaborators re-clone). Keep secrets only in Vercel → Environment Variables. | F-01, NFR-4 | S |
| 0.2 | Remove the **Edit** button and protect `/edit/<id>` and the `existing_id` path of `/create_new_entry` behind an admin check (even a temporary env-based password with `hmac.compare_digest` is better than nothing). | F-02 | S |
| 0.3 | Replace all template-string `innerHTML` with DOM building + `textContent` (or a tiny `escapeHtml` helper) in `index.html`, `static/js/map.js`, `src/js/*.js`. Only allow `href` values that start with `https://en.wikipedia.org/wiki/`. Add a Content-Security-Policy header (`script-src 'self'` + the pinned CDNs). | F-04, NFR-3 | S |
| 0.4 | Delete `displaydb.py`; add an `--i-know-what-im-doing` flag and refuse to run destructive scripts when `DATABASE_URL` isn't SQLite. | F-06 | S |
| 0.5 | Revert the uncommitted `backend/app.py` import-thread change (or import `Entry` from `backend.models.event`). | F-05 | S |
| 0.6 | Set `SECRET_KEY` from env; enable Flask-WTF `CSRFProtect`; never run with `debug=True` outside local dev. | F-17, F-46 | S |

---

## Priority 1 — Consolidate the architecture

### 1.1 Pick one backend and one frontend
The layered REST design (B) is the better base: thin routes, a service layer, proper validation, moderation states. Recommended target:

```
backend/
  app.py            create_app(), registers blueprints, no side effects on import
  config.py         Dev/Prod/Test configs; fail fast if ADMIN creds/SECRET_KEY missing in prod
  extensions.py     db, migrate, limiter, csrf
  models/           entry.py, location.py, tag.py, revision.py   (ONE set)
  services/         wikipedia.py, wikidata.py, geocoding.py, events.py, importer.py
  routes/           public.py (HTML pages), api.py (JSON), admin.py
  cli.py            flask haam import-region / import-list / import-csv / seed-tags
  templates/        Jinja pages (keep the current, nice-looking ones)
  static/           built JS/CSS
migrations/         Alembic (Flask-Migrate)
tests/
```

Frontend: either keep **server-rendered Jinja + small JS modules** (simplest; works on Vercel today) *or* finish the Vite SPA — not both. For a bachelor-thesis timeline, Jinja + ES modules bundled by Vite (`build.outDir = backend/static/dist`) gives the existing UI with a real build, no Tailwind Play CDN and pinned dependencies. Fixes F-14, F-19, F-39, F-41, NFR-12.

### 1.2 One data model

```python
class Entry(db.Model):
    id, title (str, not null), year (int, not null), date_label (str), date_precision (enum: day|month|year|decade|century)
    end_year (int, null)              # for multi-year events → enables "show what was happening in 1916"
    summary (text), wiki_url (unique, canonical), wiki_page_id (int, unique), wikidata_qid (str, unique)
    category (enum), status (enum pending|approved|rejected, index), modified (bool)
    created_at, updated_at, submitted_by (nullable), reviewed_by (nullable)
    location (1:1, unique FK, cascade delete)
    tags (M:N via entry_tags)

class Location(db.Model):  lat (float, not null), lon (float, not null), country, on_water, entry_id UNIQUE
class Tag(db.Model):        id, name (unique), slug, start_year, end_year, aliases (JSON), parent_id (for hierarchy)
class Revision(db.Model):   entry_id, changed_fields (JSON), before (JSON), after (JSON), author, created_at, status
```

- Drop `coordinates` string and `used`. Store `wiki_page_id`/`wikidata_qid` for duplicate detection independent of URL spelling (F-22).
- Add indexes on `(status, year)` and `category`.
- Fixes F-07 (unique `entry_id`), F-14, F-29 (catch `IntegrityError` → 409), F-30, F-32, F-48, DR-1…DR-5.

### 1.3 Real migrations
Introduce **Flask-Migrate/Alembic**. First migration: reconcile the current production schema (copy `coordinates` → `lat/lon` where null, dedupe Locations keeping the lowest id, add `status` defaulting existing rows to `approved`, move JSON tag names into `entry_tags`). Delete `routes/migration.py`, `fix_category_column.py`, `scripts/add_*_column.py`, `scripts/migrate_production_db.py`. Fixes F-34, NFR-8, NFR-9.

### 1.4 Clean the repository
Delete: `backend/controllers/` (after porting), `backend/api/WikiApi.py` (replaced by `services/wikipedia.py`), `backend/models/model.py`, `backend/test.py`, `backend/tempCodeRunnerFile.py`, `backend/package.json`, `temp_endblock.txt`, `debug_form.py`, `check_tags.py`, `test_tags_api.py`, the duplicated root vs. `scripts/` utilities, `frontend/static/js/map.js` (unused), `frontend/instance/`. Fix the `ToDo` file into GitHub issues. Fixes F-38, F-39, F-51.

---

## Priority 2 — Data quality (the core of the product)

### 2.1 Use Wikidata for structured facts
Every English Wikipedia article maps to a Wikidata item (`prop=pageprops&ppprop=wikibase_item`). Query it for:

| Property | Use |
|---|---|
| `P585` point in time · `P580` start time · `P582` end time | exact year/date **with precision**, BC handled natively (negative years in ISO form `-0480-…`) |
| `P625` coordinate location | coordinates when the article has none, or as a cross-check |
| `P31` instance of (+ `P279*` subclass of) | decide "is this a historical event?" (battle Q178561, siege Q188055, treaty Q131569, revolution Q10931, massacre Q3199915, …) → replaces keyword heuristics |
| `P17` country · `P276` location | country without calling Nominatim |
| `P361` part of | auto-suggest tags (e.g. "part of World War I") |

Keep the regex parser only as a fallback, and improve it:
- Support years 1–999 and the "AD 9", "9 CE", "c. 300 BC", "480–479 BC", "3rd century BC" forms (F-10, ToDo FIX 1).
- Look for the year **near the first date phrase** in the first sentence, not anywhere in the intro; take the year *from* a matched range (F-11).
- Return a confidence score; the preview highlights low-confidence fields for the contributor.
- Cover with a parametrised test suite of ~50 real intros (Teutoburg, Thermopylae, Hastings, Verdun, Stalingrad, Treaty of Westphalia…). FR-22, FR-23, FR-50.

### 2.2 Canonicalise URLs
Resolve the title via the API (`redirects=1`), store canonical `https://en.wikipedia.org/wiki/<Title_With_Underscores>` + `pageid`; accept `en.m.wikipedia.org`, `http`, percent-encoding, fragments, `?oldid=` on input. Reject other languages with a single consistent validator. Fixes F-22, F-23, FR-20, FR-29.

### 2.3 Tags in the database
Seed `tags` from `add_tags.py` via `flask haam seed-tags` (fix the duplicate "Yuan Dynasty", fix positive BC years from `populate_tags.py`). Use stable ids/slugs; validate submitted tags against the table. Then:
- **Auto-suggest** tags whose `[start_year, end_year]` contains the event year and whose name/aliases appear in the intro or in Wikidata `P361` (FR-35).
- **Keyword/alias search** for filters, e.g. tag "Ancient Greece" with aliases ["Greece", "Hellenic", "Athens", "Sparta"]; or hierarchical tags (`parent_id`) so "Greece" includes all children (FR-15).
- Admin UI to create/merge tags (FR-34).

### 2.4 Geocoding
Prefer Wikidata `P17`. If Nominatim stays: real User-Agent with contact e-mail, max 1 req/s, cache results. Replace onwater.io (now key-only) with a local land-polygon check (Natural Earth + `shapely`) or drop `on_water` if unused. Fixes F-25, F-26, NFR-6.

---

## Priority 3 — Production readiness

### 3.1 Authentication and moderation
- Admin login with a hashed password (Flask-Login or a single env-configured account) and session cookies (`Secure`, `HttpOnly`, `SameSite=Lax`), instead of an API key in `localStorage`. Fixes F-18.
- Submissions → `pending`; public pages show only `approved` (F-03, FR-36).
- Edits by the public create a **Revision** awaiting approval instead of overwriting (F-02, FR-38); admin page lists pending entries and revisions with a diff view (FR-37).
- Delete = soft delete (`status=removed`) with restore (FR-39).

### 3.2 Abuse protection
Flask-Limiter on `/preview` and submit (e.g. 10/min/IP); honeypot field or Cloudflare Turnstile on the submit form; cap description length; log moderation actions. Fixes F-17.

### 3.3 Importer as a job, not a thread
Move the geosearch import to `flask haam import-region …` (and optionally a Vercel Cron / GitHub Action that calls a protected endpoint which processes a small batch per run). Make it idempotent (upsert on `wiki_page_id`), resumable (store grid progress), and insert as `pending` or `approved` by flag. Use the Wikidata `P31` filter. Remove the import-on-startup code from both apps. Fixes F-15, F-16, FR-40.

### 3.4 Faster, non-blocking requests
- Drop the unconditional `time.sleep(1)` per request; rely on a shared `requests.Session` with retries/back-off (`urllib3.Retry`, honour `Retry-After`) and an in-process/DB cache of Wikipedia responses (F-24).
- Do geocoding asynchronously after approval or in the importer, not in the submit request.

### 3.5 Scalable map API
- `GET /api/events?bbox=…&year_from=…&year_to=…&category=…&tag=…&q=…&limit=…` returning compact GeoJSON; the page fetches instead of inlining all rows into HTML.
- Debounce slider (`'change'` or `set` + 150 ms debounce) and search input; update the cluster layer with `clearLayers()`/`addLayers()` (chunked loading) rather than recreating it.
- For many thousands of events, consider Supercluster or vector tiles. Fixes F-36, NFR-7.
- Full-text search in Postgres (`tsvector`) for `q`.

### 3.6 Logging and configuration
Configure logging once in `create_app` (INFO in prod), remove all `print`/DEBUG dumps of headers and form data, remove `sys.stdout.reconfigure`. Validate config at startup. Fixes F-27, F-28, NFR-13.

### 3.7 Tests and CI
- **pytest**: date parser cases, URL canonicaliser, service layer (create/approve/reject/duplicate/race), API contract tests with an in-memory DB, Wikipedia/Wikidata mocked with `responses`.
- **Playwright** smoke test: load map, filter by year/category/search, open details, submit a preview.
- GitHub Actions: `ruff`, `black --check`, `pytest`, `npm run build`. Pin dependencies (`pip-tools`/`uv lock`, commit `package-lock.json`). Fixes F-49, F-50, NFR-12.

### 3.8 Frontend hygiene
- Bundle Leaflet, markercluster, heat, noUiSlider via Vite (already in `package.json`); remove the Tailwind Play CDN or switch to a compiled Tailwind build — pick one styling system; pin versions + SRI for anything left on CDNs (F-41).
- Move inline `<style>`/`<script>` blocks into files; one shared `formatYear` (F-39).
- Remove the global `nav { display:none }` (F-42); load the theme script in `<head>` to avoid the light flash; drop console logs (F-43).
- Accessibility: `<button>`/`<a>` for clickable cards, pills and hamburger, `aria-label`s, focus styles, contrast check (F-44, NFR-11).

### 3.9 Quick bug fixes (each S)
| Fix | Finding |
|---|---|
| Create the Location in exactly one place; dedupe existing rows. | F-07 |
| `String(event.year ?? '')` in search. | F-08 |
| Pass `event.id` to `showEvent`, look up in a `Map`; cards use `entry.id`. | F-09 |
| Reject when lat/lon **or** year missing; validate/convert form fields with friendly errors. | F-12 |
| Don't clear year on edit; keep date as text; add edit buttons for title/description; pass `wiki_link`. | F-13 |
| Guard empty/single-event datasets in the slider (`range: {min, max: max === min ? min + 1 : max}`). | F-20 |
| Use `is not None` checks for coordinates everywhere. | F-21 |
| Heatmap uses `applyAllFilters` result; keep icon (`innerHTML` with static markup or toggle a span); two-way slider sync with a re-entrancy guard. | F-35 |
| Don't disable the category select; use `readonly`-like styling or validate server-side. | F-37 |
| Fix `entries_template.csv` (quote fields; columns: wikiLink,title,year,date,first_paragraph,category,tags,lat,lon). | F-31 |
| Replace `Query.get` with `db.session.get`. | F-47 |

### 3.10 Documentation and licensing
Rewrite the README to match the chosen architecture (setup, `flask db upgrade`, CLI commands, env vars, deploy). Add "Text from Wikipedia, CC BY-SA 4.0" with per-event source link and licence notice in the footer/detail view; correct the copyright line. Fixes F-45, F-52, NFR-14.

---

## Priority 4 — Features (after the foundation is solid)

### 4.1 Map collections without login (ToDo FR-48/FR-49)
The "two links" idea is a sound, well-known pattern (*capability URLs*, like unlisted Google Docs or Excalidraw share links) if done carefully:
- On creation generate two random tokens with `secrets.token_urlsafe(32)` (≥ 256 bits): `view_token` and `edit_token`. Store **only a hash** of the edit token (SHA-256 is fine for high-entropy tokens) so a DB leak doesn't grant edit rights.
- URLs: `/c/<view_token>` (read-only) and `/c/<view_token>/edit#<edit_token>` — putting the edit token in the **fragment** keeps it out of server logs, `Referer` headers and analytics; JS sends it in a header.
- Send `Referrer-Policy: no-referrer` and `noindex` on collection pages; allow "regenerate links" (revokes old tokens).
- Make it clear in the UI that losing the edit link means losing edit access; optional "e-mail me the links" (only then do you store an e-mail).
- Data model: `Collection(id, title, notes, view_token, edit_token_hash, is_public, created_at)`, `CollectionItem(collection_id, entry_id, note, position)`.
- Features: filter map to a collection, per-event notes, ordered "story mode" that flies from event to event, export as GeoJSON/CSV, publish to a public gallery (moderated).

### 4.2 Time dimension
- **Play button / time-lapse:** animate the year window across history (e.g. 25-year window), markers fade in/out.
- Use `end_year` to show *ongoing* events and period tags as bands on a timeline under the map (vis-timeline or a small custom SVG).
- Non-linear slider scale (piecewise: −10000…−1000 compressed, 1000…2025 expanded) — with the current linear scale, 95 % of events sit in the last 5 % of the slider.
- Historical borders overlay for the selected year (e.g. open data from the *historical-basemaps* project) — a strong thesis feature.

### 4.3 Map UX
- Category-coloured clusters (pie-chart cluster icons) instead of the default blue/yellow (ToDo "multiple map icons will look terrible").
- Spiderfy identical coordinates (many events in one city); small jitter for exact duplicates.
- Deep links: `/?event=123&year=1914-1918&cat=military` so views are shareable.
- "Events near me" / search by place (geocode a place name, fit bounds).
- Show the article thumbnail (`prop=pageimages`) in the sidebar.

### 4.4 Content growth (ToDo "Fill up db")
- Seed from curated Wikipedia lists/categories (e.g. *List of battles*, *Category:Treaties*) via Wikidata SPARQL: all items with `P31/P279* battle` and `P625` and `P585|P580` → tens of thousands of high-quality events in one query, imported as `pending` or bulk-approved.
- Expand categories beyond five (political, religious, cultural, economic, disaster, exploration) or derive them from Wikidata classes.

### 4.5 Community and quality
- "Report a problem" on each event → creates a revision/flag for moderators.
- Contributor attribution (optional nickname), contribution counts.
- Admin dashboard: pending queue, low-confidence extractions, events missing tags, duplicates by `wikidata_qid`.

### 4.6 Internationalisation (later)
Since Wikidata is language-neutral, titles/summaries in other languages can be fetched by sitelink — the "English only" rule can be relaxed for *display* while keeping one canonical item per event.

---

## Suggested roadmap

| Week | Deliverable |
|---|---|
| 1 | Priority 0 complete; quick bug fixes (§3.9) on the live app. |
| 2–3 | Single model + Alembic migration of production data; repo cleanup; one backend/frontend. |
| 4 | Wikidata-based extraction + URL canonicalisation + tests for the date parser. |
| 5 | Admin login, moderation queue, revisions, soft delete; CSRF + rate limits. |
| 6 | Importer CLI / cron, tags in DB with auto-suggest; map API with bbox + debounce. |
| 7+ | Collections with capability links, time-lapse, historical borders. |
