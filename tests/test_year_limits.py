from datetime import date

from flask_wtf import FlaskForm

from haam.forms import OptionalYearField, YearField


class _YearForm(FlaskForm):
    year = YearField("Year")


class _OptionalYearForm(FlaskForm):
    year = OptionalYearField("Year")


def _validate(app, form_class, value):
    with app.test_request_context(method="POST", data={"year": value}):
        form = form_class()
        valid = form.validate()
        return valid, form.year.errors


def test_year_field_accepts_years_in_range(app):
    assert _validate(app, _YearForm, "1066")[0]
    assert _validate(app, _YearForm, "44 BC")[0]
    assert _validate(app, _YearForm, "10000 BC")[0]
    assert _validate(app, _YearForm, str(date.today().year))[0]


def test_year_field_rejects_years_out_of_range(app):
    too_far_back = "-10001"
    too_far_ahead = str(date.today().year + 1)
    for value in ("99999", too_far_back, too_far_ahead):
        valid, errors = _validate(app, _YearForm, value)
        assert not valid
        assert errors == [f"Enter a year between 10000 BC and {date.today().year}."]


def test_optional_year_field_rejects_years_out_of_range(app):
    valid, errors = _validate(app, _OptionalYearForm, "99999")
    assert not valid
    assert errors == [f"Enter a year between 10000 BC and {date.today().year}."]


def test_optional_year_field_still_allows_empty(app):
    assert _validate(app, _OptionalYearForm, "")[0]
    assert _validate(app, _OptionalYearForm, "1066")[0]
