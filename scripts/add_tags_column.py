#!/usr/bin/env python3
"""Add tags column to the entries table."""

import sys
import os

# Add the parent directory to the path so we can import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from frontend.app import app
from backend.models.model import db

def add_tags_column():
    with app.app_context():
        # Check if column already exists
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('entries')]
        
        if 'tags' in columns:
            print("Column 'tags' already exists in entries table.")
            return
        
        # Add the column using raw SQL
        db.session.execute(db.text("ALTER TABLE entries ADD COLUMN tags JSON"))
        print("Added tags column to entries table.")
        
        db.session.commit()
        print("Successfully added tags column to entries table.")

if __name__ == "__main__":
    add_tags_column()
