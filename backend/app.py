import os
import threading
import logging
import requests
import time

from flask import Flask
from flask_cors import CORS

from backend.config import Config, INSTANCE_DIR
from backend.extensions import db
from backend.routes.admin import admin_bp
from backend.routes.events import events_bp
from backend.models.model import Entry, Location, EventCategory
from backend.api.WikiApi import get_wikipedia_data

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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


def auto_import_wikipedia_entries(lat_min=35, lat_max=70, lon_min=-10, lon_max=40, 
                                  grid_size=5, radius=10000, max_total=1000):
    """Automatically import Wikipedia entries with coordinates from a region."""
    logger.info("Starting automatic Wikipedia import...")
    entries_added = 0
    entries_skipped = 0
    entries_failed = 0
    entries_filtered = 0
    total_processed = 0
    
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
                
                total_processed += 1
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


def create_app(config_class=Config) -> Flask:
    os.makedirs(INSTANCE_DIR, exist_ok=True)

    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    CORS(app, origins=app.config["CORS_ORIGINS"])

    app.register_blueprint(events_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

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

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True, port=5000)
