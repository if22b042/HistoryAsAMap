# History As A Map (HAAM) — Requirements

> **TL;DR**
> HAAM is a web app that puts historical events from **English Wikipedia** on an interactive world map you can filter by **year, category, tag and free text**. Users paste a Wikipedia URL, the system pulls title / coordinates / year / intro paragraph, the user reviews and corrects it, and the event is stored. The README describes an **admin approval workflow** (pending → approved/rejected) that exists only in the unfinished REST backend + Vite frontend; the version actually deployed (Flask + Jinja templates, `frontend/app.py`) **publishes submissions immediately and lets anyone edit any entry**.
> This document lists every requirement found in the code, README, `ToDo` and UI copy, with an ID and its **status**: ✅ done, 🟡 partial/buggy, ❌ missing.
> Biggest gaps: moderation/admin (❌ in the live app), security of edits (❌), correct year extraction for years 1–999 AD (🟡), tag management (🟡), deleting entries (❌), personal map collections (❌).

---

## 1. Context and scope

| Item | Value |
|---|---|
| Product name | History As A Map (HAAM) |
| Goal (from `about.html`) | Show history spatially instead of as text/timelines, so connections across geography and time are easier to see |
| Data source | English Wikipedia only (MediaWiki Action API: `prop=coordinates|extracts`, `list=geosearch`) |
| Ancillary services | OpenStreetMap tiles, Nominatim reverse geocoding (country), onwater.io (land/water check) |
| Deployment target | Vercel (Python serverless, `api/index.py` → `frontend.app`) with Neon/Vercel PostgreSQL; SQLite locally |
| Users | Anonymous visitors (browse), contributors (submit/edit), administrators (moderate; only in the REST variant) |

There are **two parallel implementations** in the repository; requirements below apply to the product, and the *Status* column says which implementation meets them:

- **A — Server-rendered app (live):** `frontend/app.py`, `frontend/templates/*`, `backend/controllers/*`, `backend/models/model.py`, `backend/api/WikiApi.py`.
- **B — REST API + Vite SPA (unfinished):** `backend/app.py`, `backend/routes/*`, `backend/services/*`, `backend/models/event.py`, `frontend/src/*`.

---

## 2. Stakeholders and roles

| ID | Role | Description |
|---|---|---|
| R-1 | Visitor | Browses the map and event list without logging in. |
| R-2 | Contributor | Submits a new event from a Wikipedia URL and corrects extracted data. |
| R-3 | Administrator | Reviews pending submissions and approves/rejects them (README, `backend/routes/admin.py`). |
| R-4 | Maintainer | Runs import/migration/maintenance scripts (`scripts/`, root `*.py`). |

---

## 3. Functional requirements

### 3.1 Map and visualisation

| ID | Requirement | Source | Status |
|---|---|---|---|
| FR-1 | Show an interactive world map (Leaflet + OSM tiles), zoom 2–18, world-copy jump, bounded panning. | `index.html` | ✅ A |
| FR-2 | Show one marker per event at its coordinates. | `index.html` | ✅ A (🟡 events at lat/lon = 0 are dropped) |
| FR-3 | Colour markers by category (military red, diplomatic blue, naval dark blue, scientific green, other grey). | `index.html` | ✅ A |
| FR-4 | Cluster nearby markers so the map is not "a massive cluster of all blue points". | `ToDo` REQ 1, `leaflet.markercluster` | 🟡 A — clustering exists; ToDo still lists "multiple map icons will look terrible" |
| FR-5 | Optional heatmap layer that respects the active filters. | `index.html` `toggleHeatmap` | 🟡 A — ignores search and tag filters on first toggle; button loses its icon |
| FR-6 | Marker popup with title, formatted year, truncated description and "View full details". | `index.html` | 🟡 A — "details" opens the wrong event once filters are active |
| FR-7 | Detail sidebar with year, title, coordinates, full description, Wikipedia link, Google Maps link and Edit button. | `index.html` `showEvent` | 🟡 A — index mismatch, see Findings |
| FR-8 | Clicking an event card in the list opens its details and scrolls to the map. | `index.html` `showEventFromList` | 🟡 A — wrong event if any entry lacks a location |

