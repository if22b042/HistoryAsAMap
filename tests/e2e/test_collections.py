"""Collections: create one from a tag, edit it, its map and its share link."""

import re

from playwright.sync_api import Page, expect


def test_create_from_tag_edit_map_and_share(page: Page, seed, fresh_context):
    page.goto("/collections/new")
    page.locator("#title").fill("Wars against Carthage")
    page.locator("#description").fill("Rome and Carthage.")
    page.locator("#tag_id").select_option(str(seed.tag_ids["Punic Wars"]))
    page.get_by_role("button", name="Create collection").click()

    expect(page).to_have_url(re.compile(r"/collections/[^/]+/manage"))
    expect(page.locator(".flashes")).to_contain_text("Added 3 events tagged “Punic Wars”.")
    entries = page.locator("#entries .manage-entry")
    expect(entries).to_have_count(3)
    share_url = page.locator("#share-url").input_value()
    edit_url = page.locator("#edit-url").input_value()
    assert "/edit/" in edit_url

    # Remove an entry (after confirming the browser's question).
    page.once("dialog", lambda dialog: dialog.accept())
    entries.filter(has_text="Battle of Zama").get_by_role("button", name="Remove").click()
    expect(page.locator(".flashes")).to_contain_text("Removed “Battle of Zama”.")
    expect(entries).to_have_count(2)
    expect(page.locator("#entries h2")).to_contain_text("Entries (2)")

    # The collection page, then its full map with only its entries.
    page.get_by_role("link", name="View collection").click()
    expect(page.locator("#entry-list .entry-card")).to_have_count(2)
    page.get_by_role("link", name="Map view").click()
    expect(page).to_have_url(re.compile(r"/collections/[^/]+/map$"))
    expect(page.locator("#result-count")).to_have_text("2 events")
    expect(page.locator("#events-grid .event-card-title")).to_have_text(
        ["Battle of the Aegates", "Battle of Cannae"])
    expect(page.locator(".collection-banner")).to_contain_text("Wars against Carthage")

    # Someone else opens the share link: they can look, not edit.
    other = fresh_context().new_page()
    other.goto(share_url)
    expect(other.locator("h1")).to_contain_text("Wars against Carthage")
    expect(other.locator("#entry-list .entry-card")).to_have_count(2)
    expect(other.get_by_role("link", name="Edit collection")).to_have_count(0)
    other.goto(share_url + "/manage")
    expect(other).to_have_url(share_url)
    expect(other.locator(".flashes")).to_contain_text("Open the collection's edit link to change it.")


def test_public_collection_is_listed(page: Page, seed):
    page.goto("/collections/")
    card = page.locator(".collection-card", has_text=seed.public_collection_title)
    expect(card).to_be_visible()
    card.click()
    expect(page).to_have_url(re.compile(rf"/collections/{re.escape(seed.public_collection_token)}$"))
    expect(page.locator("#entry-list .entry-card")).to_have_count(3)
    expect(page.locator(".collection-meta")).to_contain_text("490 BC – 480 BC")
