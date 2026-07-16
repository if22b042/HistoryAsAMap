import re
from models.model import db, Entry
from web_scrape.Wikipedia import get_data
from api.WikiApi import get_wikipedia_data
import sys
# Wikipedia link validation regex
WIKIPEDIA_REGEX = r"^https:\/\/([a-z]{2}\.)?wikipedia\.org\/wiki\/.*$"

def add_new_entry(link, tablenum=0):


    # Get data from Wikipedia
    entry = get_wikipedia_data(link)
    print (entry)

    if not entry:
        print("Could not retrieve data from Wikipedia. Please enter details manually.")
        return False

    missing_fields = []
    if not entry ["year"]:
        missing_fields.append("Year")
        entry.added_year_manual = True

    if not entry ["date"]:
        missing_fields.append("Date")

    if not entry ["first_paragraph"]:
        missing_fields.append("Description")

    # Print extracted data
    print("\n--- Extracted Entry Data ---")
    print(f"Title: {entry ['title'] }")
    print(f"Year: {entry ['year']}")
    print(f"Date: {entry ['date']}")
    print(f"Description: {entry ['first_paragraph']}")
    print(f"Coordinates: {entry ['coordinates']}")
    print(f"Link: {entry ['link']}")
    
    if missing_fields:
        print(f"These fields could not be retrieved: {', '.join(missing_fields)}. Please enter them manually.\n")

    # Needs to be reworked for admin approval
    def get_user_approval():
        print("Do you approve this entry? (yes/no): ", end="")
        return sys.stdin.readline().strip().lower()
    approval = get_user_approval()
    coordinates=str(entry["coordinates"][0])+ " ⏐ " + str(entry["coordinates"][1])

    event = Entry(
        title=entry.get("title"),
        year=entry.get("year"),
        dateString=entry.get("date"),
        firstParagraph=entry.get("first_paragraph"),
        coordinates= coordinates,
        wikiLink=entry["link"]
    )

    db.session.add(event)
    db.session.commit()
    print("✅ Entry successfully added!")
    return True
