"""Every admin-panel control, clicked in a real browser."""
import httpx
from playwright.sync_api import expect

from test_ui import sign_in, url  # noqa: F401


def admin(page, url):
    sign_in(page, url, "admin", "adminpass1")
    page.locator("#admin summary").click()
    expect(page.locator("#users .item").first).to_be_visible()


def test_add_disable_reset_and_delete_user(page, url):
    admin(page, url)
    page.locator("#nu").fill("newbie")
    page.locator("#np").fill("longpassword1")
    page.locator("#nr").select_option("hr")
    page.locator("#userform").get_by_role("button", name="Add user").click()
    expect(page.locator("#amsg")).to_contain_text("Added newbie")
    row = page.locator("#users .item", has_text="newbie")
    expect(row).to_contain_text("hr")
    row.get_by_role("button", name="Disable").click()
    expect(row).to_contain_text("disabled")
    assert httpx.post(url + "/api/login", json={"username": "newbie", "password": "longpassword1"}).status_code == 401
    row.get_by_role("button", name="Enable").click()
    expect(row).not_to_contain_text("disabled")
    page.once("dialog", lambda d: d.accept("anotherpass99"))
    row.get_by_role("button", name="Reset password").click()
    expect(page.locator("#amsg")).to_contain_text("Password reset for newbie")
    assert httpx.post(url + "/api/login", json={"username": "newbie", "password": "anotherpass99"}).status_code == 200
    page.once("dialog", lambda d: d.accept())
    row.get_by_role("button", name="Delete").click()
    expect(row).to_have_count(0)


def test_upload_history_restore_and_delete_document(page, url):
    admin(page, url)

    def upload(text):
        page.locator("#upfile").set_input_files({"name": "notes.txt", "mimeType": "text/plain", "buffer": text})
        with page.expect_response(lambda r: r.url.endswith("/api/upload") and r.request.method == "POST") as resp:
            page.locator("#upform").get_by_role("button", name="Upload").click()
        assert resp.value.status == 200                      # wait for THIS upload, not the previous message
        expect(page.locator("#amsg")).to_contain_text("Indexed notes.txt")
        page.wait_for_load_state("networkidle")              # the document list refreshes just after

    upload(b"The library opens at nine in the morning.")
    row = page.locator("#docs .item", has_text="notes.txt")
    expect(row).to_be_visible()
    row.get_by_role("button", name="History").click()
    expect(row).to_contain_text("No earlier versions")
    upload(b"The library opens at ten in the morning on weekdays.")
    row.get_by_role("button", name="History").click()
    page.once("dialog", lambda d: d.accept())
    row.get_by_role("button", name="Restore").first.click()
    expect(page.locator("#amsg")).to_contain_text("Restored")
    page.once("dialog", lambda d: d.accept())
    row.get_by_role("button", name="Delete").click()
    expect(row).to_have_count(0)


def test_backup_now_and_download(page, url):
    admin(page, url)
    page.locator("#bknow").click()
    expect(page.locator("#amsg")).to_contain_text("Created backup-")
    expect(page.locator("#amsg")).to_contain_text("off-site upload is not configured")
    with page.expect_download() as d:
        page.locator("#backups").get_by_role("button", name="Download").first.click()
    assert d.value.suggested_filename.startswith("backup-")


def test_audit_log_and_filter(page, url):
    admin(page, url)
    expect(page.locator("#audit .item").first).to_be_visible()
    page.locator("#auditq").fill("admin")
    page.locator("#auditgo").click()
    expect(page.locator("#audit .item").first).to_contain_text("admin")
