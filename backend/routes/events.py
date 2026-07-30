from flask import Blueprint, jsonify, request
import sys
import os

from backend.models.event import EntryStatus
from backend.services.events import (
    EventServiceError,
    create_event,
    get_event,
    list_events,
    preview_event,
)

events_bp = Blueprint("events", __name__)


def _error_response(exc: EventServiceError):
    return jsonify({"error": exc.message}), exc.status_code


@events_bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@events_bp.get("/events")
def get_events():
    year_from = request.args.get("year_from", type=int)
    year_to = request.args.get("year_to", type=int)
    category = request.args.get("category")

    events = list_events(
        status=EntryStatus.APPROVED,
        year_from=year_from,
        year_to=year_to,
        category=category,
    )
    return jsonify([e.to_dict() for e in events])


@events_bp.get("/events/<int:event_id>")
def get_event_by_id(event_id: int):
    try:
        event = get_event(event_id, approved_only=True)
    except EventServiceError as exc:
        return _error_response(exc)
    return jsonify(event.to_dict())


@events_bp.post("/events/preview")
def preview():
    data = request.get_json(silent=True) or {}
    wiki_link = data.get("wiki_link", "").strip()

    if not wiki_link:
        return jsonify({"error": "wiki_link is required."}), 400

    try:
        result = preview_event(wiki_link)
    except EventServiceError as exc:
        return _error_response(exc)

    return jsonify(result)


@events_bp.post("/events")
def submit_event():
    data = request.get_json(silent=True) or {}

    try:
        entry = create_event(data)
    except EventServiceError as exc:
        return _error_response(exc)

    return jsonify(entry.to_dict()), 201


@events_bp.get("/tags")
def get_tags():
    # Import tags from the add_tags.py file
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
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

