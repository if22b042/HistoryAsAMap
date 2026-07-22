from functools import wraps

from flask import Blueprint, current_app, jsonify, request

from backend.services.events import (
    EventServiceError,
    approve_event,
    list_pending_events,
    reject_event,
)

admin_bp = Blueprint("admin", __name__)


def require_admin_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-Admin-Key")
        if not api_key or api_key != current_app.config["ADMIN_API_KEY"]:
            return jsonify({"error": "Unauthorized."}), 401
        return f(*args, **kwargs)

    return decorated


@admin_bp.get("/events/pending")
@require_admin_key
def pending_events():
    events = list_pending_events()
    return jsonify([e.to_dict() for e in events])


@admin_bp.patch("/events/<int:event_id>/approve")
@require_admin_key
def approve(event_id: int):
    try:
        entry = approve_event(event_id)
    except EventServiceError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(entry.to_dict())


@admin_bp.patch("/events/<int:event_id>/reject")
@require_admin_key
def reject(event_id: int):
    try:
        entry = reject_event(event_id)
    except EventServiceError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(entry.to_dict())
