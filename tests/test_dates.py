import pytest

from haam.dates import extract_date, format_year, parse_wikidata_time, parse_year_input


@pytest.mark.parametrize("text, year, label", [
    # Years below 1000 AD used to be missed entirely (old ToDo "FIX 1").
    ("The Battle of the Teutoburg Forest took place in 9 AD near modern Kalkriese.", 9, "AD 9"),
    ("The battle was fought in September AD 9 in Germania.", 9, "September AD 9"),
    ("The Battle of Hastings was fought on 14 October 1066 between the Norman-French army and the English.",
     1066, "14 October 1066"),
    ("The Battle of Stalingrad (23 August 1942 – 2 February 1943) was a major battle.", 1942, "23 August 1942"),
    ("The Battle of Vienna took place on 11–12 September 1683.", 1683, "11 September 1683"),
    ("The Battle of Thermopylae was fought in 480 BC between Greeks and Persians.", -480, "480 BC"),
    ("The Peloponnesian War (431–404 BC) was an ancient Greek war.", -431, "431 BC"),
    ("The Battle of Gettysburg was fought July 1, 1863, in Pennsylvania.", 1863, "1 July 1863"),
    ("The siege lasted from June 1453 until the city fell.", 1453, "June 1453"),
    ("The Battle of Edington was fought in 878 between Wessex and the Great Heathen Army.", 878, "AD 878"),
    ("The Battle of Marathon took place in 490 BCE.", -490, "490 BC"),
])
def test_extract_date(text, year, label):
    parsed = extract_date(text)
    assert parsed is not None
    assert (parsed.year, parsed.label) == (year, label)


def test_quantities_are_not_years():
    parsed = extract_date("About 1500 soldiers fought in the battle of 1415.")
    assert parsed.year == 1415


def test_first_paragraph_wins_over_later_text():
    text = "The treaty was signed on 4 March 1801.\nIt was revised in 1920."
    assert extract_date(text).year == 1801


def test_centuries_are_a_last_resort():
    assert extract_date("A 3rd century BC fortress.").year == -300
    assert extract_date("A 12th-century castle.").label == "12th century"


def test_no_date():
    assert extract_date("A village in Bavaria.") is None
    assert extract_date("") is None


@pytest.mark.parametrize("year, expected", [(-44, "44 BC"), (9, "AD 9"), (1066, "1066"), (None, "")])
def test_format_year(year, expected):
    assert format_year(year) == expected


@pytest.mark.parametrize("value, expected", [
    ("1066", 1066), ("-44", -44), ("44 BC", -44), ("44 bce", -44), ("AD 9", 9), ("9 CE", 9),
    (" 2001 ", 2001), ("", None), ("abc", None), ("0", None), ("-44 BC", None),
])
def test_parse_year_input(value, expected):
    assert parse_year_input(value) == expected


def test_parse_wikidata_time():
    day = parse_wikidata_time({"time": "+1066-10-14T00:00:00Z", "precision": 11})
    assert (day.year, day.label) == (1066, "14 October 1066")
    bc = parse_wikidata_time({"time": "-0480-08-00T00:00:00Z", "precision": 10})
    assert (bc.year, bc.label) == (-480, "August 480 BC")
    year_only = parse_wikidata_time({"time": "+0009-00-00T00:00:00Z", "precision": 9})
    assert (year_only.year, year_only.label) == (9, "AD 9")
    assert parse_wikidata_time({"time": "garbage"}) is None
