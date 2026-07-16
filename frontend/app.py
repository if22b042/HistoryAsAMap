from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import re

from backend.controllers.CheckNewEntry import CheckEntry
from backend.controllers.SaveEntry import SaveEntry
from backend.models.model import db, Entry, Location
from backend.controllers.LocationInfoRetriever import reverse_geocode, check_on_water
WIKIPEDIA_REGEX = r"^https:\/\/([a-z]{2}\.)?wikipedia\.org\/wiki\/.*$"

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///yourdb.db"
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

    if not entry_data:
        return render_template(
            "new_entry.html",
            error="Entry could not be retrieved or already exists in the database.",
            wiki_link=wiki_link
        )

    # Add category to entry data
    entry_data['category'] = category

    # If everything is okay, show the preview page
    return render_template("submit_entry.html", entry=entry_data)


@app.route("/create_new_entry", methods=["POST"])
def create_new_entry():
    modified = request.form.get("modified") == "true"
    entry_data = CheckEntry(request.form.get("link"))
    
    # Debug: Print all form data received
    print(f"DEBUG CREATE - Form data: {dict(request.form)}")
    print(f"DEBUG CREATE - All keys: {list(request.form.keys())}")

    if not entry_data:
            return render_template(
            "new_entry.html",
            error="Entry could not be retrieved or already exists in the database.",
            wiki_link=request.form.get("link")
        )
    
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

    # Coordinates for Location class

    # Fetch values dynamically
    country = reverse_geocode(lat, lon)
    on_water = check_on_water(lat, lon)

    # Save entry (this returns the created Entry object)
    new_entry = SaveEntry(entry_data, modified)
    
    print (lon, lat, country, on_water)
    # Create location object linked to the entry
    location = Location(
        coordinates=f"{lat},{lon}",
        country=country,
        on_water=on_water,
        entry_id=new_entry.id
    )

    db.session.add(location)
    db.session.commit()

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
