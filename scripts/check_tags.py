import sys
import os

# Add the parent directory to the path so we can import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from frontend.app import app
from backend.models.model import Tag, db

def check_tags():
    with app.app_context():
        tags = Tag.query.all()
        print(f"Found {len(tags)} tags in database:")
        for tag in tags:
            print(f"  - {tag.id}: {tag.name} ({tag.start_year} - {tag.end_year})")
        
        if len(tags) == 0:
            print("\nNo tags found. You need to run populate_tags.py first.")
        
        # Test the to_dict method
        print("\nTesting to_dict on first tag:")
        if tags:
            print(tags[0].to_dict())

if __name__ == "__main__":
    check_tags()
