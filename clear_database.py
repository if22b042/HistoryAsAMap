#!/usr/bin/env python3
# Clear all entries from the database

from backend.models.model import Entry, Location
from frontend.app import app, db

print("Clearing all entries from the database...")

with app.app_context():
    # Count entries before deletion
    entry_count = Entry.query.count()
    location_count = Location.query.count()
    print(f"Found {entry_count} entries and {location_count} locations")
    
    # Delete all entries (this will cascade delete locations due to foreign key)
    Entry.query.delete()
    Location.query.delete()
    
    # Commit the changes
    db.session.commit()
    
    print("All entries have been successfully removed!")
    print(f"Database now contains {Entry.query.count()} entries and {Location.query.count()} locations")
