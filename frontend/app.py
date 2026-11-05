from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
import re
import threading
import logging
import requests
import time

from backend.controllers.CheckNewEntry import CheckEntry
from backend.controllers.SaveEntry import SaveEntry
from backend.models.model import db, Entry, Location, EventCategory
from backend.controllers.LocationInfoRetriever import reverse_geocode, check_on_water
from backend.api.WikiApi import get_wikipedia_data
WIKIPEDIA_REGEX = r"^https:\/\/([a-z]{2}\.)?wikipedia\.org\/wiki\/.*$"

import os

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(INSTANCE_DIR, 'yourdb.db')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

def format_year(year):
    if year is None or year == "":
        return ""
    try:
        num_year = int(year)
        if num_year < 0:
            return f"{abs(num_year)} BC"
        return str(num_year)
    except (ValueError, TypeError):
        return str(year) if year else ""

app.jinja_env.filters['format_year'] = format_year


def geosearch_wikipedia(lat, lon, radius=10000, limit=500, namespace=0):
    """Search for Wikipedia articles with coordinates within a radius of a point."""
    api_url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "geosearch",
        "gsradius": radius,
        "gscoord": f"{lat}|{lon}",
        "gslimit": limit,
        "gsnamespace": namespace,
        "format": "json"
    }
    
    headers = {
        "User-Agent": "HistoryAsAMap/1.0 (https://github.com/yourusername/history-as-a-map; your.email@example.com) Python-requests/2.x"
    }
    
    try:
        time.sleep(1)
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("query", {}).get("geosearch", [])
    except Exception as e:
        logger.error(f"Error in geosearch: {e}")
        return []


def is_historical_event(title, extract):
    """Check if the Wikipedia page is a historical event, not a town/city/village."""
    if not extract:
        return False
    
    extract_lower = extract.lower()
    title_lower = title.lower()
    
    # Keywords that indicate towns, cities, villages, municipalities
    location_keywords = [
        'village', 'town', 'city', 'municipality', 'commune', 'settlement',
        'hamlet', 'suburb', 'district', 'neighborhood', 'locality',
        'is a village in', 'is a town in', 'is a city in', 'is a municipality',
        'is a commune in', 'is a settlement in', 'is a hamlet in',
        'population is', 'census', 'inhabitants', 'residents',
        'located in the', 'situated in the', 'lies in the'
    ]
    
    # Check if extract contains location keywords
    for keyword in location_keywords:
        if keyword in extract_lower:
            logger.debug(f"Skipping {title}: contains location keyword '{keyword}'")
            return False
    
    # Check if title looks like a location (ends with common location suffixes)
    location_suffixes = [
        ' district', ' province', ' region', ' county', ' state',
        ' municipality', ' commune', ' village', ' town', ' city'
    ]
    for suffix in location_suffixes:
        if title_lower.endswith(suffix):
            logger.debug(f"Skipping {title}: title ends with location suffix '{suffix}'")
            return False
    
    # Keywords that suggest historical events
    event_keywords = [
        'battle', 'war', 'siege', 'invasion', 'conquest', 'revolution',
        'uprising', 'rebellion', 'revolt', 'coup', 'assassination',
        'treaty', 'peace', 'agreement', 'alliance', 'conference',
        'massacre', 'genocide', 'holocaust', 'tragedy', 'disaster',
        'expedition', 'campaign', 'operation', 'offensive', 'raid',
        'bombing', 'attack', 'strike', 'independence', 'declaration',
        'founding', 'establishment', 'creation', 'formation', 'unification',
        'collapse', 'fall of', 'rise of', 'empire', 'kingdom', 'dynasty'
    ]
    
    # At least one event keyword should be present
    has_event_keyword = any(keyword in extract_lower or keyword in title_lower for keyword in event_keywords)
    
    if not has_event_keyword:
        logger.debug(f"Skipping {title}: no historical event keywords found")
        return False
    
    return True


