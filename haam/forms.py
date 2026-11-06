"""HTML forms (Flask-WTF handles CSRF protection for all of them)."""

from urllib.parse import urlparse

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    FloatField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional, ValidationError

from haam.dates import parse_year_input
from haam.models import Category
from haam.wikipedia import title_from_url

CATEGORY_CHOICES = [(c.value, c.label) for c in Category]


def _english_wikipedia_url(form, field):
    if title_from_url(field.data or "") is None:
        raise ValidationError("Enter an English Wikipedia article link (https://en.wikipedia.org/wiki/...).")


class YearField(StringField):
    """Text field that accepts '1066', '-44', '44 BC', 'AD 9' and stores an int in ``.year``."""

    def pre_validate(self, form):
        self.year = parse_year_input(self.data or "")
        if self.year is None:
            raise ValidationError("Enter a year such as 1066, 44 BC or AD 9.")


class LinkForm(FlaskForm):
    url = StringField("Wikipedia link", validators=[DataRequired(), _english_wikipedia_url])
    category = SelectField("Category", choices=[("", "Select a category…")] + CATEGORY_CHOICES, default="")


class EventForm(FlaskForm):
    url = HiddenField(validators=[DataRequired(), _english_wikipedia_url])
    title = StringField("Title", validators=[DataRequired(), Length(max=300)])
    year = YearField("Year")
    date_label = StringField("Date", validators=[Length(max=120)])
    summary = TextAreaField("Description", validators=[DataRequired(), Length(max=5000)])
    lat = FloatField("Latitude", validators=[InputRequired(), NumberRange(-90, 90)])
    lon = FloatField("Longitude", validators=[InputRequired(), NumberRange(-180, 180)])
    category = SelectField("Category", choices=CATEGORY_CHOICES, validators=[DataRequired()])
    tags = SelectMultipleField("Tags", coerce=int, validate_choice=False)


def _web_link(form, field):
    value = (field.data or "").strip()
    if not value:
        return
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or any(c.isspace() for c in value):
        raise ValidationError("Enter a full web address starting with http:// or https://.")


class CollectionForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    description = TextAreaField("Description", validators=[Length(max=5000)])
    is_public = BooleanField("List this collection on the public Collections page")


class OptionalYearField(StringField):
    """Like YearField, but may be left empty (``.year`` is then None)."""

    def pre_validate(self, form):
        self.year = parse_year_input(self.data) if (self.data or "").strip() else None
        if (self.data or "").strip() and self.year is None:
            raise ValidationError("Enter a year such as 1066, 44 BC or AD 9, or leave it empty.")


class TagEntriesForm(FlaskForm):
    """Add all events of an official tag (optionally only some years) to a collection."""

    tag_id = SelectField("Tag", coerce=int, validate_choice=False)
    year_from = OptionalYearField("From year")
    year_to = OptionalYearField("To year")


class NewCollectionForm(CollectionForm):
    """A new collection, optionally starting with all events of a tag."""

    tag_id = SelectField("Start with the events of a tag (optional)", coerce=int, validate_choice=False, default=0)
    year_from = OptionalYearField("From year")
    year_to = OptionalYearField("To year")


class EntryEventEditForm(FlaskForm):
    """A main-map event in a collection: a note, and optionally other coordinates."""

    note = TextAreaField("Your note", validators=[Length(max=2000)])
    lat = FloatField("Latitude", validators=[Optional(), NumberRange(-90, 90)])
    lon = FloatField("Longitude", validators=[Optional(), NumberRange(-180, 180)])


class CustomEntryForm(FlaskForm):
    """An entry that exists only inside one collection (not reviewed)."""

    title = StringField("Title", validators=[DataRequired(), Length(max=300)])
    year = YearField("Year")
    date_label = StringField("Date", validators=[Length(max=120)])
    category = SelectField("Category", choices=CATEGORY_CHOICES, default="other")
    lat = FloatField("Latitude", validators=[InputRequired(message="Click the map to choose a place."),
                                             NumberRange(-90, 90)])
    lon = FloatField("Longitude", validators=[InputRequired(message="Click the map to choose a place."),
                                              NumberRange(-180, 180)])
    summary = TextAreaField("Description", validators=[Length(max=5000)])
    link = StringField("Source link", validators=[Length(max=500), _web_link])
    note = TextAreaField("Your note", validators=[Length(max=2000)])


class EventEntryForm(FlaskForm):
    """Add an approved event from the main map to a collection."""

    event_id = IntegerField(validators=[InputRequired(message="Choose an event from the list.")])
    note = TextAreaField("Your note", validators=[Length(max=2000)])


class NoteForm(FlaskForm):
    note = TextAreaField("Your note", validators=[Length(max=2000)])


class ReportForm(FlaskForm):
    reason = TextAreaField("What is wrong with this collection?", validators=[DataRequired(), Length(max=500)])


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


class ActionForm(FlaskForm):
    """Empty form used only for its CSRF token on approve/reject/delete buttons."""
