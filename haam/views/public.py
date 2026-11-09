"""Pages for visitors: the map, the about page and the submission flow."""

from flask import Blueprint, render_template, url_for

from haam import events, feed
from haam.dates import format_year
from haam.events import EventData, EventError
from haam.forms import EventForm, LinkForm
from haam.models import Status

bp = Blueprint("public", __name__)


@bp.get("/")
def index():
    # The map starts loading its chunks straight away, without asking for the manifest.
    return render_template("map.html", manifest=feed.manifest(url_for))


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
