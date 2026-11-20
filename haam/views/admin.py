"""Administrator pages: log in, review submissions, edit and delete events."""

from urllib.parse import urlparse

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from haam import activity, auth, collections_service, events
from haam.dates import format_year
from haam.events import EventData
from haam.forms import ActionForm, EventForm, LoginForm
from haam.extensions import db
from haam.models import Collection, EventReport, ReportStatus, Status, Tag
from haam.ratelimit import limit

bp = Blueprint("admin", __name__, url_prefix="/admin")

REVIEW_PER_PAGE = 50
COLLECTIONS_PER_PAGE = 20


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
@limit("admin-login", 5, 60, methods=("POST",))
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
        open_reports=events.open_report_count(),
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


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@bp.post("/events/bulk/<any(approve, reject):action>")
@auth.admin_required
def bulk_moderate(action: str):
    if not ActionForm().validate_on_submit():
        abort(400)
    ids = [i for i in (_int_or_none(v) for v in request.form.getlist("event_ids")) if i is not None]
    if not ids:
        flash("Select at least one event first.", "error")
    else:
        status = Status.APPROVED if action == "approve" else Status.REJECTED
        changed = events.bulk_set_status(ids, status)
        flash(f"{'Approved' if action == 'approve' else 'Rejected'} {changed} event{'s' if changed != 1 else ''}.",
              "success")
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
    page = max(request.args.get("page", 1, type=int), 1)
    items, total = collections_service.all_collections(page=page, per_page=COLLECTIONS_PER_PAGE)
    # Reported collections first, then public ones, then most recently changed.
    return render_template("admin/collections.html", collections=items, action_form=ActionForm(), page=page,
                           pages=max((total + COLLECTIONS_PER_PAGE - 1) // COLLECTIONS_PER_PAGE, 1))


@bp.post("/collections/<int:collection_id>/<any(hide, unhide, feature, unfeature, delete):action>")
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
    elif action in ("feature", "unfeature"):
        collection.is_featured = action == "feature"
        db.session.commit()
        flash(f"{'Featured' if collection.is_featured else 'Unfeatured'} collection “{title}”.", "success")
    else:
        collections_service.set_hidden(collection, action == "hide")
        flash(f"{'Hid' if action == 'hide' else 'Restored'} collection “{title}”.", "success")
    return redirect(url_for("admin.collections"))


# ---------------------------------------------------------------- reports

@bp.get("/reports")
@auth.admin_required
def reports():
    return render_template("admin/reports.html", reports=events.open_reports(), action_form=ActionForm())


@bp.post("/reports/<int:report_id>/<any(apply, dismiss):action>")
@auth.admin_required
def moderate_report(report_id: int, action: str):
    if not ActionForm().validate_on_submit():
        abort(400)
    report = db.session.get(EventReport, report_id)
    if report is None:
        abort(404)
    if report.status != ReportStatus.OPEN:
        flash("This report was already handled.", "error")
    elif action == "apply":
        event = events.apply_report(report)
        flash(f"Applied the report to “{event.title}”.", "success")
    else:
        events.dismiss_report(report)
        flash("Dismissed the report.", "success")
    return redirect(url_for("admin.reports"))


# ------------------------------------------------------------------- tags

@bp.get("/tags")
@auth.admin_required
def tags():
    rows = events.tag_rows()
    return render_template("admin/tags.html", rows=rows, curated=events.curated_tag_names(),
                           empty=sum(1 for r in rows if r.total == 0), action_form=ActionForm())


@bp.post("/tags/new")
@auth.admin_required
def create_tag():
    if not ActionForm().validate_on_submit():
        abort(400)
    try:
        tag = events.create_tag(request.form.get("name"), _int_or_none(request.form.get("start_year")),
                                _int_or_none(request.form.get("end_year")))
        flash(f"Created the tag “{tag.name}”.", "success")
    except events.TagError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.tags"))


@bp.post("/tags/<int:tag_id>/<any(rename, delete, merge):action>")
@auth.admin_required
def moderate_tag(tag_id: int, action: str):
    if not ActionForm().validate_on_submit():
        abort(400)
    tag = db.session.get(Tag, tag_id)
    if tag is None:
        abort(404)
    name = tag.name
    curated = name in events.curated_tag_names()
    try:
        if action == "rename":
            events.rename_tag(tag, request.form.get("name"))
            flash(f"Renamed “{name}” to “{tag.name}”." + (
                " It is a curated tag: its tree and seed-tags still know it by the old name." if curated else ""),
                "success")
        elif action == "delete":
            events.delete_empty_tag(tag)
            flash(f"Deleted the tag “{name}”." + (
                " seed-tags will add it again when it is next run." if curated else ""), "success")
        else:
            target_id = _int_or_none(request.form.get("target"))
            target = db.session.get(Tag, target_id) if target_id is not None else None
            if target is None:
                raise events.TagError("Choose the tag to merge into.")
            target_name = target.name
            moved = events.merge_tags(tag, target)
            flash(f"Merged “{name}” into “{target_name}” ({moved} event{'s' if moved != 1 else ''} moved).",
                  "success")
    except events.TagError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.tags"))
