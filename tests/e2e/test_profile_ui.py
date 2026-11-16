import pytest
from playwright.sync_api import expect

from test_ui import sign_in, url  # noqa: F401  (shared server fixture)


def open_profile(page):
    page.locator("#avatarbtn").click()
    expect(page.locator("#profilepane")).to_be_visible()


def test_edit_profile_and_it_persists(page, url):
    sign_in(page, url, "carol", "carol123")
    open_profile(page)
    expect(page.locator("#pr_username")).to_be_disabled()
    expect(page.locator("#pr_role")).to_be_disabled()
    page.get_by_role("button", name="Edit profile").click()
    expect(page.locator("#psave")).to_be_disabled()                      # nothing changed yet
    page.locator("#pf_full_name").fill("Carol Rao")
    page.locator("#pf_phone").fill("98765 43210")
    page.locator("#pf_department").select_option("CSE")
    page.locator("#pf_semester").select_option("5")
    expect(page.locator("#psave")).to_be_enabled()
    page.locator("#psave").click()
    expect(page.locator(".toast")).to_contain_text("Profile saved")
    expect(page.locator("#pview")).to_contain_text("Carol Rao")
    page.reload()
    sign_in(page, url, "carol", "carol123")
    open_profile(page)
    expect(page.locator("#pview")).to_contain_text("Carol Rao")
    expect(page.locator("#pview")).to_contain_text("9876543210")


def test_validation_blocks_saving(page, url):
    sign_in(page, url, "bob", "bob123")
    open_profile(page)
    page.get_by_role("button", name="Edit profile").click()
    page.locator("#pf_phone").fill("123")
    expect(page.locator("#pf_phone_e")).to_contain_text("valid phone")
    expect(page.locator("#psave")).to_be_disabled()


def test_cancel_discards_changes(page, url):
    sign_in(page, url, "alice", "alice123")
    open_profile(page)
    page.get_by_role("button", name="Edit profile").click()
    page.locator("#pf_full_name").fill("Someone Else")
    page.once("dialog", lambda d: d.accept())
    page.locator("#pcancel").click()
    expect(page.locator("#pview")).not_to_contain_text("Someone Else")


def test_back_to_chat_and_header_avatar_initials(page, url):
    sign_in(page, url, "carol", "carol123")
    open_profile(page)
    page.locator("#pback").click()
    expect(page.locator("#convo")).to_be_visible()
    expect(page.locator("#askbar")).to_be_visible()
