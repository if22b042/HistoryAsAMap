"""The main map: filters, tags, search, event details and links that carry them."""

import re

from playwright.sync_api import Page, expect


def open_map(page: Page, path: str = "/"):
    page.goto(path)
    # map.js has loaded the events once the count is shown.
    expect(page.locator("#result-count")).to_have_text(re.compile(r"\d+ events$"))


def count(page: Page):
    return page.locator("#result-count")


def card_titles(page: Page):
    return page.locator("#events-grid .event-card-title")


def test_filters_details_and_history(page: Page, seed):
    open_map(page)
    # Not fixed: the admin test may have approved one more event already.
    total = int(count(page).inner_text().split()[0])
    assert total >= seed.approved_count

    # Category: only updates the current address.
    page.locator('.category-btn[data-category="military"]').click()
    expect(page.locator('.category-btn[data-category="military"]')).to_have_attribute("aria-pressed", "true")
    expect(count(page)).to_have_text(re.compile(rf"^\d+ of {total} events$"))
    military_count = count(page).inner_text()
    expect(page).to_have_url(re.compile(r"\?cat=military$"))

    # A tag: a new history entry, ?tag= in the address, a chip.
    napoleonic = seed.tag_ids["Napoleonic Wars"]
    page.locator("#tag-filter").select_option(str(napoleonic))
    expect(page).to_have_url(re.compile(rf"[?&]tag={napoleonic}(&|$)"))
    chips = page.locator("#filters [data-tag-chips]")
    expect(chips).to_contain_text("Napoleonic Wars")
    expect(count(page)).to_have_text(f"3 of {total} events")  # Austerlitz, Borodino, Waterloo

    # Search.
    page.locator("#search").fill("Waterloo")
    expect(count(page)).to_have_text(f"1 of {total} events")
    expect(page).to_have_url(re.compile(r"[?&]q=Waterloo(&|$)"))
    expect(card_titles(page)).to_have_text(["Battle of Waterloo"])

    # Open the event: details panel and ?event=.
    page.locator("#events-grid .event-card-main", has_text="Battle of Waterloo").click()
    sidebar = page.locator("#sidebar")
    expect(sidebar).to_be_visible()
    expect(sidebar.locator(".detail-title")).to_have_text("Battle of Waterloo")
    # The full text is fetched from /api/events/<id>.
    expect(sidebar.locator(".detail-summary")).to_contain_text("took place in 18 June 1815")
    expect(page).to_have_url(re.compile(rf"[?&]event={seed.event_ids['Battle of Waterloo']}(&|$)"))

    # Back: the state before the tag was chosen (military, no tag, no search).
    page.go_back()
    expect(page).to_have_url(re.compile(r"\?cat=military$"))
    expect(chips).to_be_hidden()
    expect(page.locator("#search")).to_have_value("")
    expect(page.locator('.category-btn[data-category="military"]')).to_have_attribute("aria-pressed", "true")
    expect(count(page)).to_have_text(military_count)

    # Forward: tag, search and category again.
    page.go_forward()
    expect(chips).to_contain_text("Napoleonic Wars")
    expect(page.locator("#search")).to_have_value("Waterloo")
    expect(page.locator('.category-btn[data-category="military"]')).to_have_attribute("aria-pressed", "true")
    expect(count(page)).to_have_text(f"1 of {total} events")

    # Closing the details removes ?event=.
    page.goto(page.url)  # reload: the ?event= in the address opens the panel again
    expect(sidebar.locator(".detail-title")).to_have_text("Battle of Waterloo")
    page.locator("#sidebar-close").click()
    expect(sidebar).to_be_hidden()
    expect(page).not_to_have_url(re.compile(r"[?&]event="))


def test_shared_link_applies_tag_and_search(page: Page, seed):
    civil_war = seed.tag_ids["American Civil War"]
    open_map(page, f"/?tag={civil_war}&q=Gettysburg")
    expect(page.locator("#filters [data-tag-chips]")).to_contain_text("American Civil War")
    expect(page.locator("#search")).to_have_value("Gettysburg")
    expect(count(page)).to_have_text(re.compile(r"^1 of \d+ events$"))
    expect(card_titles(page)).to_have_text(["Battle of Gettysburg"])
    expect(page.locator("#tag-filter")).to_contain_text("Add another tag")

    # Removing the tag leaves the search.
    page.get_by_role("button", name="Remove the tag American Civil War").first.click()
    expect(page).not_to_have_url(re.compile(r"[?&]tag="))
    expect(card_titles(page)).to_have_text(["Battle of Gettysburg"])


def test_bc_years_and_large_search(page: Page, seed):
    open_map(page, f"/?tag={seed.tag_ids['Punic Wars']}")
    expect(page.locator("#year-from")).to_have_value("241 BC")
    expect(page.locator("#year-to")).to_have_value("202 BC")
    expect(card_titles(page)).to_have_text(["Battle of the Aegates", "Battle of Cannae", "Battle of Zama"])

    page.locator("#search-expand").click()
    big = page.locator("#search-big")
    expect(big).to_be_focused()
    big.fill("Cannae")
    results = page.locator("#search-results .search-result")
    expect(results).to_have_count(1)
    big.press("Enter")
    expect(page.locator("#search-panel")).to_be_hidden()
    expect(page.locator("#sidebar .detail-title")).to_have_text("Battle of Cannae")
