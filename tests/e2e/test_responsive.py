"""Layout at phone/tablet/desktop widths, keyboard use, and a touch-device run."""
import pytest
from playwright.sync_api import expect

from test_ui import sign_in, url  # noqa: F401


@pytest.mark.parametrize("w,h", [(360, 740), (390, 844), (768, 1024), (1280, 800)])
def test_no_horizontal_scroll_on_any_screen(browser, url, w, h):
    ctx = browser.new_context(viewport={"width": w, "height": h})
    page = ctx.new_page()

    def fits(label):
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), f"sideways scroll on {label} at {w}px"

    page.goto(url); fits("login")
    sign_in(page, url, "admin", "adminpass1")
    page.wait_for_selector("#chat:not([hidden])")
    page.locator("#q").fill("When is lunch served?"); page.locator("#send").click(); page.wait_for_selector(".src"); fits("chat")
    page.locator("#admin summary").click(); page.wait_for_selector("#users .item"); fits("admin panel")
    page.locator("#avatarbtn").click(); fits("profile view")
    page.get_by_role("button", name="Edit profile").click(); fits("profile edit")
    ctx.close()


def test_keyboard_focus_is_visible_everywhere(page, url):
    page.goto(url)
    seen = []
    for _ in range(12):
        page.keyboard.press("Tab")
        tag = page.evaluate("document.activeElement.tagName")
        if tag == "BODY":                                    # focus has not entered the page yet
            continue
        seen.append(page.evaluate("document.activeElement.id || document.activeElement.textContent.trim().slice(0, 20)"))
        assert page.evaluate("getComputedStyle(document.activeElement).boxShadow") != "none", f"no focus ring on {seen[-1]}"
        if len(seen) == 6:
            break
    assert "u" in seen and "p" in seen, seen                 # username and password are reachable by keyboard
    sign_in(page, url, "carol", "carol123")
    page.wait_for_selector("#chat:not([hidden])")
    page.locator("#themebtn").focus()
    page.keyboard.press("Tab")                               # next stop in the header: the avatar button
    assert page.evaluate("document.activeElement.id") == "avatarbtn"
    ring = page.evaluate("getComputedStyle(document.activeElement).boxShadow")
    assert "rgba(79, 70, 229" in ring or "rgba(129, 140, 248" in ring, ring   # the avatar button shows the focus ring too


def test_touch_phone_flow(playwright, browser, url):
    ctx = browser.new_context(**playwright.devices["Pixel 5"])
    page = ctx.new_page()
    page.goto(url)
    page.locator("#u").fill("carol"); page.locator("#p").fill("carol123")
    page.locator("#login").get_by_role("button", name="Sign in", exact=True).tap()
    page.wait_for_selector("#chat:not([hidden])")
    page.locator("#avatarbtn").tap()
    expect(page.locator("#profilepane")).to_be_visible()
    ctx.close()
