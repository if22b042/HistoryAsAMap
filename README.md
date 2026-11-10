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

`seed/wikidata_events.csv` holds 19,176 validated events (52 of them pending
review) with every column the Event model needs: Wikidata id, Wikipedia page id
and URL, title, year, date text, coordinates, country, category, status, tags and
introduction, plus where the date and coordinates came from. Make a database's
Wikidata events match it – offline, in seconds, safe to re-run – with:

```bash
flask --app haam haam sync-wikidata --dry-run   # shows what would change
flask --app haam haam sync-wikidata
```

It adds events that are missing, removes imported events that are no longer in
the file, and sets each imported event's tags to the file's. Events submitted on
the website are never changed, and an event used in a collection is never
removed (it is listed instead). Older rows of the same article without a
Wikidata id (the demo data) are adopted. `flask --app haam haam export-wikidata`
rebuilds the file from Wikidata (about an hour).

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

Everything rejected goes to `seed/wikidata_rejected.csv` with the reason. The
first matching type decides the broad category (naval battle → naval, treaty →
diplomatic, …); for natural, fire and "other" items it is then refined from the
item's own P31 classes (`CATEGORY_CLASSES` in `haam/data/event_types.py`):
massacres and terrorist attacks → disaster; earthquakes,
eruptions, storms and floods → natural; fires, explosions, accidents and
collapses → disaster; wildfires stay natural unless Wikidata names a human cause
(arson, slash-and-burn…). Events dated only by an inception go in as pending.
`flask --app haam haam recategorize` applies the same rules to the database and
the CSV (`--dry-run` to preview). Options:
`--type Q178561` (only some types), `--limit 20` (trial run), `--status pending`
(send everything through the review queue).

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
excluded (`EXCLUDED_TAGS`). After changing the rules, refresh the file's tags
without a full export, then sync:

```bash
flask --app haam haam retag-csv seed/wikidata_events.csv
flask --app haam haam sync-wikidata
```

**Tag trees.** The tree button on a selected tag chip shows the tag as a tree of
its parts, every level largest branch first: World War II › European Theater ›
Eastern Front › Operation Barbarossa › its battles. Clicking a part narrows the map
to its events (`?tag=301&part=Q83055`), clicking a tag in the tree selects that tag
and clicking a single event opens it. The tree follows the same "part of" chains
as tagging; they are stored in `haam/data/part_of.json` so no Wikidata request is
made at page load (`haam/tag_tree.py`, served by `/api/tags/<id>/tree`). Each event
sits once, under the longest chain that leads to the tag. Rebuild the file after a
new export or retag (about 7,000 events, a few minutes) and commit it:

```bash
flask --app haam haam build-part-of
```

## Commands

| Command | Purpose |
|---|---|
| `flask --app haam db upgrade` | Create or upgrade the database schema |
| `flask --app haam haam seed-tags` | Add the curated tags (safe to re-run) |
| `flask --app haam haam hash-password` | Generate `ADMIN_PASSWORD_HASH` |
| `flask --app haam haam import-titles "Battle of Hastings" "Peace of Westphalia"` | Import articles by title |
| `flask --app haam haam import-region --lat 35 70 --lon -10 40 --max-new 100` | Find dated events by geosearch in a lat/lon box |
| `flask --app haam haam export-wikidata` | Rebuild `seed/wikidata_events.csv` from Wikidata |
| `flask --app haam haam sync-wikidata` | Make the database's Wikidata events match `seed/wikidata_events.csv` |
| `flask --app haam haam recategorize` | Re-derive imported events' categories from their Wikidata classes (database and CSV) |
| `flask --app haam haam retag-csv seed/wikidata_events.csv` | Recompute the file's tags column from Wikidata |
| `flask --app haam haam build-part-of` | Fetch the tagged events' "part of" chains into `haam/data/part_of.json` (tag trees) |
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
3. Load the events, from your machine, with the database's connection string:
   ```bash
   set DATABASE_URL=postgresql://...   # PowerShell: $env:DATABASE_URL = "..."
   flask --app haam haam sync-wikidata
   ```
4. Once, to keep the events of the old version, run from your machine:
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
