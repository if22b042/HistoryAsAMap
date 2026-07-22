# History As A Map (HAAM)

An interactive map of historical events sourced from English Wikipedia. Users submit events for admin approval; approved events appear on the public map.

## Architecture

- **Backend:** Flask REST API (`backend/`) with SQLAlchemy + SQLite
- **Frontend:** Plain HTML/CSS/JS with Vite dev server (`frontend/`)

## Setup

### Backend

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m backend.app
```

API runs at `http://127.0.0.1:5000`.

If upgrading from the old monolithic schema, reset the database:

```bash
python scripts/reset_db.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173` and proxies `/api` to the backend.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/events` | List approved events |
| GET | `/api/events/:id` | Get one approved event |
| POST | `/api/events/preview` | Preview Wikipedia data |
| POST | `/api/events` | Submit event (status: pending) |
| GET | `/api/admin/events/pending` | List pending (header: `X-Admin-Key`) |
| PATCH | `/api/admin/events/:id/approve` | Approve event |
| PATCH | `/api/admin/events/:id/reject` | Reject event |

Default admin API key: `dev-admin-key` (override with `ADMIN_API_KEY` env var).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///instance/yourdb.db` | Database connection |
| `ADMIN_API_KEY` | `dev-admin-key` | Admin authentication key |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Allowed CORS origins |

## Scripts

- `scripts/reset_db.py` — Drop and recreate tables
- `scripts/clear_database.py` — Delete all data
- `scripts/display_db.py` — Print database contents

## Workflow

1. User submits an English Wikipedia URL on **Add Event**
2. Backend fetches metadata and shows a preview
3. User edits if needed and submits — entry saved as **pending**
4. Admin approves/rejects on **Admin** page
5. Approved events appear on the map
