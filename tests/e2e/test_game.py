"""The game: one round of the daily game and one of practice mode."""

import re

from playwright.sync_api import Page, expect


def play_round(page: Page):
    expect(page.locator("#game-round")).to_be_visible()
    expect(page.locator("#round-title")).not_to_be_empty()
    confirm = page.locator("#guess-btn")
    expect(confirm).to_be_disabled()

    game_map = page.locator("#game-map")
    box = game_map.bounding_box()
    game_map.click(position={"x": box["width"] / 2, "y": box["height"] / 2})
    expect(confirm).to_be_enabled()
    confirm.click()

    result = page.locator("#round-result")
    expect(result).to_be_visible()
    expect(page.locator("#result-points")).to_have_text(re.compile(r"^\d{1,3}(,\d{3})?$"))
    expect(page.locator("#result-distance")).to_contain_text("km")
    expect(page.locator("#game-progress li.done")).to_have_count(1)


def test_daily_round(page: Page, live_server):
    page.goto("/game")
    expect(page.locator("#game-meta")).to_contain_text("Today")
    expect(page.locator("#mode-daily")).to_have_class(re.compile(r"\bactive\b"))
    play_round(page)

    # Progress is kept in localStorage: a reload shows the round as played.
    page.reload()
    expect(page.locator("#game-progress li.done")).to_have_count(1)
    expect(page.locator("#round-num")).to_have_text("Event 2 of 5")


def test_practice_round(page: Page, live_server):
    page.goto("/game?mode=practice")
    expect(page.locator("#game-meta")).to_contain_text("Practice")
    expect(page.locator("#practice-filters")).to_be_visible()
    play_round(page)
    page.locator("#next-btn").click()
    expect(page.locator("#round-result")).to_be_hidden()
    expect(page.locator("#guess-btn")).to_be_disabled()
