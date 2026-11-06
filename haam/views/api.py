"""Read-only JSON API used by the map page."""

import gzip

from flask import Blueprint, abort, jsonify, request

from haam import events
from haam.models import Category, Status

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.after_request
def compress(response):
    """Gzip larger JSON responses: the event list for the map can be several MB."""
    if (response.status_code == 200 and response.mimetype == "application/json"
            and "gzip" in request.headers.get("Accept-Encoding", "")
            and not response.direct_passthrough and "Content-Encoding" not in response.headers):
        data = response.get_data()
        if len(data) > 1024:
            response.set_data(gzip.compress(data, compresslevel=6))
            response.headers["Content-Encoding"] = "gzip"
            response.headers["Vary"] = "Accept-Encoding"
    return response


@bp.get("/health")
def health():
    return jsonify(status="ok")


@bp.get("/events")
def list_events():
    """All approved events, compact: full text comes from /api/events/<id>."""
    response = jsonify([event.to_list_dict() for event in events.approved_events()])
    response.cache_control.public = True
    response.cache_control.max_age = 60
    return response


@bp.get("/events/<int:event_id>")
def get_event(event_id: int):
    event = events.get_event_or_none(event_id)
    if event is None or event.status != Status.APPROVED:
        abort(404)
    return jsonify(event.to_dict())


@bp.get("/tags")
def list_tags():
    return jsonify([tag.to_dict() for tag in events.all_tags()])


@bp.get("/categories")
def list_categories():
    return jsonify([{"value": c.value, "label": c.label} for c in Category])