### 3.2 Filtering and search

| ID | Requirement | Source | Status |
|---|---|---|---|
| FR-9 | Filter by year range with a dual slider covering min…max year in the data; BC shown as "N BC". | `index.html` | ✅ A (🟡 crashes when there are 0 events) |
| FR-10 | Filter by category (All / Military / Diplomatic / Naval / Scientific / Other). | `index.html`, `EventCategory` | ✅ A |
| FR-11 | Free-text search over title, description, year, category; updates map and list. | `index.html` | 🟡 A — throws a TypeError on every keystroke (numeric year), so the map is not filtered |
| FR-12 | Filter by historical tag (dropdown populated from `/api/tags`). | `index.html` | ✅ A |
| FR-13 | All filters combine (AND) and update both markers and list cards. | `applyAllFilters` | 🟡 A (see FR-11) |
| FR-14 | Server-side filtering by `year_from`, `year_to`, `category`. | `GET /api/events` | ✅ B only |
| FR-15 | Tag filtering should be "smarter": keyword-based (e.g. "Greece" returns everything related to Greece). | `ToDo` Tags | ❌ |

### 3.3 Event list

| ID | Requirement | Source | Status |
|---|---|---|---|
| FR-16 | Below the map, show all events as cards (year, category, title, description, tags, "Read more"). | `index.html` | ✅ A |
| FR-17 | Floating "View All Events" button visible only while the map is in view. | `index.html` | ✅ A |
| FR-18 | List sorted chronologically. | B: `order_by(Entry.year)` | 🟡 A uses `Entry.query.all()` (insertion order); B sorts |

### 3.4 Submitting an event

| ID | Requirement | Source | Status |
|---|---|---|---|
| FR-19 | Contributor enters a Wikipedia URL and picks a category (required). | `new_entry.html` | ✅ A, B |
| FR-20 | Accept **English Wikipedia** URLs only (`https://en.wikipedia.org/wiki/...`). | `validators.py`, README | 🟡 A — the first regex allows any 2-letter language, a second check then rejects; mobile/percent-encoded/fragment URLs are not normalised |
| FR-21 | Fetch title, coordinates, intro paragraph, date string and year from the Wikipedia API. | `WikiApi.py`, `services/wikipedia.py` | 🟡 — see FR-22/23 |
| FR-22 | Extract the event **year**, including BC/BCE years (stored as negative integers). | `WikiApi.py` | 🟡 — AD years 1–999 are never found (ToDo FIX 1: Teutoburg Forest, AD 9); first year anywhere in the intro wins |
| FR-23 | Extract a human-readable **date string** (single date or the start of a date range). | `WikiApi.py` | 🟡 — the range year comes from the first 4-digit number in the text, not the range |
| FR-24 | Reject articles without coordinates or without an extractable year. | `services/events.py` | 🟡 A rejects only when *both* are missing, then crashes on save if coordinates are missing |
| FR-25 | Show a preview where the user can review and **edit** year, date, category, latitude, longitude and tags. | `submit_entry.html` | 🟡 — title and description cannot be edited; editing year wipes it; editing date switches to a date picker that cannot hold BC/early dates |
| FR-26 | Track whether the user changed extracted data (`modified` flag). | `submit_entry.html`, model | ✅ |
| FR-27 | Year is mandatory for every entry. | `SaveEntry.py` | ✅ (not type-checked) |
| FR-28 | Enrich saved locations with country (reverse geocoding) and on-water flag. | `LocationInfoRetriever.py`, `services/geocoding.py` | 🟡 — onwater.io needs an API key now; failures default to `False` without notice |
| FR-29 | Detect duplicates by Wikipedia link; offer to edit the existing entry. | `CheckNewEntry.py` | 🟡 — compares raw URL strings only |
| FR-30 | Help tooltip: for multi-year events enter the first year. | `submit_entry.html` | ✅ |

