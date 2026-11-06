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

## Demo data

`seed/` contains CSV files with 74 real events (most approved, some pending or rejected,
so the review queue has work in it) and 8 collections in different states: public,
unlisted, reported, hidden by an editor, and empty. Load them all with:

```bash
python seed_demo.py
```

Events are looked up live on Wikipedia, so the first run takes a couple of minutes;
running it again skips what already exists. Collection share and edit links are
printed and saved to `instance/demo-links.txt`.

## Bulk events from Wikidata

`flask --app haam haam export-wikidata` builds `seed/wikidata_events_places.csv`: every
column the Event model needs (Wikidata id, Wikipedia page id and URL, title, year,
date text, coordinates, country, category, status, tags, introduction), plus where
the date and coordinates came from. Load it, offline and in batches, with:

```bash
flask --app haam haam import-csv seed/wikidata_events_places.csv
```

Two exports are in `seed/`:

| File | Events | Locations |
|---|---|---|
| `wikidata_events_places.csv` (+ `wikidata_rejected_places.csv`) | 18,078 | only specific places (towns, buildings); the current rules |
| `wikidata_events.csv` (+ `wikidata_rejected.csv`) | 21,680 | older export that also placed 3,602 events at the centre of a country, region or sea |

A database loaded from the older file can drop those 3,602 events with
(`--dry-run` only counts; events used in a collection are kept and listed):

```bash
flask --app haam haam remove-events seed/wikidata_rejected_places.csv --reason "location is a country"
```

An item becomes an event only if it passes all of these checks
(`haam/wikidata.py: validate`, tested in `tests/test_wikidata.py`):

1. it has an English Wikipedia article;
2. it is an *instance of* one of the event types in `haam/data/event_types.py`
   (battle, siege, treaty, coup, earthquake, …) or any of their subtypes;
3. it is not also typed as a non-event: a person, settlement, building,
   battlefield, list, category, recurring event, or any kind of fictional entity;
   and an item with no point in time or start time of its own must not be a
   military unit, state or organisation (Afrika Korps, UN missions, Transnistria
   are filed under event types on Wikidata but were founded, not fought);
4. it has a date, at least year-precise and not in the future: on Wikidata its
   point in time (P585), start time (P580), end time (P582) or inception (P571);
   failing those, the year in its Wikipedia title ("Battle of Tripoli (2018)")
   or a date in the article's first paragraph – never a century. The CSV's
   `date_source` column says which one was used;
5. it has coordinates on Earth: its own, or those of its location / place of
   creation / place of formation (that is how treaties get a place), but only
   if that location is a specific place – a town, a building, a street – never
   a country, region, province, sea or continent, whose coordinates are just a
   rough centre (`PLACE_ROOTS` / `AREA_ROOTS` in `haam/data/event_types.py`);
6. its Wikipedia link, after redirects, leads to an article about the same item;
7. that article is not a list, timeline or disambiguation page.

Everything rejected goes to `seed/wikidata_rejected_places.csv` with the reason. The
first matching type decides the category (naval battle → naval, treaty →
diplomatic, …). Options: `--type Q178561` (only some types), `--limit 20` (trial
run), `--status pending` (send everything through the review queue).

`--undated` exports the items the normal export skips because Wikidata gives
them no point in time or start time (such as the Siege of Trondheim); they go to
`seed/wikidata_events_undated.csv` and `seed/wikidata_rejected_undated.csv`.
Load both files to get everything:

```bash
flask --app haam haam import-csv seed/wikidata_events_places.csv
flask --app haam haam import-csv seed/wikidata_events_undated.csv
```

### Tags

An event gets every tag from `haam/data/tags.py` that it is *part of* (P361) on
Wikidata, directly or up to five steps up the chain: Battle of Freeman's Farm →
Battles of Saratoga → American Revolutionary War → American Revolution gives both
"American Revolutionary War" and "American Revolution" (`haam/tagging.py`).
Names are compared loosely (case, accents, dashes, apostrophes, a leading "The")
against each item's label and aliases, `TAG_PARENTS` adds broader tags Wikidata
does not link, and a tag is only given if the event's year is within the tag's
years (one year early is allowed, none late). A hand check of 660 assignments
found Wikidata links that join conflicts historians treat as separate (the wars
in Afghanistan → "War against the Islamic State" → Syrian Civil War, Lebanon →
Arab Cold War → Cold War, Finnish Civil War → Russian Civil War, ...): the chain
is not followed above those items (`NO_CLIMB`), and three direct links are
excluded (`EXCLUDED_TAGS`). To apply the rules to existing data without a full
export:

```bash
flask --app haam haam retag-csv seed/wikidata_events_places.csv seed/wikidata_events_undated.csv
flask --app haam haam retag-events --replace --dry-run   # then without --dry-run
```

`retag-events` only adds tags; `--replace` also removes the tags the rules no
longer give. Both leave events submitted on the website alone.

## Commands

| Command | Purpose |
|---|---|
| `flask --app haam db upgrade` | Create or upgrade the database schema |
| `flask --app haam haam seed-tags` | Add the curated tags (safe to re-run) |
| `flask --app haam haam hash-password` | Generate `ADMIN_PASSWORD_HASH` |
| `flask --app haam haam import-titles "Battle of Hastings" "Peace of Westphalia"` | Import articles by title |
| `flask --app haam haam import-region --lat 35 70 --lon -10 40 --max-new 100` | Find dated events by geosearch in a lat/lon box |
| `flask --app haam haam export-wikidata` | Write validated events from Wikidata to `seed/wikidata_events_places.csv` |
| `flask --app haam haam import-csv seed/events.csv` | Import a CSV (`url`, optional `category,status,year,lat,lon,tags`) |
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
