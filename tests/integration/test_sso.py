"""SSO against a local OpenID Connect provider, including the quirks of real vendors."""
import re, sys

import httpx
import pytest

from tests.integration.helpers import HERE, Proc, free_port, login, start_app, wait


@pytest.fixture(scope="module")
def idp():
    port = free_port()
    p = Proc([sys.executable, str(HERE / "fake_idp.py"), str(port)])
    base = f"http://127.0.0.1:{port}"
    wait(base + "/.well-known/openid-configuration")
    yield base
    p.stop()


def app(idp, **extra):
    return start_app(SSO_ISSUER=idp, SSO_CLIENT_ID="docs", SSO_CLIENT_SECRET="s3cret", SSO_ALLOWED_DOMAIN="corp.example",
                     SSO_AUTO_PROVISION="1", SSO_DEFAULT_ROLE="admin", **extra)


@pytest.fixture(scope="module")
def strict(idp):
    p, url = app(idp)
    yield url, idp
    p.stop()


@pytest.fixture(scope="module")
def trusting(idp):
    p, url = app(idp, SSO_TRUST_EMAIL="1")
    yield url, idp
    p.stop()


def sso(env, email, verified="true", claim="email", aud="", tamper=False):
    url, idp = env
    httpx.get(f"{idp}/_set", params={"email": email, "verified": verified, "claim": claim, "aud": aud})
    c = httpx.Client(base_url=url)
    loc = c.get("/api/sso/login").headers["location"]
    cb = httpx.get(loc).headers["location"]
    if tamper:
        cb = re.sub(r"state=[^&]+", "state=forged", cb)
    final = c.get(cb.replace(url, "")).headers["location"]
    if "#sso=" not in final:
        return None, c, None
    code = final.split("#sso=")[1]
    r = c.post("/api/sso/exchange", json={"token": code})
    return (r.json() if r.status_code == 200 else None), c, code


def test_existing_user_keeps_role_and_code_is_single_use(strict):
    url, _ = strict
    httpx.patch(url + "/api/users/alice", json={"email": "alice@corp.example"}, headers=login(url, "admin", "adminpass1"))
    j, c, code = sso(strict, "alice@corp.example")
    assert j and j["user"] == "alice" and j["role"] == "hr"
    assert c.post("/api/sso/exchange", json={"token": code}).status_code == 400


def test_auto_provision_is_never_admin(strict):
    j, *_ = sso(strict, "sam@corp.example")
    assert j and j["role"] == "employee"


@pytest.mark.parametrize("kw", [
    {"email": "mallory@evil.example"}, {"email": "sam@corp.example", "verified": "false"},
    {"email": "sam@corp.example", "verified": "absent"}, {"email": "sam@corp.example", "aud": "someone-else"},
    {"email": "sam@corp.example", "tamper": True}], ids=["domain", "unverified", "no-claim-strict", "audience", "forged-state"])
def test_rejections(strict, kw):
    assert sso(strict, **kw)[0] is None


def test_string_true_is_accepted(strict):
    assert sso(strict, "sam@corp.example", verified="string-true")[0]


def test_disabled_user_rejected(strict):
    url, _ = strict
    httpx.patch(url + "/api/users/alice", json={"disabled": True}, headers=login(url, "admin", "adminpass1"))
    assert sso(strict, "alice@corp.example")[0] is None


def test_entra_style_tokens_need_the_trust_flag(trusting):
    assert sso(trusting, "sam@corp.example", verified="absent")[0]                              # no email_verified claim
    assert sso(trusting, "sam@corp.example", verified="absent", claim="preferred_username")[0]  # email only in the UPN
    assert sso(trusting, "sam@corp.example", verified="false")[0] is None                        # explicit "false" still wins
