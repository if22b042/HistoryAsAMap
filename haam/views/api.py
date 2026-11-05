"""Read-only JSON API used by the map page."""

from flask import Blueprint, jsonify

from haam import events
from haam.models import Category

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify(status="ok")


@bp.get("/events")
def list_events():
    return jsonify([event.to_dict() for event in events.approved_events()])


@bp.get("/tags")
def list_tags():
    return jsonify([tag.to_dict() for tag in events.all_tags()])


@bp.get("/categories")
def list_categories():
    return jsonify([{"value": c.value, "label": c.label} for c in Category])
