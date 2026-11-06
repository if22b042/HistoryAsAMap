"""Administrator pages: log in, review submissions, edit and delete events."""

from urllib.parse import urlparse

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from haam import activity, auth, collections_service, events
from haam.dates import format_year
from haam.events import EventData
from haam.forms import ActionForm, EventForm, LoginForm
from haam.extensions import db
from haam.models import Collection, Status

bp = Blueprint("admin", __name__, url_prefix="/admin")

REVIEW_PER_PAGE = 50


def _safe_next(target: str | None) -> str:
    """Only allow redirects to paths on this site."""
    if target and target.startswith("/") and not urlparse(target).netloc and not target.startswith("//"):
        return target
    return url_for("admin.review")


def _event_or_404(event_id: int):
    event = events.get_event_or_none(event_id)
    if event is None:
        abort(404)
    return event


@bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if auth.check_credentials(form.username.data, form.password.data):
            auth.log_in()
            return redirect(_safe_next(request.args.get("next")))
        flash("Wrong username or password.", "error")
    return render_template("admin/login.html", form=form)


@bp.post("/logout")
def logout():
    if ActionForm().validate_on_submit():
        auth.log_out()
    return redirect(url_for("public.index"))


@bp.get("/")
@auth.admin_required
def review():
    try:
        status = Status(request.args.get("status", Status.PENDING.value))
    except ValueError:
        abort(404)
    counts = events.status_counts()
    pages = max(1, -(-counts[status] // REVIEW_PER_PAGE))
    page = min(request.args.get("page", 1, type=int) or 1, pages)
    return render_template(
        "admin/review.html",
        events=events.events_page(status, page, REVIEW_PER_PAGE),
        status=status,
        counts=counts,
        page=max(page, 1),
        pages=pages,
        action_form=ActionForm(),
    )


@bp.get("/recent")
@auth.admin_required
def recent():
    days = request.args.get("days", 7, type=int)
    if days not in activity.PERIODS:
        days = 7
    return render_template(
        "admin/recent.html",
        activity=activity.recent_activity(days),
        days=days,
        periods=activity.PERIODS,
    )


@bp.post("/events/<int:event_id>/<any(approve, reject, delete):action>")
@auth.admin_required
def moderate(event_id: int, action: str):
    if not ActionForm().validate_on_submit():
        abort(400)
    event = _event_or_404(event_id)
    title = event.title
    if action == "approve":
        events.set_status(event, Status.APPROVED)
        flash(f"Approved “{title}”.", "success")
    elif action == "reject":
        events.set_status(event, Status.REJECTED)
        flash(f"Rejected “{title}”.", "success")
    else:
        events.delete_event(event)
        flash(f"Deleted “{title}”.", "success")
    return redirect(_safe_next(request.form.get("next")))


@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@auth.admin_required
def edit(event_id: int):
    event = _event_or_404(event_id)
    if request.method == "GET":
        form = EventForm(
            formdata=None,
            url=event.wiki_url,
            title=event.title,
            year=format_year(event.year),
            date_label=event.date_label,
            summary=event.summary,
            lat=event.lat,
            lon=event.lon,
            category=event.category.value,
            tags=[tag.id for tag in event.tags],
        )
    else:
        form = EventForm()
        if form.validate_on_submit():
            events.update_event(event, EventData.from_form(form))
            flash(f"Saved “{event.title}”.", "success")
            return redirect(url_for("admin.review", status=event.status.value))
    return render_template(
        "admin/edit.html",
        form=form,
        event=event,
        tags=events.all_tags(),
        suggested=events.suggested_tag_ids(event.year),
        action_form=ActionForm(),
    ), 400 if form.errors else 200


# ------------------------------------------------------------ collections

@bp.get("/collections")
@auth.admin_required
def collections():
    items = collections_service.all_collections()
    # Reported collections first, then most recently changed.
    items.sort(key=lambda c: (not c.reports, not c.is_public), reverse=False)
    return render_template("admin/collections.html", collections=items, action_form=ActionForm())


@bp.post("/collections/<int:collection_id>/<any(hide, unhide, delete):action>")
@auth.admin_required
def moderate_collection(collection_id: int, action: str):
    if not ActionForm().validate_on_submit():
        abort(400)
    collection = db.session.get(Collection, collection_id)
    if collection is None:
        abort(404)
    title = collection.title
    if action == "delete":
        collections_service.delete_collection(collection)
        flash(f"Deleted collection “{title}”.", "success")
    else:
        collections_service.set_hidden(collection, action == "hide")
        flash(f"{'Hid' if action == 'hide' else 'Restored'} collection “{title}”.", "success")
    return redirect(url_for("admin.collections"))
