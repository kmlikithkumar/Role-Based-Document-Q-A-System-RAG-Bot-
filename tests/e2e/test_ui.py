"""Browser tests: start the real server and drive the UI with Playwright.
   pip install pytest-playwright && playwright install chromium && pytest tests/e2e"""
import os, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import expect  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def url():
    tmp = tempfile.mkdtemp()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "DATA_DIR": f"{tmp}/data", "DOCS_DIR": f"{tmp}/docs", "ADMIN_PASSWORD": "adminpass1", "SEED_DEMO": "1",
           "JWT_SECRET": "e2e-secret", "BACKUP_HOURS": "0", "GEMINI_API_KEY": "", "APP_ENV": "development"}
    env.pop("REDIS_URL", None)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=ROOT, env=env)
    base = f"http://127.0.0.1:{port}"
    for _ in range(240):  # first start downloads the embedding model
        try:
            urllib.request.urlopen(base + "/api/health")
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("server did not start")
    yield base
    proc.terminate()


def sign_in(page, url, user, pw):
    page.goto(url)
    page.locator("#u").fill(user)
    page.locator("#p").fill(pw)
    page.locator("#login").get_by_role("button", name="Sign in", exact=True).click()


def ask(page, q):
    page.locator("#q").fill(q)
    page.locator("#send").click()
    page.wait_for_selector(".src")


def test_wrong_password_shows_error(page, url):
    sign_in(page, url, "carol", "wrong-password")
    expect(page.locator("#lerr")).to_contain_text("Wrong username or password")


def test_employee_only_sees_public_sources(page, url):
    sign_in(page, url, "carol", "carol123")
    expect(page.locator("#admin")).to_be_hidden()
    ask(page, "How many days of annual leave do I get?")
    assert page.locator(".src .tag.hr").count() == 0 and page.locator(".src .tag.engineering").count() == 0


def test_hr_sees_hr_source_and_can_open_it(page, url):
    sign_in(page, url, "alice", "alice123")
    ask(page, "How many days of annual leave do I get?")
    assert page.locator(".src .tag.hr").count() >= 1
    with page.context.expect_page() as popup:
        page.get_by_role("button", name="Open document").first.click()
    popup.value.wait_for_load_state()


def test_admin_sees_admin_panel_and_can_sign_out(page, url):
    sign_in(page, url, "admin", "adminpass1")
    expect(page.locator("#admin")).to_be_visible()
    page.get_by_role("button", name="Sign out").click()
    expect(page.locator("#login")).to_be_visible()
