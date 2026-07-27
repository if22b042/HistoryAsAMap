from backend.models.model import db, Entry, Location, EventCategory

def SaveEntry(entry, modified, existing_id=None):
    # 1 Save the entry first
    link = entry.get("link")
    
    # If existing_id is provided, update the existing entry
    if existing_id:
        existing_entry = Entry.query.get(existing_id)
        if existing_entry:
            # Update the existing entry
            category_str = entry.get("category")
            category = EventCategory(category_str) if category_str else EventCategory.OTHER
            
            existing_entry.title = entry.get("title")
            existing_entry.year = entry.get("year")
            existing_entry.dateString = entry.get("date")
            existing_entry.firstParagraph = entry.get("first_paragraph")
            existing_entry.category = category
            existing_entry.modified = modified
            
            # Update the location
            lat = entry.get("lat")
            lon = entry.get("lon")
            coordinates = f"{lat},{lon}"
            country = entry.get("country") or None
            on_water = entry.get("on_water", False)
            
            if existing_entry.location:
                existing_entry.location.coordinates = coordinates
                existing_entry.location.country = country
                existing_entry.location.on_water = on_water
            else:
                location = Location(
                    coordinates=coordinates,
                    country=country,
                    on_water=on_water,
                    entry_id=existing_entry.id
                )
                db.session.add(location)
            
            db.session.commit()
            return existing_entry
    
    # Otherwise, check for duplicate by link and return if exists
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
