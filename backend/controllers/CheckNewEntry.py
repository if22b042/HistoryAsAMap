import re
import logging
from backend.models.model import db, Entry
from backend.api.WikiApi import get_wikipedia_data
from backend.utils.validators import is_valid_english_wikipedia_url
import sys

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def CheckEntry(link, tablenum=0):
    logger.info(f"=== CheckEntry called with link: {link}, tablenum: {tablenum} ===")
    
    # Validate that it's an English Wikipedia link
    if not is_valid_english_wikipedia_url(link):
        logger.error(f"Non-English Wikipedia link detected: {link}")
        return {"error": "The article must be from English Wikipedia (https://en.wikipedia.org/wiki/). Please provide an English Wikipedia article link."}

    logger.info("English Wikipedia link validation passed")

    # Use Flask app context to query the DB
    from frontend.app import app
    logger.info("Checking database for existing entry...")
    with app.app_context():
        existing_entry = Entry.query.filter_by(wikiLink=link).first()
        if existing_entry:
            logger.warning(f"Entry already exists in database - ID: {existing_entry.id}, Link: {link}")
            # Return existing entry data with a flag indicating it's a duplicate
            entry_dict = existing_entry.to_dict()
            entry_dict['is_duplicate'] = True
            entry_dict['existing_id'] = existing_entry.id
            
            # Normalize the data structure to match Wikipedia data format
            if existing_entry.location:
                coords = existing_entry.location.coordinates.split(',')
                entry_dict['coordinates'] = [float(coords[0]), float(coords[1])]
                entry_dict['lat'] = float(coords[0])
                entry_dict['lon'] = float(coords[1])
            else:
                entry_dict['coordinates'] = [None, None]
                entry_dict['lat'] = None
                entry_dict['lon'] = None
            
            entry_dict['date'] = existing_entry.dateString
            entry_dict['first_paragraph'] = existing_entry.firstParagraph
            
            return entry_dict

    logger.info("No existing entry found in database")

    # Get data from Wikipedia
    logger.info("Calling get_wikipedia_data...")
    entry = get_wikipedia_data(link)
    if not entry:
        logger.error("get_wikipedia_data returned None/False")
        return {"error": "Could not retrieve data from Wikipedia. The article may not exist or may not have coordinates."}

    logger.info(f"Successfully retrieved Wikipedia data: {entry}")
    
    # Check if both coordinates and year are missing
    if (entry.get("lat") is None or entry.get("lon") is None) and entry.get("year") is None:
        logger.error("Both coordinates and year are missing from Wikipedia data")
        return {"error": "This Wikipedia article has neither coordinates nor an extractable year. Please choose an article with both a mapped location and a clear date in the first paragraph."}
    
    # Print the retrieved data
    print(entry)
    return entry
