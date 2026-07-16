import re
import logging
from backend.models.model import db, Entry
from backend.api.WikiApi import get_wikipedia_data
import sys
# Wikipedia link validation regex
WIKIPEDIA_REGEX = r"^https:\/\/([a-z]{2}\.)?wikipedia\.org\/wiki\/.*$"

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def CheckEntry(link, tablenum=0):
    logger.info(f"=== CheckEntry called with link: {link}, tablenum: {tablenum} ===")
    
    # Validate Wikipedia link
    if not re.match(WIKIPEDIA_REGEX, link):
        logger.error(f"Invalid Wikipedia link format: {link}")
        print("Invalid Wikipedia link. Please enter a valid Wikipedia URL.")
        return False

    logger.info("Link format validation passed")

    # Use Flask app context to query the DB
    from frontend.app import app
    logger.info("Checking database for existing entry...")
    with app.app_context():
        existing_entry = Entry.query.filter_by(wikiLink=link).first()
        if existing_entry:
            logger.warning(f"Entry already exists in database - ID: {existing_entry.id}, Link: {link}")
            print(f"Entry with link '{link}' already exists in the database (ID: {existing_entry.id}).")
            return False  # stop here, entry exists

    logger.info("No existing entry found in database")

    # Get data from Wikipedia
    logger.info("Calling get_wikipedia_data...")
    entry = get_wikipedia_data(link)
    if not entry:
        logger.error("get_wikipedia_data returned None/False")
        print("Could not retrieve data from Wikipedia. Please enter details manually.")
        return False

    logger.info(f"Successfully retrieved Wikipedia data: {entry}")
    # Print the retrieved data
    print(entry)
    return entry