### 3.5 Tags

| ID | Requirement | Source | Status |
|---|---|---|---|
| FR-31 | A curated list of historical periods/conflicts with start/end years (`None` = ongoing). | `add_tags.py` (341 tags) | ✅ (one duplicate: "Yuan Dynasty") |
| FR-32 | `GET /api/tags` returns tags with id, name, years, display date, sorted by mid-point year. | `frontend/app.py`, `routes/events.py` | ✅ (ids are list positions, not stable) |
| FR-33 | Contributor can search and multi-select tags during preview. | `submit_entry.html` | ✅ A (B sends `tag_ids`, which the API ignores) |
| FR-34 | Users can create new tags. | `ToDo` | ❌ |
| FR-35 | Tags are suggested/auto-assigned from the event year. | implied by tag year ranges | ❌ |

### 3.6 Editing, moderation, deletion

| ID | Requirement | Source | Status |
|---|---|---|---|
| FR-36 | Submissions are stored as **pending** and appear on the map only after admin approval. | README "Workflow" | ❌ A (published immediately); ✅ B (API only) |
| FR-37 | Admin can list pending submissions and approve/reject them, authenticated by `X-Admin-Key`. | `routes/admin.py`, `admin.js` | 🟡 B — API ok; `admin.html` page missing |
| FR-38 | Existing entries can be edited (`/edit/<id>`). | `frontend/app.py` | 🟡 A — anyone can edit anything, no auth, no history |
| FR-39 | Entries can be deleted. | `ToDo` QOL | ❌ |

### 3.7 Data population

| ID | Requirement | Source | Status |
|---|---|---|---|
| FR-40 | Fill the database automatically from Wikipedia geosearch over a lat/lon grid (default Europe 35–70°N, −10–40°E), keeping only "historical events" (keyword heuristic), at most 1000 entries, whenever the DB has < 100 entries. | `frontend/app.py`, `backend/app.py`, `import_wikipedia_geosearch.py` | 🟡 — runs as a thread on app import (also on Vercel/scripts); heuristic is very lossy |
| FR-41 | Import entries from a CSV file. | `import_entries_from_csv.py`, `entries_template.csv` | 🟡 — template is malformed; script targets the B schema |
| FR-42 | Import a given list of article titles. | `import_wikipedia_geosearch.py list ...` | ✅ (CLI) |
| FR-43 | "Fill up db" with substantially more events (major expansion). | `ToDo` | 🟡 |

### 3.8 General UI

| ID | Requirement | Source | Status |
|---|---|---|---|
| FR-44 | Pages: Home (map), About, Add Event, (Admin in B). | `base.html`, `vite.config.js` | ✅ A / 🟡 B |
| FR-45 | Dark mode toggle, remembering the choice and following the OS preference by default. | `ToDo`, `dark-mode.js` | ✅ |
| FR-46 | Responsive/mobile layout (hamburger menu, mobile filter section, synced mobile slider). | `ToDo`, commits "mobile version" | ✅ (🟡 mobile slider syncs one way only) |
| FR-47 | About page with idea, how it works, author and contact. | `about.html` | ✅ |

### 3.9 Future features (from `ToDo`)

| ID | Requirement | Status |
|---|---|---|
| FR-48 | **Map collections:** a user builds a personal collection of events with notes per event and per collection, views only those on the map, and can publish it. | ❌ |
| FR-49 | Collections without login: on creation generate an **edit link** and a **view link** (capability URLs) the user must keep. | ❌ (design question open — see Improvements §6) |
| FR-50 | Verify that ordering of dates before year 0 is correct. | ❌ no tests |

---

## 4. Data requirements

