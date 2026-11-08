"""Admin: log in, approve the pending event, find it on the map."""

import re

from playwright.sync_api import Page, expect

from tests.e2e.conftest import ADMIN_PASSWORD


def test_approve_pending_event(page: Page, seed):
    title = seed.pending_title
    page.goto("/admin/")
    expect(page).to_have_url(re.compile(r"/admin/login"))
    page.locator("#username").fill("admin")
    page.locator("#password").fill(ADMIN_PASSWORD)
    page.get_by_role("button", name="Log in").click()

    expect(page.get_by_role("heading", name="Review events")).to_be_visible()
    card = page.locator(".review-card", has_text=title)
    expect(card).to_be_visible()
    card.get_by_role("button", name="Approve").click()
    expect(page.locator(".flashes")).to_contain_text(f"Approved “{title}”.")
    expect(page.locator(".review-card", has_text=title)).to_have_count(0)

    page.goto("/?q=Vesuvius")
    expect(page.locator("#result-count")).to_have_text(re.compile(r"^1 of \d+ events$"))
    page.locator("#events-grid .event-card-main", has_text=title).click()
    expect(page.locator("#sidebar .detail-title")).to_have_text(title)
    expect(page.locator("#sidebar .detail-meta")).to_contain_text("Natural")


def test_wrong_password_is_refused(page: Page, live_server):
    page.goto("/admin/login")
    page.locator("#username").fill("admin")
    page.locator("#password").fill("not the password")
    page.get_by_role("button", name="Log in").click()
    expect(page.locator(".flashes")).to_contain_text("Wrong username or password.")
