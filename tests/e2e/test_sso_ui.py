"""The SSO button, end to end in a browser, through a local OpenID Connect provider."""
import sys
from pathlib import Path

import pytest
from playwright.sync_api import expect

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.integration.helpers import HERE, Proc, free_port, start_app, wait  # noqa: E402


@pytest.fixture(scope="module")
def sso_app():
    port = free_port()
    idp = Proc([sys.executable, str(HERE / "fake_idp.py"), str(port)])
    issuer = f"http://127.0.0.1:{port}"
    wait(issuer + "/.well-known/openid-configuration")
    app, url = start_app(SSO_ISSUER=issuer, SSO_CLIENT_ID="docs", SSO_CLIENT_SECRET="s3cret", SSO_ALLOWED_DOMAIN="corp.example",
                         SSO_AUTO_PROVISION="1")
    yield url
    app.stop(); idp.stop()


def test_sso_button_signs_you_in(page, sso_app):
    page.goto(sso_app)
    expect(page.locator("#ssobtn")).to_be_visible()
    page.locator("#ssobtn").click()
    expect(page.locator("#chat")).to_be_visible()
    expect(page.locator("#who")).to_contain_text("sam@corp.example")
    assert "#sso=" not in page.url                       # the one-time code is removed from the address bar
