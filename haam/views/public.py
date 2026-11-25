"""Pages for visitors: the map, event and tag pages, the about page and the submission flow."""

import re
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select

from haam import events, feed, seo, tag_pages
from haam.dates import format_year, parse_year_input
from haam.events import EventData, EventError
from haam.extensions import db
from haam.forms import EventForm, EventReportForm, LinkForm
from haam.models import Event, Status, Tag, event_tags
from haam.ratelimit import limit
from haam.story import tag_story as build_tag_story

bp = Blueprint("public", __name__)

RELATED_LIMIT = 8


def _map_page(embed: bool):
    """The map (or its embeddable form). ``?event=<public id>`` previews that event, not the whole map."""
    pid = request.args.get("event", type=int)
    event = events.find_approved(pid) if pid else None
    if event is None and pid:
        old = events.moved_event(pid)  # a link made with a row id, before addresses used page ids
        if old is not None:
            args = request.args.to_dict(flat=False)
            args["event"] = [str(events.public_id(old))]
            return redirect(url_for(request.endpoint, **args), 301)
    # The map starts loading its chunks straight away, without asking for the manifest.
    return render_template("map.html", manifest=feed.manifest(url_for), shared_event=event, embed=embed)


@bp.get("/")
def index():
    return _map_page(embed=False)


@bp.get("/embed")
def embed():
    """Just the map, for an <iframe> on another site (see ``security_headers`` in haam/__init__.py)."""
    return _map_page(embed=True)


def _tag_story_page(tag_id: int, embed: bool):
    """A tag played in date order; ``from``, ``to`` (years) and ``part`` (a Wikidata item) narrow it."""
    tag = db.session.get(Tag, tag_id)
    if tag is None:
        abort(404)
    part = request.args.get("part", "")
    story = build_tag_story(tag, parse_year_input(request.args.get("from", "")),
                            parse_year_input(request.args.get("to", "")), part if re.fullmatch(r"Q\d+", part) else None)
    if not story["steps"]:
        abort(404)
    return render_template("story.html", story=story, embed=embed)


@bp.get("/story/tag/<int:tag_id>")
def tag_story(tag_id: int):
    return _tag_story_page(tag_id, embed=False)


@bp.get("/embed/story/tag/<int:tag_id>")
def tag_story_embed(tag_id: int):
    return _tag_story_page(tag_id, embed=True)


def _related(event: Event) -> tuple[object | None, list[Event]]:
    """Events from the same tag (the most specific one), closest in time first."""
    if not event.tags:
        return None, []
    # An ongoing tag (no end year) runs up to this year.
    tag = min(event.tags, key=lambda t: (t.end_year if t.end_year is not None else date.today().year)
              - (t.start_year or -10**6))
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
    event = _approved_or_redirect(event_id)
    if not isinstance(event, Event):
        return event
    canonical_slug = seo.slugify(event.title)
    if slug != canonical_slug:
        return redirect(seo.event_path(event), 301)
    return _render_event(event, EventReportForm())


def _approved_or_redirect(pid: int):
    """The approved event with public id ``pid``; for an old row-id link, a redirect to the event's address."""
    event = events.find_approved(pid)
    if event is not None:
        return event
    old = events.moved_event(pid)
    if old is not None:
        return redirect(seo.event_path(old), 301)
    abort(404)


def _render_event(event: Event, report_form: EventReportForm, status: int = 200):
    tag, related = _related(event)
    return render_template(
        "event.html",
        event=event,
        tile_map=seo.tile_map(event.lat, event.lon),
        related_tag=tag,
        related=related,
        report_form=report_form,
    ), status


@bp.post("/event/<int:event_id>/report")
@limit("event-report", 5, 3600)
def report_event(event_id: int):
    """"Report a problem": what is wrong, and optionally the corrected year, date or place."""
    event = events.find_approved(event_id)
    if event is None:
        abort(404)
    form = EventReportForm()
    if not form.validate_on_submit():
        return _render_event(event, form, 400)
    events.create_report(event, form)
    flash("Thank you. An editor will look at your report.", "success")
    return redirect(seo.event_path(event) + "#report")


@bp.get("/tag/<int:tag_id>")
@bp.get("/tag/<int:tag_id>-<slug>")
def tag_page(tag_id: int, slug: str = ""):
    """A tag's landing page. A renamed tag keeps its id, so its old address redirects here.

    A merged tag's row is deleted without a trace of where it went, so its old id is a 404.
    """
    tag = db.session.get(Tag, tag_id)
    if tag is None:
        abort(404)
    if slug != seo.slugify(tag.name):
        return redirect(seo.tag_path(tag), 301)
    context = tag_pages.page(tag)
    if context is None:
        abort(404)
    return render_template("tag.html", **context)


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


def _render_preview(form: EventForm, year: int | None, dated_by_wikidata: bool | None = None):
    # dated_by_wikidata is None when unknown (no hidden value came back): no warning then.
    return render_template(
        "preview.html",
        form=form,
        tags=events.all_tags(),
        suggested=events.suggested_tag_ids(year),
        dated_by_wikidata=dated_by_wikidata,
    )


@bp.post("/submit")
@limit("submit", 10, 60)
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
        dated_by_wikidata="1" if article.dated_by_wikidata else "0",
    )
    return _render_preview(event_form, article.year, article.dated_by_wikidata)


@bp.post("/submit/confirm")
@limit("submit-confirm", 10, 60)
def confirm():
    form = EventForm()
    if not form.validate_on_submit():
        year = getattr(form.year, "year", None)
        # Only decides whether the warning is shown again; the value is never used for anything else.
        dated = {"1": True, "0": False}.get(form.dated_by_wikidata.data)
        return _render_preview(form, year, dated), 400
    try:
        event = events.submit(form.url.data, EventData.from_form(form))
    except EventError as error:
        return _render_duplicate(LinkForm(formdata=None, url=form.url.data), error), 409
    return render_template("submitted.html", event=event)
