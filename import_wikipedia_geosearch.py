import requests
import time
import sys
import logging
from flask import Flask
from backend.models.model import db, Entry, Location, EventCategory
from backend.config import Config
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
    """
    Search for Wikipedia articles with coordinates within a radius of a point.
    
    Args:
        lat: Latitude of center point
        lon: Longitude of center point
        radius: Search radius in meters (default: 10000 = 10km)
        limit: Maximum number of results (max 500)
        namespace: Wikipedia namespace (0 = main articles)
    
    Returns:
        List of page titles with coordinates
    """
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
        time.sleep(1)  # Rate limiting
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        pages = data.get("query", {}).get("geosearch", [])
        logger.info(f"Found {len(pages)} pages near ({lat}, {lon})")
        return pages
        
    except Exception as e:
        logger.error(f"Error in geosearch: {e}")
        return []

def import_wikipedia_entries_by_region(lat_min, lat_max, lon_min, lon_max, 
                                       grid_size=5, radius=10000, max_total=None):
    """
    Import Wikipedia entries with coordinates from a geographic region.
    
    Args:
        lat_min, lat_max: Latitude bounds
        lon_min, lon_max: Longitude bounds
        grid_size: Size of grid cells in degrees
        radius: Search radius for each grid point in meters
        max_total: Maximum total entries to import (None for unlimited)
    """
    # Initialize Flask app
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    
    with app.app_context():
        entries_added = 0
        entries_skipped = 0
        entries_failed = 0
        entries_filtered = 0
        total_processed = 0
        
        # Generate grid points
        lat_steps = int((lat_max - lat_min) / grid_size) + 1
        lon_steps = int((lon_max - lon_min) / grid_size) + 1
        
        logger.info(f"Scanning region: lat [{lat_min}, {lat_max}], lon [{lon_min}, {lon_max}]")
        logger.info(f"Grid size: {grid_size}°, Grid points: {lat_steps} x {lon_steps} = {lat_steps * lon_steps}")
        
        for lat_i in range(lat_steps):
            for lon_j in range(lon_steps):
                if max_total and entries_added >= max_total:
                    logger.info(f"Reached max total limit of {max_total} entries")
                    break
                
                lat = lat_min + (lat_i * grid_size)
                lon = lon_min + (lon_j * grid_size)
                
                logger.info(f"Scanning grid point ({lat:.2f}, {lon:.2f})")
                
                # Get pages with coordinates near this point
                pages = geosearch_wikipedia(lat, lon, radius=radius)
                
                for page in pages:
                    if max_total and entries_added >= max_total:
                        break
                    
                    total_processed += 1
                    title = page.get("title")
                    wiki_link = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                    
                    # Check if entry already exists
                    existing_entry = Entry.query.filter_by(wikiLink=wiki_link).first()
                    if existing_entry:
                        logger.debug(f"Skipping: already exists - {title}")
                        entries_skipped += 1
                        continue
                    
                    # Fetch full Wikipedia data
                    logger.info(f"Fetching data for: {title}")
                    wiki_data = get_wikipedia_data(wiki_link)
                    
                    if not wiki_data:
                        logger.warning(f"Failed to fetch data for: {title}")
                        entries_failed += 1
                        continue
                    
                    # Skip entries without coordinates or year
                    if not wiki_data.get("lat") or not wiki_data.get("lon"):
                        logger.warning(f"Skipping {title}: no coordinates")
                        entries_failed += 1
                        continue
                    
                    if wiki_data.get("year") is None:
                        logger.warning(f"Skipping {title}: no year detected")
                        entries_failed += 1
                        continue
                    
                    # Filter out towns, cities, villages - only keep historical events
                    extract = wiki_data.get("first_paragraph", "")
                    if not is_historical_event(title, extract):
                        entries_filtered += 1
                        continue
                    
                    # Parse year (convert to int, handle BC years)
                    year = wiki_data.get("year")
                    if year is not None:
                        try:
                            year = int(year)
                        except (ValueError, TypeError):
                            year = None
                    
                    # Create entry
                    entry = Entry(
                        title=wiki_data.get("title"),
                        year=year,
                        dateString=wiki_data.get("date") or "Unknown date",
                        firstParagraph=wiki_data.get("first_paragraph") or "No description available.",
                        wikiLink=wiki_link,
                        category=EventCategory.OTHER,  # Default category
                        used=False
                    )
                    
                    db.session.add(entry)
                    db.session.flush()  # Generate ID without committing
                    
                    # Create location if coordinates available
                    lat_coord = wiki_data.get("lat")
                    lon_coord = wiki_data.get("lon")
                    
                    if lat_coord and lon_coord:
                        location = Location(
                            coordinates=f"{lat_coord},{lon_coord}",
                            country=None,  # Could be added later
                            on_water=False,  # Could be detected later
                            entry_id=entry.id
                        )
                        db.session.add(location)
                    
                    db.session.commit()
                    entries_added += 1
                    logger.info(f"Added entry {entries_added}: {title}")
                    
                    # Rate limiting between entries
                    time.sleep(0.5)
                
                # Small delay between grid points
                time.sleep(1)
        
        logger.info("\n" + "="*50)
        logger.info("Import complete!")
        logger.info(f"Total processed: {total_processed}")
        logger.info(f"Entries added: {entries_added}")
        logger.info(f"Entries skipped (already exist): {entries_skipped}")
        logger.info(f"Entries failed: {entries_failed}")
        logger.info(f"Entries filtered (non-events): {entries_filtered}")
        logger.info("="*50)

