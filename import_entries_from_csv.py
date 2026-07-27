import csv
import sys
import os
from flask import Flask
from backend.models.event import db, Entry, Location, Tag, EventCategory, EntryStatus
from backend.config import Config

def import_entries_from_csv(csv_file_path):
    """Import entries from a CSV file into the database."""
    
    # Initialize Flask app
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    
    with app.app_context():
        entries_added = 0
        entries_skipped = 0
        tags_added = 0
        
        with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                wiki_link = row.get('wikiLink', '').strip()
                
                if not wiki_link:
                    print(f"Skipping row: missing wikiLink")
                    entries_skipped += 1
                    continue
                
                # Check if entry already exists
                existing_entry = Entry.query.filter_by(wikiLink=wiki_link).first()
                if existing_entry:
                    print(f"Skipping: entry already exists - {wiki_link}")
                    entries_skipped += 1
                    continue
                
                # Parse category
                category_str = row.get('category', 'other').strip().lower()
                try:
                    category = EventCategory(category_str)
                except ValueError:
                    print(f"Invalid category '{category_str}' for {wiki_link}, using 'other'")
                    category = EventCategory.OTHER
                
                # Create entry
                entry = Entry(
                    title=row.get('title', '').strip() or None,
                    year=int(row.get('year', 0)) if row.get('year') else None,
                    dateString=row.get('date', '').strip() or 'Unknown date',
                    firstParagraph=row.get('first_paragraph', '').strip() or 'No description available.',
                    wikiLink=wiki_link,
                    category=category,
                    status=EntryStatus.PENDING,
                    modified=False
                )
                
                db.session.add(entry)
                db.session.flush()  # Generate ID without committing
                
                # Create location if coordinates provided
                lat = row.get('lat', '').strip()
                lon = row.get('lon', '').strip()
                
                if lat and lon:
                    try:
                        location = Location(
                            lat=float(lat),
                            lon=float(lon),
                            country=row.get('country', '').strip() or None,
                            on_water=row.get('on_water', 'false').strip().lower() == 'true',
                            entry_id=entry.id
                        )
                        db.session.add(location)
                    except ValueError:
                        print(f"Invalid coordinates for {wiki_link}, skipping location")
                
                # Handle tags
                tags_str = row.get('tags', '').strip()
                if tags_str:
                    tag_names = [tag.strip() for tag in tags_str.split(',')]
                    for tag_name in tag_names:
                        if tag_name:
                            # Get or create tag
                            tag = Tag.query.filter_by(name=tag_name).first()
                            if not tag:
                                tag = Tag(name=tag_name, start_year=None, end_year=None)
                                db.session.add(tag)
                                tags_added += 1
                            entry.tags.append(tag)
                
                db.session.commit()
                entries_added += 1
                print(f"Added entry: {entry.title or wiki_link}")
        
        print(f"\nImport complete!")
        print(f"Entries added: {entries_added}")
        print(f"Entries skipped: {entries_skipped}")
        print(f"Tags added: {tags_added}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python import_entries_from_csv.py <csv_file_path>")
        print("Example: python import_entries_from_csv.py entries_template.csv")
        sys.exit(1)
    
    csv_file_path = sys.argv[1]
    
    if not os.path.exists(csv_file_path):
        print(f"Error: CSV file not found: {csv_file_path}")
        sys.exit(1)
    
    import_entries_from_csv(csv_file_path)