def auto_import_wikipedia_entries(lat_min=35, lat_max=70, lon_min=-10, lon_max=40, 
                                  grid_size=5, radius=10000, max_total=1000):
    """Automatically import Wikipedia entries with coordinates from a region."""
    with app.app_context():
        logger.info("Starting automatic Wikipedia import...")
        entries_added = 0
        entries_skipped = 0
        entries_failed = 0
        entries_filtered = 0
        
        lat_steps = int((lat_max - lat_min) / grid_size) + 1
        lon_steps = int((lon_max - lon_min) / grid_size) + 1
        
        logger.info(f"Scanning region: lat [{lat_min}, {lat_max}], lon [{lon_min}, {lon_max}]")
        logger.info(f"Grid points: {lat_steps} x {lon_steps}")
        
        for lat_i in range(lat_steps):
            for lon_j in range(lon_steps):
                if max_total and entries_added >= max_total:
                    logger.info(f"Reached max total limit of {max_total} entries")
                    break
                
                lat = lat_min + (lat_i * grid_size)
                lon = lon_min + (lon_j * grid_size)
                
                pages = geosearch_wikipedia(lat, lon, radius=radius)
                
                for page in pages:
                    if max_total and entries_added >= max_total:
                        break
                    
                    title = page.get("title")
                    wiki_link = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                    
                    existing_entry = Entry.query.filter_by(wikiLink=wiki_link).first()
                    if existing_entry:
                        entries_skipped += 1
                        continue
                    
                    wiki_data = get_wikipedia_data(wiki_link)
                    
                    if not wiki_data:
                        entries_failed += 1
                        continue
                    
                    if not wiki_data.get("lat") or not wiki_data.get("lon"):
                        entries_failed += 1
                        continue
                    
                    if wiki_data.get("year") is None:
                        entries_failed += 1
                        continue
                    
                    # Filter out towns, cities, villages - only keep historical events
                    extract = wiki_data.get("first_paragraph", "")
                    if not is_historical_event(title, extract):
                        entries_filtered += 1
                        continue
                    
                    year = wiki_data.get("year")
                    try:
                        year = int(year)
                    except (ValueError, TypeError):
                        year = None
                    
                    entry = Entry(
                        title=wiki_data.get("title"),
                        year=year,
                        dateString=wiki_data.get("date") or "Unknown date",
                        firstParagraph=wiki_data.get("first_paragraph") or "No description available.",
                        wikiLink=wiki_link,
                        category=EventCategory.OTHER,
                        used=False
                    )
                    
                    db.session.add(entry)
                    db.session.flush()
                    
                    lat_coord = wiki_data.get("lat")
                    lon_coord = wiki_data.get("lon")
                    
                    if lat_coord and lon_coord:
                        location = Location(
                            coordinates=f"{lat_coord},{lon_coord}",
                            country=None,
                            on_water=False,
                            entry_id=entry.id
                        )
                        db.session.add(location)
                    
                    db.session.commit()
                    entries_added += 1
                    logger.info(f"Added entry {entries_added}: {title}")
                    
                    time.sleep(0.5)
                
                time.sleep(1)
        
        logger.info(f"Auto-import complete: added={entries_added}, skipped={entries_skipped}, failed={entries_failed}, filtered (non-events)={entries_filtered}")


db.init_app(app)
with app.app_context():
    db.create_all()
    
    # Only auto-import if database has less than 100 entries
    entry_count = Entry.query.count()
    if entry_count < 100:
        logger.info(f"Database has {entry_count} entries (< 100), starting automatic Wikipedia import...")
        import_thread = threading.Thread(target=auto_import_wikipedia_entries, daemon=True)
        import_thread.start()
        logger.info("Started automatic Wikipedia import in background")
    else:
        logger.info(f"Database already has {entry_count} entries (>= 100), skipping auto-import")

@app.route("/")
def index():
    raw_entries = Entry.query.all()
    entries = [e.to_dict() for e in raw_entries]
    return render_template("index.html", entries=entries)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/newEntry")
def newEntry():
    return render_template("new_entry.html", entry={})


@app.route("/edit/<int:entry_id>")
def editEntry(entry_id):
    entry = Entry.query.get(entry_id)
    if not entry:
        return redirect(url_for("index"))
    
    # Parse coordinates from location
    lat, lon = 0, 0
    if entry.location and entry.location.coordinates:
        try:
            coords = entry.location.coordinates.split(',')
            lat = float(coords[0])
            lon = float(coords[1])
        except (ValueError, IndexError):
            lat, lon = 0, 0
    
    # Format entry data for the preview/edit page
    entry_data = {
        "title": entry.title,
        "date": entry.dateString,
        "year": entry.year,
        "first_paragraph": entry.firstParagraph,
        "link": entry.wikiLink,
        "category": entry.category.value if entry.category else "other",
        "tags": entry.tags if entry.tags else [],
        "coordinates": [lat, lon],
        "lat": lat,
        "lon": lon,
    }
    
    return render_template("submit_entry.html", entry=entry_data, is_duplicate=True, existing_id=entry_id, is_edit=True)


