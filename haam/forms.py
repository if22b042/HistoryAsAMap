"""HTML forms (Flask-WTF handles CSRF protection for all of them)."""

from flask_wtf import FlaskForm
from wtforms import (
    FloatField,
    HiddenField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, ValidationError

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


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


class ActionForm(FlaskForm):
    """Empty form used only for its CSRF token on approve/reject/delete buttons."""
