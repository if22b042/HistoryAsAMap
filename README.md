# History As A Map (HAAM)

An interactive world map of historical events sourced from English Wikipedia.
Anyone can suggest an event; an editor reviews it before it appears on the map.

## How it works

1. A visitor pastes an English Wikipedia link on **Add event**.
2. HAAM reads the article: title, introduction, coordinates and date. Dates and
   coordinates come from **Wikidata** when available (reliable, handles BC and
   early AD years); otherwise the introduction text is parsed.
3. The visitor checks and corrects the details, picks a category and tags, and submits.
4. The event is stored as **pending**. An editor approves, rejects, edits or
   deletes it on the **Review** page (`/admin`).
5. Approved events appear on the map, filterable by year, category, tag and text.

The site never creates events on its own. Bulk imports are manual commands (see below).

## Map collections

Anyone can build a personal map at **Collections** (`/collections`), without an account:

- Add **confirmed events** from the main map, or **your own entries** (title, year,
  place picked on a map, description, category, optional link). Own entries are not
  reviewed and only appear inside that collection.
- Write a description for the collection and a note on every entry.
- Creating a collection gives two links: a **share link** (view only) and a secret
  **edit link**. The edit link is remembered in the browser that opened it; only a
  hash of it is stored, so it cannot be recovered if lost.
- Collections marked public are listed on the Collections page right away. Visitors
  can report them; editors hide or delete them under **Review → Review collections**.

Trust marks: ★ on an entry means it is backed by an English Wikipedia article (always
true for main-map events; checked against Wikipedia when an own entry's link is saved).
✔ marks confirmed main-map events. A collection shows the Wikipedia badge when every
entry has an article, and the certificate badge when every entry is a confirmed event.

## Project layout

```
haam/
  __init__.py       create_app(): config, extensions, blueprints, security headers
  config.py         settings from environment variables
  models.py         Event, Tag, Collection, CollectionEntry (tables prefixed haam_)
  events.py         business logic: preview, submit, update, moderate
  wikipedia.py      Wikipedia + Wikidata client, URL canonicalisation
  dates.py          year/date parsing and formatting (negative years = BC)
  geocoding.py      optional country lookup (OpenStreetMap Nominatim)
  importer.py       bulk imports used by the CLI
  auth.py           single editor account (session login)
  forms.py          WTForms forms (CSRF-protected)
  cli.py            `flask haam ...` commands
  data/tags.py      curated list of ~340 historical periods/conflicts
  collections_service.py  map collections: secret links, entries, reports
  views/            public pages, collections, admin pages, JSON API
  templates/        Jinja templates
  static/           CSS and JavaScript (no build step)
migrations/         Alembic database migrations
tests/              pytest suite (no network access needed)
api/index.py        Vercel entry point
```

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
```

Fill in `.env`: at least `SECRET_KEY`, and for the editor login `ADMIN_PASSWORD_HASH`:

```bash
flask --app haam haam hash-password
```

Create the database and load the tags:

```bash
flask --app haam db upgrade
flask --app haam haam seed-tags
```

Run the site at http://127.0.0.1:5000 (editor login at `/admin`):

```bash
flask --app haam run --debug
```

Run the tests:

```bash
pytest
```

GitHub Actions (`.github/workflows/tests.yml`) runs pyflakes and the test suite on every
push and pull request, on SQLite (Python 3.11 and 3.12) and on PostgreSQL 16, and checks
that the migrations apply, downgrade and match the models. Run the suite against your own
PostgreSQL with `TEST_DATABASE_URL=postgresql://user:pass@host/db pytest`.

The app applies pending migrations and loads the tags automatically when it starts
(disable with `AUTO_SETUP_DATABASE=false`); `flask db upgrade` does the same by hand.

## Commands

| Command | Purpose |
|---|---|
| `flask --app haam db upgrade` | Create or upgrade the database schema |
| `flask --app haam haam seed-tags` | Add the curated tags (safe to re-run) |
| `flask --app haam haam hash-password` | Generate `ADMIN_PASSWORD_HASH` |
| `flask --app haam haam import-titles "Battle of Hastings" "Peace of Westphalia"` | Import articles by title |
| `flask --app haam haam import-region --lat 35 70 --lon -10 40 --max-new 100` | Find dated events by geosearch in a lat/lon box |
| `flask --app haam haam import-csv examples/events.csv` | Import a CSV (`url,category,year,tags`) |
| `flask --app haam haam import-legacy` | Copy data from the previous version's `entries`/`locations` tables |

Imports go into the review queue as **pending**; add `--approve` to publish directly.
`import-region` keeps only articles that Wikidata dates with a point in time or a
start time, which filters out towns, buildings and other places.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(required in production)* | Signs session cookies and CSRF tokens |
| `DATABASE_URL` | `sqlite:///instance/haam.db` | PostgreSQL in production (`postgres://` and `postgresql://` both work) |
| `ADMIN_USERNAME` | `admin` | Editor username |
| `ADMIN_PASSWORD_HASH` | *(login disabled)* | Werkzeug hash from `hash-password` |
| `HAAM_ENV` | `production` on Vercel, else `development` | `development`, `production` or `testing` |
| `HAAM_USER_AGENT` | project URL | Sent to Wikipedia and Nominatim, as their policies require |
| `GEOCODING_ENABLED` | `true` | Look up each event's country |
| `SESSION_COOKIE_SECURE` | `true` | Set `false` only for plain-HTTP setups |
| `AUTO_SETUP_DATABASE` | `true` | Apply migrations and load tags on startup |

## Deploying to Vercel

1. In Vercel → Settings → Environment Variables set `SECRET_KEY`, `DATABASE_URL`
   and `ADMIN_PASSWORD_HASH` (never commit `.env` files).
2. Push. Vercel serves `api/index.py`; on its first start the app creates its tables
   and loads the tags.
3. Once, to keep the events of the old version, run from your machine:
   ```bash
   set DATABASE_URL=postgresql://...   # macOS/Linux: export DATABASE_URL=...
   flask --app haam haam import-legacy
   ```

The old tables (`entries`, `locations`, `tags`, `entry_tags`) are only read by
`import-legacy`; drop them by hand once you're happy with the migrated data.

## API

| Method | Path | Returns |
|---|---|---|
| GET | `/api/events` | Approved events |
| GET | `/api/tags` | All tags |
| GET | `/api/categories` | Category values and labels |
| GET | `/api/health` | `{"status": "ok"}` |

## Credits

Event text © Wikipedia contributors,
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Map data ©
[OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.