@app.route("/PreviewEntry", methods=["POST"])
def PreviewEntry():
    wiki_link = request.form.get("wikiLink")
    category = request.form.get("category")
    
    # Debug: Print all form data
    print(f"DEBUG - Form data received: {dict(request.form)}")
    print(f"DEBUG - wikiLink: '{wiki_link}' (type: {type(wiki_link)})")
    print(f"DEBUG - category: '{category}' (type: {type(category)})")

    if not wiki_link or not re.match(WIKIPEDIA_REGEX, wiki_link):
        return render_template(
            "new_entry.html",
            error="Invalid Wikipedia link. Please enter a valid Wikipedia URL.",
            wiki_link=wiki_link
        )

    entry_data = CheckEntry(wiki_link)

    if isinstance(entry_data, dict) and "error" in entry_data:
        return render_template(
            "new_entry.html",
            error=entry_data["error"],
            wiki_link=wiki_link
        )
    elif not entry_data:
        return render_template(
            "new_entry.html",
            error="Entry could not be retrieved or already exists in the database.",
            wiki_link=wiki_link
        )

    # Add category to entry data
    entry_data['category'] = category

    # Initialize tags as empty array (will be selected in preview)
    entry_data["tags"] = []

    # If it's a duplicate entry, pass the flag to the template
    is_duplicate = entry_data.get('is_duplicate', False)
    existing_id = entry_data.get('existing_id')

    # If everything is okay, show the preview page
    return render_template("submit_entry.html", entry=entry_data, is_duplicate=is_duplicate, existing_id=existing_id)


@app.route("/create_new_entry", methods=["POST"])
def create_new_entry():
    modified = request.form.get("modified") == "true"
    existing_id = request.form.get("existing_id")
    
    # Debug: Print all form data received
    print(f"DEBUG CREATE - Form data: {dict(request.form)}")
    print(f"DEBUG CREATE - All keys: {list(request.form.keys())}")
    print(f"DEBUG CREATE - existing_id: {existing_id}")

    # Validate category
    category = request.form.get("category")
    print(f"DEBUG CREATE - category: '{category}' (type: {type(category)})")
    print(f"DEBUG CREATE - category is None: {category is None}")
    print(f"DEBUG CREATE - category == '': {category == ''}")
    
    if not category or category == "":
        return render_template(
            "new_entry.html",
            error="Event category is required.",
            wiki_link=request.form.get("link")
        )
    
    lat = float(request.form.get("lat"))
    lon = float(request.form.get("lon"))

    # Gather data
    entry_data = {
        "title": request.form.get("title"),
        "date": request.form.get("date"),
        "year": request.form.get("year"),
        "first_paragraph": request.form.get("first_paragraph"),
        "link": request.form.get("link"),
        "category": category,
        "lat": lat,
        "lon": lon
    }
    
    # Handle tags
    tags_str = request.form.get("tags")
    print(f"DEBUG - tags_str received: '{tags_str}'")
    if tags_str:
        import json
        try:
            entry_data["tags"] = json.loads(tags_str)
            print(f"DEBUG - Parsed tags: {entry_data['tags']}")
        except json.JSONDecodeError as e:
            print(f"DEBUG - JSON decode error: {e}")
            entry_data["tags"] = []
    else:
        print(f"DEBUG - No tags_str received")
        entry_data["tags"] = []

    # Fetch values dynamically
    country = reverse_geocode(lat, lon)
    on_water = check_on_water(lat, lon)

    entry_data["country"] = country
    entry_data["on_water"] = on_water

    # Save entry (this returns the created or updated Entry object)
    if existing_id:
        new_entry = SaveEntry(entry_data, modified, existing_id=int(existing_id))
    else:
        new_entry = SaveEntry(entry_data, modified)
    
    print (lon, lat, country, on_water)
    
    # If we're creating a new entry (not updating), we need to create the location
    # SaveEntry already handles location for updates, but for new entries we need to add it
    if not existing_id:
        location = Location(
            coordinates=f"{lat},{lon}",
            country=country,
            on_water=on_water,
            entry_id=new_entry.id
        )
        db.session.add(location)
        db.session.commit()

    return redirect(url_for("index"))


@app.route("/api/tags")
def get_tags():
    # Import tags from the add_tags.py file
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from add_tags import TAGS
    
    def format_year(year):
        if year is None:
            return "Present"
        if year < 0:
            return f"{abs(year)} BC"
        return f"{year} AD"
    
    def get_average_year(start_year, end_year):
        if start_year is None and end_year is None:
            return 0
        if start_year is None:
            return end_year
        if end_year is None:
            return start_year
        return (start_year + end_year) / 2
    
    # Add IDs, formatted dates, and calculate average for sorting
    tags_with_data = []
    for idx, tag in enumerate(TAGS):
        start_year = tag.get("start_year")
        end_year = tag.get("end_year")
        avg_year = get_average_year(start_year, end_year)
        
        tags_with_data.append({
            "id": idx,
            "name": tag["name"],
            "start_year": start_year,
            "end_year": end_year,
            "display_date": f"{format_year(start_year)} - {format_year(end_year)}",
            "average_year": avg_year
        })
    
    # Sort by average year
    tags_with_data.sort(key=lambda x: x["average_year"])
    
    return jsonify(tags_with_data)


if __name__ == "__main__":
    app.run(debug=True)
