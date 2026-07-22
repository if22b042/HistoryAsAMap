#!/usr/bin/env python3
"""Drop and recreate the database with the current schema."""

from backend.app import create_app
from backend.extensions import db

app = create_app()

with app.app_context():
    db.drop_all()
    db.create_all()
    print("Database reset complete.")
