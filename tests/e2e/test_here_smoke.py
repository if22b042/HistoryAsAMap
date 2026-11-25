"""'What happened here?' in a real browser: all years, radius, back to the list, phone."""

import pytest

expect = pytest.importorskip("playwright.sync_api").expect

JERUSALEM = "31.778,35.229"


def test_what_happened_here_lists_all_years_and_comes_back(chromium, live_url):
    page = chromium.new_page(viewport={"width": 1280, "height": 800})
    # The years 1900–2000 are selected, yet the list has every era.
    page.goto(f"{live_url}/?here={JERUSALEM},25&from=1900&to=2000")
    card = page.locator("#here")
    expect(card).to_be_visible()
    titles = page.locator("#here-list .welcome-event-title")
    expect(titles).to_have_text(["Siege of Jerusalem (587 BC)", "Siege of Jerusalem (70 CE)", "Siege of Jerusalem (1187)"])
    expect(page.locator(".here-century > span:first-child")).to_have_text(
        ["6th century BC", "1st century", "12th century"])

    page.locator(".here-radius button[data-km='100']").click()
    expect(titles).to_have_count(4)
    expect(page.locator(".here-radius button[data-km='100']")).to_have_attribute("aria-pressed", "true")
    assert "here=31.778%2C35.229%2C100" in page.url

    # Opening an event hides the card; closing the details brings it back, focus on that row.
    row = page.locator("#here-list .welcome-event").nth(1)
    row.click()
    expect(page.locator("#sidebar")).to_be_visible()
    expect(card).to_be_hidden()
    page.locator("#sidebar-close").click()
    expect(card).to_be_visible()
    expect(row).to_be_focused()

    page.keyboard.press("Escape")
    expect(card).to_be_hidden()
    assert "here=" not in page.url
    page.close()


def test_what_happened_here_on_a_phone(chromium, live_url):
    page = chromium.new_page(viewport={"width": 375, "height": 812}, has_touch=True)
    page.goto(f"{live_url}/?view=9/{JERUSALEM.replace(',', '/')}")
    welcome = page.locator("#welcome")
    if welcome.is_visible():  # the first visit opens the welcome card
        page.locator("#welcome-close").click()
    pill = page.locator("#here-open")
    expect(pill).to_have_text("Here", use_inner_text=True)
    expect(pill).to_have_attribute("aria-label", "What happened here?")
    pill.click()
    card = page.locator("#here")
    expect(card).to_be_visible()
    expect(page.locator("#here-list .welcome-event")).to_have_count(3)
    box = card.bounding_box()
    assert box["y"] > 812 * 0.4 and box["y"] + box["height"] <= 812 + 1  # a bottom sheet, map above it
    page.close()
