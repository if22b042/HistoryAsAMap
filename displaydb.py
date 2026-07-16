# displaydb.py
from backend.models.model import Entry, Location
from frontend.app import app, db
import os
# Make sure to use Flask app context
with app.app_context():
    db.drop_all()
    db.create_all()
    print("Entries:")
    all_entries = Entry.query.all()
    for entry in all_entries:
        print(entry.to_dict())

    print("\nLocations:")
    all_locations = Location.query.all()
    for loc in all_locations:
        print(loc.to_dict())