def import_wikipedia_entries_by_list(page_titles, max_total=None):
    """
    Import Wikipedia entries from a list of page titles.
    
    Args:
        page_titles: List of Wikipedia page titles
        max_total: Maximum total entries to import (None for unlimited)
    """
    # Initialize Flask app
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    
    with app.app_context():
        entries_added = 0
        entries_skipped = 0
        entries_failed = 0
        entries_filtered = 0
        
        logger.info(f"Processing {len(page_titles)} page titles")
        
        for title in page_titles:
            if max_total and entries_added >= max_total:
                logger.info(f"Reached max total limit of {max_total} entries")
                break
            
            wiki_link = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            
            # Check if entry already exists
            existing_entry = Entry.query.filter_by(wikiLink=wiki_link).first()
            if existing_entry:
                logger.debug(f"Skipping: already exists - {title}")
                entries_skipped += 1
                continue
            
            # Fetch full Wikipedia data
            logger.info(f"Fetching data for: {title}")
            wiki_data = get_wikipedia_data(wiki_link)
            
            if not wiki_data:
                logger.warning(f"Failed to fetch data for: {title}")
                entries_failed += 1
                continue
            
            # Skip entries without coordinates or year
            if not wiki_data.get("lat") or not wiki_data.get("lon"):
                logger.warning(f"Skipping {title}: no coordinates")
                entries_failed += 1
                continue
            
            if wiki_data.get("year") is None:
                logger.warning(f"Skipping {title}: no year detected")
                entries_failed += 1
                continue
            
            # Filter out towns, cities, villages - only keep historical events
            extract = wiki_data.get("first_paragraph", "")
            if not is_historical_event(title, extract):
                entries_filtered += 1
                continue
            
            # Parse year
            year = wiki_data.get("year")
            if year is not None:
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    year = None
            
            # Create entry
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
            
            # Create location if coordinates available
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
            
            # Rate limiting
            time.sleep(0.5)
        
        logger.info("\n" + "="*50)
        logger.info("Import complete!")
        logger.info(f"Entries added: {entries_added}")
        logger.info(f"Entries skipped: {entries_skipped}")
        logger.info(f"Entries failed: {entries_failed}")
        logger.info(f"Entries filtered (non-events): {entries_filtered}")
        logger.info("="*50)

if __name__ == "__main__":
    print("Wikipedia GeoSearch Import Script")
    print("="*50)
    print("\nUsage modes:")
    print("1. Region-based scan: python import_wikipedia_geosearch.py region <lat_min> <lat_max> <lon_min> <lon_max> [grid_size] [radius] [max_total]")
    print("2. List-based import: python import_wikipedia_geosearch.py list <title1> <title2> ...")
    print("\nExamples:")
    print("  # Scan Europe (approximate bounds)")
    print("  python import_wikipedia_geosearch.py region 35 70 -10 40 5 10000 100")
    print("  # Import specific pages")
    print("  python import_wikipedia_geosearch.py list 'Battle of Verdun' 'D-Day' 'Fall of Berlin'")
    
    if len(sys.argv) < 2:
        sys.exit(1)
    
    mode = sys.argv[1].lower()
    
    if mode == "region":
        if len(sys.argv) < 6:
            print("Error: Region mode requires lat_min, lat_max, lon_min, lon_max")
            sys.exit(1)
        
        lat_min = float(sys.argv[2])
        lat_max = float(sys.argv[3])
        lon_min = float(sys.argv[4])
        lon_max = float(sys.argv[5])
        grid_size = float(sys.argv[6]) if len(sys.argv) > 6 else 5
        radius = int(sys.argv[7]) if len(sys.argv) > 7 else 10000
        max_total = int(sys.argv[8]) if len(sys.argv) > 8 else None
        
        import_wikipedia_entries_by_region(lat_min, lat_max, lon_min, lon_max, 
                                           grid_size, radius, max_total)
    
    elif mode == "list":
        if len(sys.argv) < 3:
            print("Error: List mode requires at least one page title")
            sys.exit(1)
        
        page_titles = sys.argv[2:]
        import_wikipedia_entries_by_list(page_titles)
    
    else:
        print(f"Error: Unknown mode '{mode}'")
        sys.exit(1)
