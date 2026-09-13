#!/usr/bin/env python3
"""Check tags in database entries."""

import sys
import os

# Add the parent directory to the path so we can import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from frontend.app import app
from backend.models.model import db, Entry

def check_entry_tags():
    with app.app_context():
        # Check if tags column exists
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('entries')]
        print(f"Columns in entries table: {columns}")
        print(f"'tags' column exists: {'tags' in columns}")
        
        # Get all entries
        entries = Entry.query.all()
        print(f"\nFound {len(entries)} entries in database")
        
        # Check Battle of Stormberg specifically
        stormberg = Entry.query.filter_by(wikiLink="https://en.wikipedia.org/wiki/Battle_of_Stormberg").first()
        if stormberg:
            print(f"\nBattle of Stormberg entry found:")
            print(f"  ID: {stormberg.id}")
            print(f"  Title: {stormberg.title}")
            print(f"  Tags: {stormberg.tags}")
            print(f"  Tags type: {type(stormberg.tags)}")
        else:
            print("\nBattle of Stormberg entry not found")
        
        # Show tags for all entries
        print("\nTags for all entries:")
        for entry in entries:
            print(f"  {entry.title}: {entry.tags}")

if __name__ == "__main__":
    check_entry_tags()
