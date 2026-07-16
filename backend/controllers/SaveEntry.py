from backend.models.model import db, Entry, Location, EventCategory

def SaveEntry(entry, modified):
    # 1 Save the entry first
    link = entry.get("link")
    existing_entry = Entry.query.filter_by(wikiLink=link).first()
    if existing_entry:
        return existing_entry
    
    # Convert category string to enum
    category_str = entry.get("category")
    category = EventCategory(category_str) if category_str else EventCategory.OTHER
    
    event = Entry(
        title=entry.get("title"),
        year=entry.get("year"),
        dateString=entry.get("date"),
        firstParagraph=entry.get("first_paragraph"),
        wikiLink=entry.get("link"),
        category=category,
        modified=modified
    )
    db.session.add(event)
    db.session.flush()  # Important: generate ID without committing

    # 2 Save the location linked to the entry
    lat = entry.get("lat")
    lon = entry.get("lon")
    coordinates = f"{lat},{lon}" 
    country = entry.get("country") or None
    on_water = entry.get("on_water", False)

    location = Location(
        coordinates=coordinates,
        country=country,
        on_water=on_water,
        entry_id=event.id
    )
    db.session.add(location)

    # 3️⃣ Commit both together
    db.session.commit()

    return event
