"""Read-only JSON API used by the map page."""

import gzip

from flask import Blueprint, abort, jsonify, request, url_for

from haam import events, feed, welcome
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
    """All approved events as objects in one response (the map uses the chunks below)."""
    response = jsonify([event.to_list_dict() for event in events.approved_events()])
    response.cache_control.public = True
    response.cache_control.max_age = 60
    return response


# ------------------------------------------------- the map's chunked data (haam.feed)

YEAR = 365 * 24 * 3600


@bp.get("/events/manifest")
def feed_manifest():
    """The current version and the URLs of every chunk (also embedded in the map page)."""
    data = feed.manifest(url_for)
    response = jsonify(data)
    response.set_etag(data["version"], weak=True)
    response.cache_control.no_cache = True
    return response.make_conditional(request)


def _versioned(version: str, key: str, build):
    """A response for a versioned URL: cached for good when ``version`` is current."""
    current = feed.state()["version"]
    response = jsonify(build(current))
    response.set_etag(f"{current}-{key}", weak=True)
    if version == current:
        # Browsers and Vercel's CDN keep it: a change to the events gives new URLs.
        response.cache_control.public = True
        response.cache_control.max_age = YEAR
        response.cache_control.s_maxage = YEAR
        response.cache_control.immutable = True
    else:
        # An outdated page asked for an old version: answer with the current data,
        # but never store it under the old URL.
        response.cache_control.no_cache = True
    return response.make_conditional(request)


def _chunk_or_404(chunk: int) -> int:
    if not 0 <= chunk < feed.CHUNKS:
        abort(404)
    return chunk


@bp.get("/events/<version>/core/<int:chunk>.json")
def feed_core(version: str, chunk: int):
    _chunk_or_404(chunk)
    return _versioned(version, f"core{chunk}", lambda current: feed.core_chunk(chunk, current))


@bp.get("/events/<version>/text/<int:chunk>.json")
def feed_text(version: str, chunk: int):
    _chunk_or_404(chunk)
    return _versioned(version, f"text{chunk}", lambda current: feed.text_chunk(chunk, current))


@bp.get("/events/<version>/tags.json")
def feed_tags(version: str):
    return _versioned(version, "tags", lambda current: [tag.to_dict() for tag in events.all_tags()])


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


@bp.get("/welcome")
def welcome_card():
    """The map's welcome card for the visitor's local day (``?month=11&day=8``)."""
    month, day = welcome.requested_day(request.args.get("month"), request.args.get("day"))
    response = jsonify(welcome.payload(month, day))
    response.cache_control.public = True
    response.cache_control.max_age = 300
    return response
