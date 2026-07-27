#!/usr/bin/env python3
"""Add start_year and end_year columns to the tags table."""

import sys
import os

# Add the parent directory to the path so we can import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from frontend.app import app
from backend.models.model import db

def add_tag_dates_columns():
    with app.app_context():
        # Check if columns already exist
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('tags')]
        
        if 'start_year' in columns and 'end_year' in columns:
            print("Columns start_year and end_year already exist in tags table.")
            return
        
        # Add the columns using raw SQL
        if 'start_year' not in columns:
            db.session.execute(db.text("ALTER TABLE tags ADD COLUMN start_year INTEGER"))
            print("Added start_year column to tags table.")
        
        if 'end_year' not in columns:
            db.session.execute(db.text("ALTER TABLE tags ADD COLUMN end_year INTEGER"))
            print("Added end_year column to tags table.")
        
        db.session.commit()
        print("Successfully added date columns to tags table.")

if __name__ == "__main__":
    add_tag_dates_columns()
