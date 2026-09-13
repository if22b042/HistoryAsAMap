#!/usr/bin/env python3
"""Update Battle of Stormberg entry with Boer Wars tag."""

import sys
import os

# Add the parent directory to the path so we can import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from frontend.app import app
from backend.models.model import db, Entry

def update_stormberg_tag():
    with app.app_context():
        # Find Battle of Stormberg entry
        stormberg = Entry.query.filter_by(wikiLink="https://en.wikipedia.org/wiki/Battle_of_Stormberg").first()
        
        if stormberg:
            print(f"Found Battle of Stormberg entry (ID: {stormberg.id})")
            print(f"Current tags: {stormberg.tags}")
            
            # Update with Boer Wars tag
            stormberg.tags = ["Boer Wars"]
            db.session.commit()
            
            print(f"Updated tags to: {stormberg.tags}")
            print("Successfully updated Battle of Stormberg with Boer Wars tag")
        else:
            print("Battle of Stormberg entry not found")

if __name__ == "__main__":
    update_stormberg_tag()
