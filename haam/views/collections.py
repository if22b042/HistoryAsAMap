"""Map collections: gallery, creation, sharing and editing via secret links."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from haam import collections_service as service
from haam.auth import is_admin
from haam.collections_service import CollectionError, CustomEntryData
from haam.dates import format_year
from haam.forms import ActionForm, CollectionForm, CustomEntryForm, EventEntryForm, NoteForm, ReportForm

bp = Blueprint("collections", __name__, url_prefix="/collections")


@bp.after_request
def private_headers(response):
    # Collection URLs contain secret tokens: keep them out of search engines and
    # out of the Referer header sent to the (arbitrary) websites entries link to.
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _collection_or_404(view_token: str):
    collection = service.get_by_view_token(view_token)
    if collection is None:
        abort(404)
    return collection


def _editable_or_redirect(view_token: str):
    """The collection, if this browser may edit it; otherwise ``(None, redirect)``."""
    collection = _collection_or_404(view_token)
    if service.can_edit(collection):
        return collection, None
    flash("Open the collection's edit link to change it.", "error")
    return None, redirect(url_for("collections.view", view_token=view_token))


def _share_url(collection) -> str:
    return url_for("collections.view", view_token=collection.view_token, _external=True)


def _edit_url(collection) -> str | None:
    token = service.edit_token_for(collection)
    if token is None:
        return None
    return url_for("collections.claim", view_token=collection.view_token, edit_token=token, _external=True)


# ------------------------------------------------------------------ public

@bp.get("/")
def index():
    page = max(request.args.get("page", 1, type=int), 1)
    public, total = service.public_collections(page=page)
    return render_template(
        "collections/index.html",
        mine=service.my_collections(),
        public=public,
        page=page,
        pages=max((total + 23) // 24, 1),
    )


@bp.route("/new", methods=["GET", "POST"])
def new():
    form = CollectionForm()
    if form.validate_on_submit():
        collection, edit_token = service.create_collection(
            form.title.data, form.description.data or "", form.is_public.data)
        service.remember(collection, edit_token)
        flash("Collection created. Save your edit link somewhere safe – it is the only way to edit "
              "this collection from another browser.", "success")
        return redirect(url_for("collections.manage", view_token=collection.view_token))
    return render_template("collections/new.html", form=form), 400 if form.errors else 200


@bp.get("/<view_token>")
def view(view_token: str):
    collection = _collection_or_404(view_token)
    editable = service.can_edit(collection)
    if collection.is_hidden and not (editable or is_admin()):
        return render_template("error.html", code=410,
                               message="This collection has been hidden by an editor."), 410
    return render_template(
        "collections/view.html",
        collection=collection,
        editable=editable,
        share_url=_share_url(collection),
        entries_data=[entry.to_dict() for entry in collection.entries],
        report_form=ReportForm(),
    )


@bp.post("/<view_token>/report")
def report(view_token: str):
    collection = _collection_or_404(view_token)
    form = ReportForm()
    if form.validate_on_submit():
        service.report(collection, form.reason.data)
        flash("Thank you. An editor will look at this collection.", "success")
    else:
        flash("Please say briefly what is wrong.", "error")
    return redirect(url_for("collections.view", view_token=view_token))


@bp.get("/<view_token>/edit/<edit_token>")
def claim(view_token: str, edit_token: str):
    """The secret edit link: remember edit access in this browser, then open the editor."""
    collection = _collection_or_404(view_token)
    if not service.check_edit_token(collection, edit_token):
        abort(404)  # don't reveal whether the collection exists
    service.remember(collection, edit_token)
    return redirect(url_for("collections.manage", view_token=view_token))


# ----------------------------------------------------------------- editing

@bp.get("/<view_token>/manage")
def manage(view_token: str):
    collection, denied = _editable_or_redirect(view_token)
    if denied:
        return denied
    return _render_manage(collection)


def _render_manage(collection, *, settings_form=None, custom_form=None, event_form=None, status=200):
    settings_form = settings_form or CollectionForm(
        formdata=None, title=collection.title, description=collection.description,
        is_public=collection.is_public)
    return render_template(
        "collections/manage.html",
        collection=collection,
        share_url=_share_url(collection),
        edit_url=_edit_url(collection),
        settings_form=settings_form,
        custom_form=custom_form or CustomEntryForm(formdata=None),
        event_form=event_form or EventEntryForm(formdata=None),
        action_form=ActionForm(),
    ), status


@bp.post("/<view_token>/settings")
def settings(view_token: str):
    collection, denied = _editable_or_redirect(view_token)
    if denied:
        return denied
    form = CollectionForm()
    if not form.validate_on_submit():
        return _render_manage(collection, settings_form=form, status=400)
    service.update_settings(collection, form.title.data, form.description.data or "", form.is_public.data)
    flash("Settings saved.", "success")
    return redirect(url_for("collections.manage", view_token=view_token))


@bp.post("/<view_token>/entries/event")
def add_event(view_token: str):
    collection, denied = _editable_or_redirect(view_token)
    if denied:
        return denied
    form = EventEntryForm()
    if not form.validate_on_submit():
        return _render_manage(collection, event_form=form, status=400)
    try:
        entry = service.add_event(collection, form.event_id.data, form.note.data or "")
    except CollectionError as error:
        flash(error.message, "error")
        return _render_manage(collection, event_form=form, status=400)
    flash(f"Added “{entry.title}”.", "success")
    return redirect(url_for("collections.manage", view_token=view_token, _anchor="entries"))


@bp.post("/<view_token>/entries/custom")
def add_custom(view_token: str):
    collection, denied = _editable_or_redirect(view_token)
    if denied:
        return denied
    form = CustomEntryForm()
    if not form.validate_on_submit():
        return _render_manage(collection, custom_form=form, status=400)
    try:
        entry = service.add_custom(collection, CustomEntryData.from_form(form))
    except CollectionError as error:
        flash(error.message, "error")
        return _render_manage(collection, custom_form=form, status=400)
    flash(f"Added “{entry.title}”." + (" ★ Wikipedia article found." if entry.wiki_verified else ""), "success")
    return redirect(url_for("collections.manage", view_token=view_token, _anchor="entries"))


@bp.route("/<view_token>/entries/<int:entry_id>/edit", methods=["GET", "POST"])
def edit_entry(view_token: str, entry_id: int):
    collection, denied = _editable_or_redirect(view_token)
    if denied:
        return denied
    entry = service.get_entry(collection, entry_id)
    if entry is None:
        abort(404)

    if entry.is_event:
        form = NoteForm(formdata=None, note=entry.note) if request.method == "GET" else NoteForm()
    elif request.method == "GET":
        form = CustomEntryForm(
            formdata=None, title=entry.custom_title, year=format_year(entry.custom_year),
            date_label=entry.custom_date_label, category=entry.category.value,
            lat=entry.custom_lat, lon=entry.custom_lon, summary=entry.custom_summary,
            link=entry.link or "", note=entry.note)
    else:
        form = CustomEntryForm()

    if request.method == "POST" and form.validate_on_submit():
        if entry.is_event:
            service.update_note(entry, form.note.data or "")
        else:
            service.update_custom(entry, CustomEntryData.from_form(form))
        flash("Entry saved.", "success")
        return redirect(url_for("collections.manage", view_token=view_token, _anchor="entries"))
    return render_template("collections/entry_edit.html", collection=collection, entry=entry,
                           form=form), 400 if form.errors else 200


@bp.post("/<view_token>/entries/<int:entry_id>/delete")
def delete_entry(view_token: str, entry_id: int):
    collection, denied = _editable_or_redirect(view_token)
    if denied:
        return denied
    entry = service.get_entry(collection, entry_id)
    if entry is None or not ActionForm().validate_on_submit():
        abort(400)
    title = entry.title
    service.remove_entry(entry)
    flash(f"Removed “{title}”.", "success")
    return redirect(url_for("collections.manage", view_token=view_token, _anchor="entries"))


@bp.post("/<view_token>/delete")
def delete(view_token: str):
    collection, denied = _editable_or_redirect(view_token)
    if denied:
        return denied
    if not ActionForm().validate_on_submit():
        abort(400)
    service.forget(collection.id)
    service.delete_collection(collection)
    flash("Collection deleted.", "success")
    return redirect(url_for("collections.index"))


@bp.post("/<view_token>/forget")
def forget(view_token: str):
    """Stop remembering edit access in this browser (e.g. on a shared computer)."""
    collection = _collection_or_404(view_token)
    if ActionForm().validate_on_submit():
        service.forget(collection.id)
        flash("This browser no longer has edit access. You can still use your edit link.", "success")
    return redirect(url_for("collections.view", view_token=view_token))
