#!/usr/bin/env python3
"""Remove all entries and locations from the database."""

from backend.app import create_app
from backend.extensions import db
from backend.models.event import Entry, Location

app = create_app()

with app.app_context():
    entry_count = Entry.query.count()
    location_count = Location.query.count()
    print(f"Found {entry_count} entries and {location_count} locations")

    Location.query.delete()
    Entry.query.delete()
    db.session.commit()

    print(f"Cleared. Now: {Entry.query.count()} entries, {Location.query.count()} locations")
