"""Pages for visitors: the map, event pages, the about page and the submission flow."""

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy import func, select

from haam import events, feed, seo
from haam.dates import format_year
from haam.events import EventData, EventError
from haam.extensions import db
from haam.forms import EventForm, LinkForm
from haam.models import Event, Status, event_tags

bp = Blueprint("public", __name__)

RELATED_LIMIT = 8


def _approved_event(event_id: int) -> Event | None:
    event = db.session.get(Event, event_id)
    return event if event is not None and event.status == Status.APPROVED else None


@bp.get("/")
def index():
    # A shared link to one event (/?event=7) previews that event, not the whole map.
    event_id = request.args.get("event", type=int)
    event = _approved_event(event_id) if event_id else None
    # The map starts loading its chunks straight away, without asking for the manifest.
    return render_template("map.html", manifest=feed.manifest(url_for), shared_event=event)


def _related(event: Event) -> tuple[object | None, list[Event]]:
    """Events from the same tag (the most specific one), closest in time first."""
    if not event.tags:
        return None, []
    tag = min(event.tags, key=lambda t: (t.end_year or 10**6) - (t.start_year or -10**6))
    related = db.session.scalars(
        select(Event)
        .join(event_tags, event_tags.c.event_id == Event.id)
        .where(event_tags.c.tag_id == tag.id, Event.status == Status.APPROVED, Event.id != event.id)
        .order_by(func.abs(Event.year - event.year), Event.id)
        .limit(RELATED_LIMIT)
    ).all()
    return tag, related


@bp.get("/event/<int:event_id>")
@bp.get("/event/<int:event_id>-<slug>")
def event_page(event_id: int, slug: str = ""):
    event = _approved_event(event_id)
    if event is None:
        abort(404)
    canonical_slug = seo.slugify(event.title)
    if slug != canonical_slug:
        return redirect(url_for("public.event_page", event_id=event.id, slug=canonical_slug), 301)
    tag, related = _related(event)
    return render_template(
        "event.html",
        event=event,
        tile_map=seo.tile_map(event.lat, event.lon),
        related_tag=tag,
        related=related,
    )


@bp.get("/about")
def about():
    return render_template("about.html")


@bp.get("/submit")
def submit():
    return render_template("submit.html", form=LinkForm())


def _render_duplicate(form, error: EventError):
    existing = error.existing
    approved = existing is not None and existing.status == Status.APPROVED
    return render_template("submit.html", form=form, error=error.message,
                           existing=existing if approved else None)


def _render_preview(form: EventForm, year: int | None):
    return render_template(
        "preview.html",
        form=form,
        tags=events.all_tags(),
        suggested=events.suggested_tag_ids(year),
    )


@bp.post("/submit")
def preview():
    form = LinkForm()
    if not form.validate_on_submit():
        return render_template("submit.html", form=form), 400
    try:
        article = events.preview(form.url.data)
    except EventError as error:
        return _render_duplicate(form, error), 409 if error.existing else 400

    event_form = EventForm(
        formdata=None,
        url=article.url,
        title=article.title,
        year=format_year(article.year),
        date_label=article.date_label,
        summary=article.summary,
        lat=None if article.lat is None else round(article.lat, 6),
        lon=None if article.lon is None else round(article.lon, 6),
        category=form.category.data or "other",
    )
    return _render_preview(event_form, article.year)


@bp.post("/submit/confirm")
def confirm():
    form = EventForm()
    if not form.validate_on_submit():
        year = getattr(form.year, "year", None)
        return _render_preview(form, year), 400
    try:
        event = events.submit(form.url.data, EventData.from_form(form))
    except EventError as error:
        return _render_duplicate(LinkForm(formdata=None, url=form.url.data), error), 409
    return render_template("submitted.html", event=event)
