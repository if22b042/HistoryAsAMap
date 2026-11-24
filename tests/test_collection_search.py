"""Searching public collections and what is inside them."""

from haam import collections_service as service
from haam.collections_service import CustomEntryData
from haam.models import Category


def make(title, description="", entries=(), public=True, hidden=False):
    collection, _ = service.create_collection(title, description, public)
    for name, year, summary, category, note in entries:
        service.add_custom(collection, CustomEntryData(
            title=name, year=year, date_label="", category=category, lat=10.0, lon=10.0,
            summary=summary, link="", note=note))
    if hidden:
        service.set_hidden(collection, True)
    return collection


def titles(hits):
    return [h.collection.title for h in hits]


def test_finds_a_word_inside_an_entry(app):
    make("Chips", entries=[("Point-contact transistor", 1947, "Built at Bell Labs", Category.SCIENTIFIC, "")])
    make("Wars", entries=[("Battle of Hastings", 1066, "Normans", Category.MILITARY, "")])
    hits, total = service.search_public("transistor")
    assert titles(hits) == ["Chips"] and total == 1
    assert [e.title for e in hits[0].entries] == ["Point-contact transistor"]


def test_every_word_must_be_found_but_may_sit_in_different_entries(app):
    make("Mixed", entries=[("Transistor", 1947, "", Category.SCIENTIFIC, ""),
                           ("Colossus", 1944, "Bletchley", Category.SCIENTIFIC, "")])
    make("Only one", entries=[("Transistor", 1947, "", Category.SCIENTIFIC, "")])
    assert titles(service.search_public("transistor bletchley")[0]) == ["Mixed"]


def test_accents_and_special_letters_are_ignored(app):
    make("Polar", entries=[("Gjøa winters", 1903, "", Category.NAVAL, ""), ("Königsberg bridges", 1736, "", Category.SCIENTIFIC, "")])
    assert titles(service.search_public("gjoa")[0]) == ["Polar"]
    assert titles(service.search_public("KONIGSBERG")[0]) == ["Polar"]
    assert titles(service.search_public("Gjøa")[0]) == ["Polar"]


def test_quoted_phrase_is_one_term(app):
    make("A", entries=[("Bell Labs transistor", 1947, "", Category.SCIENTIFIC, "")])
    make("B", entries=[("Bell tower", 1900, "labs nearby", Category.OTHER, "")])
    assert titles(service.search_public('"bell labs"')[0]) == ["A"]
    assert sorted(titles(service.search_public("bell labs")[0])) == ["A", "B"]


def test_matches_year_note_and_description(app):
    make("Old", "Notes about wire", entries=[("Telegraph", 1844, "", Category.SCIENTIFIC, "first line")])
    assert titles(service.search_public("1844")[0]) == ["Old"]
    assert titles(service.search_public("first line")[0]) == ["Old"]
    assert titles(service.search_public("wire")[0]) == ["Old"]


def test_category_and_year_filters_apply_to_entries(app):
    make("Mix", entries=[("Battle", 1066, "", Category.MILITARY, ""), ("Telescope", 1609, "", Category.SCIENTIFIC, "")])
    hits, _ = service.search_public("", category=Category.SCIENTIFIC)
    assert [e.title for e in hits[0].entries] == ["Telescope"]
    assert service.search_public("", year_from=1700)[1] == 0
    hits, _ = service.search_public("", year_from=1000, year_to=1100)
    assert [e.title for e in hits[0].entries] == ["Battle"]
    assert service.search_public("battle", category=Category.SCIENTIFIC)[1] == 0


def test_bc_years_filter_correctly(app):
    make("Ancient", entries=[("Marathon", -490, "", Category.MILITARY, "")])
    assert service.search_public("", year_from=-500, year_to=-400)[1] == 1
    assert service.search_public("", year_from=-300)[1] == 0


def test_unlisted_hidden_and_empty_collections_are_not_searched(app):
    make("Secret transistor", entries=[("Transistor", 1947, "", Category.SCIENTIFIC, "")], public=False)
    make("Hidden transistor", entries=[("Transistor", 1947, "", Category.SCIENTIFIC, "")], hidden=True)
    make("Transistor but empty")
    assert service.search_public("transistor")[1] == 0


def test_title_hits_rank_above_entry_hits_and_nothing_found_is_empty(app):
    make("Farm animals", entries=[("Mule", 1800, "", Category.OTHER, "")])
    make("Mule", entries=[("Something else", 1800, "", Category.OTHER, "")])
    assert titles(service.search_public("mule")[0])[0] == "Mule"
    assert service.search_public("zzzzqqq") == ([], 0)


def test_many_entries_show_best_ones_and_count_the_rest(app):
    make("Big", entries=[(f"Radio {i}", 1900 + i, "", Category.SCIENTIFIC, "") for i in range(10)])
    hit = service.search_public("radio")[0][0]
    assert len(hit.entries) == service.HIT_ENTRIES and hit.more == 4


def test_search_page_shows_matching_entries_with_links(client, app):
    collection = make("Chips", entries=[("Point-contact transistor", 1947, "", Category.SCIENTIFIC, "")])
    html = client.get("/collections/?q=transistor").get_data(as_text=True)
    assert "1 collection matches" in html
    assert "Point-contact transistor" in html
    entry_id = collection.entries[0].id
    assert f"/collections/{collection.view_token}#entry-{entry_id}" in html


def test_search_page_keeps_values_ignores_bad_years_and_empty_result(client, app):
    make("Chips", entries=[("Transistor", 1947, "", Category.SCIENTIFIC, "")])
    html = client.get("/collections/?q=transistor&category=scientific&year_from=abc").get_data(as_text=True)
    assert 'value="transistor"' in html and "could not be read" in html and "Transistor" in html
    assert "Nothing matches" in client.get("/collections/?q=nothinghere").get_data(as_text=True)
    assert client.get("/collections/?category=bogus").status_code == 200
    assert "Map collections" in client.get("/collections/").get_data(as_text=True)
