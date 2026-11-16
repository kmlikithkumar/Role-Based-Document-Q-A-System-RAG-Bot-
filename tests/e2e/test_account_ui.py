"""Photo upload through the real file picker, 2FA set-up, password change, email."""
import io, time

import httpx
from PIL import Image
from playwright.sync_api import expect

from app import totp
from test_ui import sign_in, url  # noqa: F401


def png(w=800, h=500):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 60, 90)).save(buf, "PNG")
    return buf.getvalue()


def test_photo_upload_crop_reload_and_remove(page, url):
    sign_in(page, url, "bob", "bob123")
    page.locator("#avatarbtn").click()
    page.get_by_role("button", name="Edit profile").click()
    page.locator("#pfile").set_input_files({"name": "me.txt", "mimeType": "text/plain", "buffer": b"not an image"})
    expect(page.locator(".toast")).to_contain_text("not a readable image")
    page.locator("#pfile").set_input_files({"name": "me.png", "mimeType": "image/png", "buffer": png()})
    expect(page.locator("#pavatar img")).to_be_visible()                  # square preview
    expect(page.locator("#photosave")).to_be_visible()
    page.locator("#photosave").click()
    expect(page.locator(".toast", has_text="Photo updated")).to_be_visible()
    expect(page.locator("#avatarbtn img")).to_be_visible()
    tok = httpx.post(url + "/api/login", json={"username": "bob", "password": "bob123"}).json()["token"]
    r = httpx.get(url + "/api/profile/avatar", headers={"Authorization": "Bearer " + tok})
    assert Image.open(io.BytesIO(r.content)).size == (512, 512)           # cropped to a square on the way in
    page.reload()
    sign_in(page, url, "bob", "bob123")
    expect(page.locator("#avatarbtn img")).to_be_visible()                # survives a reload
    page.locator("#avatarbtn").click()
    page.get_by_role("button", name="Edit profile").click()
    page.locator("#photodel").click()
    expect(page.locator(".toast", has_text="Photo removed")).to_be_visible()
    expect(page.locator("#avatarbtn")).to_have_text("B")                  # back to initials


def test_two_factor_setup_and_sign_in(page, url):
    sign_in(page, url, "alice", "alice123")
    page.locator("#acct summary").click()
    page.get_by_role("button", name="Set up an authenticator app").click()
    secret = page.locator("#tfa code").inner_text()
    page.locator("#te_code").fill("000000")
    page.get_by_role("button", name="Turn on").click()
    expect(page.locator("#tmsg")).to_contain_text("didn't match")
    page.locator("#te_code").fill(totp.code(secret, int(time.time() // 30)))
    page.get_by_role("button", name="Turn on").click()
    expect(page.locator("#tmsg")).to_contain_text("Two-factor is on")
    page.get_by_role("button", name="Sign out").click()
    sign_in(page, url, "alice", "alice123")
    expect(page.locator("#mfa")).to_be_visible()                          # password alone is no longer enough
    page.locator("#mc").fill("000000")
    page.locator("#mfa").get_by_role("button", name="Verify").click()
    expect(page.locator("#mmsg")).to_contain_text("didn't match")
    page.locator("#mc").fill(totp.code(secret, int(time.time() // 30) + 1))
    page.locator("#mfa").get_by_role("button", name="Verify").click()
    expect(page.locator("#chat")).to_be_visible()


def test_change_password_and_set_email(page, url):
    sign_in(page, url, "carol", "carol123")
    page.locator("#acct summary").click()
    page.locator("#me_email").fill("carol@example.com")
    page.get_by_role("button", name="Save and verify").click()
    expect(page.locator("#acctinfo")).to_contain_text("carol@example.com")
    expect(page.locator("#acctinfo")).to_contain_text("not verified")
    page.get_by_role("group").filter(has_text="My password").locator("summary").click()
    page.locator("#po").fill("carol123")
    page.locator("#pn").fill("newpassword9")
    page.locator("#pwform").get_by_role("button", name="Change").click()
    expect(page.locator("#pmsg")).to_contain_text("Password changed")
    assert httpx.post(url + "/api/login", json={"username": "carol", "password": "newpassword9"}).status_code == 200


def test_sso_button_hidden_when_not_configured(page, url):
    page.goto(url)
    expect(page.locator("#ssobtn")).to_be_hidden()
