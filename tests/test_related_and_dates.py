from datetime import date

from haam import importer
from haam.collections_service import _touch
from haam.extensions import db
from haam.models import Collection, Event, Tag, _utcnow
from haam.views.public import _related


def test_ongoing_tag_is_measured_up_to_this_year(app, make_event):
    # "Norman Conquest" (1066-1075) is 9 years long; an ongoing tag from last year is 1 year
    # long. With no end year the tag must count up to this year, not to a million years.
    ongoing = Tag(name="Ongoing era", start_year=date.today().year - 1, end_year=None)
    db.session.add(ongoing)
    norman = db.session.scalar(db.select(Tag).filter_by(name="Norman Conquest of England"))
    event = make_event()
    event.tags = [norman, ongoing]
    db.session.commit()

    tag, _ = _related(event)
    assert tag is ongoing


def test_timestamps_are_naive_utc(app):
    assert _utcnow().tzinfo is None
    collection = Collection()
    _touch(collection)
    assert collection.updated_at.tzinfo is None


def _write_csv(tmp_path, text):
    path = tmp_path / "events.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_csv_year_override_changes_the_date_label(wiki, tmp_path):
    wiki.add("Battle of Hastings", year=1066, date_label="14 October 1066")
    path = _write_csv(tmp_path, "url,year\nhttps://en.wikipedia.org/wiki/Battle_of_Hastings,1067\n")
    importer.import_csv(path, approve=True, report=lambda message: None)
    event = db.session.scalar(db.select(Event))
    assert (event.year, event.date_label) == (1067, "1067")


def test_csv_year_equal_to_the_article_keeps_the_date_label(wiki, tmp_path):
    wiki.add("Battle of Hastings", year=1066, date_label="14 October 1066")
    path = _write_csv(tmp_path, "url,year\nhttps://en.wikipedia.org/wiki/Battle_of_Hastings,1066\n")
    importer.import_csv(path, approve=True, report=lambda message: None)
    event = db.session.scalar(db.select(Event))
    assert event.date_label == "14 October 1066"
