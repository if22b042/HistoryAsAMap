#!/usr/bin/env python3
"""Print all entries and locations."""

from backend.app import create_app
from backend.models.event import Entry, Location

app = create_app()

with app.app_context():
    print("Entries:")
    for entry in Entry.query.all():
        print(entry.to_dict())

    print("\nLocations:")
    for loc in Location.query.all():
        print(loc.to_dict())