| ID | Requirement | Status |
|---|---|---|
| DR-1 | **Entry:** id, title, year (int, negative = BC, required), date string (≤100 chars, required), first paragraph (text, required), Wikipedia link (unique), category (enum), modified flag, tags (JSON list of names), status (B only), `used` (A only, unused). | 🟡 two incompatible model definitions |
| DR-2 | **Location:** 1:1 with entry; coordinates (A: `"lat,lon"` string; B: `lat`/`lon` floats), country, on_water. | 🟡 A does not enforce 1:1 (`unique=False`) |
| DR-3 | **Category** enum: military, diplomatic, naval, scientific, other. | ✅ |
| DR-4 | **Status** enum: pending, approved, rejected. | 🟡 B only |
| DR-5 | **Tag:** name, start_year, end_year (null = present). | 🟡 lives in Python source, not the DB; a stale `tags`/`entry_tags` table exists in the local DB |
| DR-6 | Year 0 does not exist historically; 1 BC → 1 AD ordering must be correct. | ❌ unverified |

---

## 5. External interface requirements (REST, implementation B)

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/api/health` | Health check | – |
| GET | `/api/events?year_from&year_to&category` | Approved events | – |
| GET | `/api/events/<id>` | One approved event | – |
| POST | `/api/events/preview` `{wiki_link}` | Extract Wikipedia data | – |
| POST | `/api/events` | Submit (status = pending) | – |
| GET | `/api/tags` | Tag catalogue | – |
| GET | `/api/admin/events/pending` | Pending list | `X-Admin-Key` |
| PATCH | `/api/admin/events/<id>/approve` · `/reject` | Moderate | `X-Admin-Key` |
| POST | `/run-migration` (blueprint not registered) | Add lat/lon columns | none (!) |

Implementation A exposes HTML routes `/`, `/about`, `/newEntry`, `POST /PreviewEntry`, `POST /create_new_entry`, `/edit/<id>` and JSON `/api/tags`.

---

## 6. Non-functional requirements

| ID | Category | Requirement | Status |
|---|---|---|---|
| NFR-1 | Accuracy | Data comes only from English Wikipedia; user changes are flagged (`modified`). | ✅ |
| NFR-2 | Security | Only admins can approve, edit or delete; admin key must not have a public default. | ❌ A has no auth; B defaults to `dev-admin-key` |
| NFR-3 | Security | User/Wikipedia text must never be rendered as HTML (XSS). | ❌ |
| NFR-4 | Security | Secrets (DB passwords, tokens) must not be in the repository. | ❌ `.env.production` is committed |
| NFR-5 | Security | State-changing forms are protected against CSRF; CORS limited to known origins. | ❌ |
| NFR-6 | Fair use of third-party APIs | Respect Wikipedia (descriptive User-Agent with real contact, ~1 req/s), Nominatim (≤1 req/s, real UA), OSM tile policy. | 🟡 placeholder contact info |
| NFR-7 | Performance | Map page loads and filters smoothly for thousands of events. | 🟡 all events inlined in HTML; full re-cluster on every slider tick |
| NFR-8 | Deployability | Runs on Vercel serverless with PostgreSQL; schema created/migrated reproducibly. | 🟡 manual ad-hoc migrations |
| NFR-9 | Portability | Works on SQLite (dev) and PostgreSQL (prod) with the same schema. | ❌ schemas diverged |
| NFR-10 | Usability | Responsive, dark mode, readable on mobile. | ✅ |
| NFR-11 | Accessibility | Keyboard-navigable, labelled controls, sufficient contrast. | 🟡 clickable `div`s, icon-only buttons without labels |
| NFR-12 | Maintainability | One backend, one frontend, one model, tests, linting. | ❌ |
| NFR-13 | Observability | Structured logging without leaking data; no debug prints in production. | ❌ DEBUG logs of headers/payloads, `print()` |
| NFR-14 | Licensing | Wikipedia text is CC BY-SA: attribution and share-alike notice required; OSM attribution. | 🟡 OSM attribution present; no CC BY-SA notice |
| NFR-15 | Privacy | No personal data collected; contact e-mail public by design. | ✅ |
