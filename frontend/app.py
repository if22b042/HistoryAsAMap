from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
import re

from backend.controllers.CheckNewEntry import CheckEntry
from backend.controllers.SaveEntry import SaveEntry
from backend.models.model import db, Entry, Location
from backend.controllers.LocationInfoRetriever import reverse_geocode, check_on_water
WIKIPEDIA_REGEX = r"^https:\/\/([a-z]{2}\.)?wikipedia\.org\/wiki\/.*$"

import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(INSTANCE_DIR, 'yourdb.db')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
with app.app_context():
    db.create_all()

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
    if tags_str:
        import json
        try:
            entry_data["tags"] = json.loads(tags_str)
        except json.JSONDecodeError:
            entry_data["tags"] = []
    else:
        entry_data["tags"] = []
    
    # Handle tags
    tags_str = request.form.get("tags")
    if tags_str:
        import json
        try:
            entry_data["tags"] = json.loads(tags_str)
        except json.JSONDecodeError:
            entry_data["tags"] = []
    else:
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
