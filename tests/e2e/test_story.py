"""Story mode: a collection and a tag played step by step, as a link and in an iframe."""

import re

from playwright.sync_api import Page, expect


def _story(seed) -> str:
    return f"/collections/{seed.public_collection_token}/story"


def test_collection_story_steps_with_keys_and_the_steps_menu(page: Page, seed):
    page.goto(_story(seed))
    intro = page.locator("#story-intro")
    expect(intro).to_be_visible()
    expect(intro).to_contain_text(seed.public_collection_title)
    page.get_by_role("button", name="Start").click()

    counter = page.locator("#story-counter")
    title = page.locator("#story-caption .story-step-title")
    expect(counter).to_have_text("1 / 3")
    expect(title).to_have_text("Battle of Marathon")
    expect(intro).to_be_hidden()
    # The focus leaves the hidden Start button for the caption, so Space reaches the story's keys.
    expect(page.locator("#story-caption")).to_be_focused()

    page.keyboard.press("ArrowRight")
    expect(counter).to_have_text("2 / 3")
    expect(title).to_have_text("Battle of Salamis")
    expect(page).to_have_url(re.compile(r"[?&]step=2\b"))
    expect(page.locator("path.story-path")).to_have_count(1)  # collections show the path by default

    page.keyboard.press("ArrowLeft")
    expect(counter).to_have_text("1 / 3")

    play = page.get_by_role("button", name="Play the story")
    page.keyboard.press("Space")
    expect(page.get_by_role("button", name="Pause the story")).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("Space")
    expect(play).to_have_attribute("aria-pressed", "false")

    page.get_by_role("button", name="Steps").click()
    steps = page.locator("#story-steps")
    expect(steps).to_be_visible()
    steps.get_by_role("button", name=re.compile("Thermopylae")).click()
    expect(steps).to_be_hidden()
    expect(counter).to_have_text("3 / 3")
    expect(page.get_by_role("button", name="Next step")).to_be_disabled()


def test_a_step_link_opens_that_step(page: Page, seed):
    page.goto(_story(seed) + "?step=3")
    expect(page.locator("#story-intro")).to_be_hidden()
    expect(page.locator("#story-counter")).to_have_text("3 / 3")
    expect(page.locator("#story-caption .story-step-title")).to_have_text("Battle of Thermopylae")


def test_reduced_motion_moves_without_flying(page: Page, seed):
    page.emulate_media(reduced_motion="reduce")
    page.goto(_story(seed) + "?step=1")
    page.get_by_role("button", name="Next step").click()
    expect(page.locator("#story-counter")).to_have_text("2 / 3")
    expect(page.locator("#story-map")).not_to_have_class(re.compile(r"leaflet-zoom-anim"))


def test_on_a_phone_the_caption_sits_below_the_map(page: Page, seed):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(_story(seed) + "?step=1")
    expect(page.locator("#story-counter")).to_have_text("1 / 3")
    map_box = page.locator("#story-map").bounding_box()
    caption_box = page.locator("#story-caption").bounding_box()
    assert map_box["y"] + map_box["height"] <= caption_box["y"] + 1


def test_the_embed_plays_inside_an_iframe(page: Page, seed, base_url):
    page.goto(f"{base_url}/about")  # any page of the site; the frame is put on it
    page.evaluate("""(src) => {
        const frame = document.createElement("iframe");
        frame.src = src; frame.width = "800"; frame.height = "520";
        document.body.prepend(frame);
    }""", f"{base_url}/collections/{seed.public_collection_token}/embed?step=2")
    frame = page.frame_locator("iframe").first
    expect(frame.locator("#story-counter")).to_have_text("2 / 3")
    expect(frame.locator(".navbar")).to_have_count(0)


def test_tag_story_in_date_order_with_the_path_off(page: Page, seed):
    page.goto(f"/story/tag/{seed.tag_ids['World War II']}?step=1")
    counter = page.locator("#story-counter")
    expect(counter).to_have_text("1 / 5")
    expect(page.locator("#story-caption .story-step-title")).to_have_text("Battle of Midway")
    expect(page.locator("#story-caption").get_by_role("link", name=re.compile("Event page"))).to_have_attribute(
        "href", re.compile(r"^/event/"))
    expect(page.locator("path.story-path")).to_have_count(0)  # tags start without the path

    path_button = page.get_by_role("button", name="Show the path")
    path_button.click()
    expect(path_button).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("ArrowRight")  # Midway to Stalingrad: across the date line
    expect(counter).to_have_text("2 / 5")
    expect(page.locator("path.story-path")).to_have_count(1)
