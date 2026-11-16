import json
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def auth(client, user, pw):
    r = client.post("/api/login", json={"username": user, "password": pw})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


def ask(client, headers, q, chat_id=None):
    r = client.post("/api/ask", json={"question": q, "chat_id": chat_id}, headers=headers)
    assert r.status_code == 200
    return [json.loads(x) for x in r.text.splitlines() if x]


def srcs(events):
    return next(e for e in events if e["type"] == "sources")["sources"]


def test_bad_login(client):
    assert client.post("/api/login", json={"username": "alice", "password": "nope"}).status_code == 401


def test_ask_requires_auth(client):
    r = client.post("/api/ask", json={"question": "hi"})
    assert r.status_code in (401, 403)


def test_hr_sees_hr_doc(client):
    ev = ask(client, auth(client, "alice", "alice123"), "How many days of annual leave do I get?")
    assert "leave_policy.md" in {s["file"] for s in srcs(ev)}
    assert ev[-1]["type"] == "done"


def test_employee_only_sees_public(client):
    h = auth(client, "carol", "carol123")
    for q in ["How many days of annual leave do I get?", "When can we deploy to production?"]:
        assert {s["tag"] for s in srcs(ask(client, h, q))} <= {"public"}


def test_engineer_cannot_see_hr(client):
    ev = ask(client, auth(client, "bob", "bob123"), "What is the paternity leave policy?")
    assert "hr" not in {s["tag"] for s in srcs(ev)}


def test_upload_requires_admin(client):
    r = client.post("/api/upload", data={"tag": "hr"}, files={"file": ("x.txt", b"hello", "text/plain")},
                    headers=auth(client, "bob", "bob123"))
    assert r.status_code == 403


def test_admin_upload_respects_roles(client):
    admin = auth(client, "admin", "adminpass1")
    text = b"Gym reimbursement is 500 rupees per month for eligible staff."
    r = client.post("/api/upload", data={"tag": "hr"}, files={"file": ("perks.txt", text, "text/plain")}, headers=admin)
    assert r.status_code == 200 and r.json()["chunks"] >= 1
    q = "gym reimbursement"
    assert "perks.txt" in {s["file"] for s in srcs(ask(client, auth(client, "alice", "alice123"), q))}
    assert "perks.txt" not in {s["file"] for s in srcs(ask(client, auth(client, "carol", "carol123"), q))}


def test_create_user(client):
    admin = auth(client, "admin", "adminpass1")
    ok = client.post("/api/users", json={"username": "dave", "password": "longpassword", "role": "employee"}, headers=admin)
    assert ok.status_code == 200
    auth(client, "dave", "longpassword")
    short = client.post("/api/users", json={"username": "eve", "password": "short", "role": "hr"}, headers=admin)
    assert short.status_code == 400


def mk(client, name, role="employee", pw="longpassword"):
    admin = auth(client, "admin", "adminpass1")
    assert client.post("/api/users", json={"username": name, "password": pw, "role": role}, headers=admin).status_code == 200
    return admin


def test_followup_uses_saved_chat(client):
    a = auth(client, "alice", "alice123")
    cid = ask(client, a, "Annual leave days?")[0]["id"]
    ev = ask(client, a, "What about sick leave?", cid)
    assert ev[0]["id"] == cid and ev[-1]["type"] == "done"


def test_chats_saved_and_private(client):
    a, c = auth(client, "alice", "alice123"), auth(client, "carol", "carol123")
    ev = ask(client, a, "How many days of annual leave?")
    assert ev[0]["type"] == "chat"
    cid = ev[0]["id"]
    msgs = client.get(f"/api/chats/{cid}", headers=a).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert client.get(f"/api/chats/{cid}", headers=c).status_code == 404
    assert client.delete(f"/api/chats/{cid}", headers=c).status_code == 404
    assert client.delete(f"/api/chats/{cid}", headers=a).status_code == 200


def test_disable_user_revokes_session(client):
    admin = mk(client, "frank")
    h = auth(client, "frank", "longpassword")
    assert client.get("/api/chats", headers=h).status_code == 200
    assert client.patch("/api/users/frank", json={"disabled": True}, headers=admin).status_code == 200
    assert client.get("/api/chats", headers=h).status_code == 401
    assert client.post("/api/login", json={"username": "frank", "password": "longpassword"}).status_code == 401


def test_logout_revokes_token(client):
    mk(client, "gina")
    h = auth(client, "gina", "longpassword")
    assert client.post("/api/logout", headers=h).status_code == 200
    assert client.get("/api/chats", headers=h).status_code == 401


def test_change_password(client):
    mk(client, "hank")
    h = auth(client, "hank", "longpassword")
    assert client.post("/api/password", json={"old": "wrongpass1", "new": "newlongpass"}, headers=h).status_code == 400
    assert client.post("/api/password", json={"old": "longpassword", "new": "newlongpass"}, headers=h).status_code == 200
    auth(client, "hank", "newlongpass")


def test_login_lockout(client):
    for _ in range(5):
        assert client.post("/api/login", json={"username": "mallory", "password": "x"}).status_code == 401
    assert client.post("/api/login", json={"username": "mallory", "password": "x"}).status_code == 429


def test_cannot_delete_self_or_last_admin(client):
    admin = auth(client, "admin", "adminpass1")
    assert client.delete("/api/users/admin", headers=admin).status_code == 400
    assert client.patch("/api/users/admin", json={"disabled": True}, headers=admin).status_code == 400


def test_list_and_delete_doc(client):
    admin = auth(client, "admin", "adminpass1")
    client.post("/api/upload", data={"tag": "public"}, files={"file": ("temp.txt", b"The office plant is called Gerald.", "text/plain")}, headers=admin)
    assert any(d["file"] == "temp.txt" and d["chunks"] >= 1 for d in client.get("/api/docs", headers=admin).json())
    assert client.delete("/api/docs/public/temp.txt", headers=admin).status_code == 200
    assert not any(d["file"] == "temp.txt" for d in client.get("/api/docs", headers=admin).json())
    assert client.delete("/api/docs/public/..%2Fx", headers=admin).status_code in (400, 404)


def test_unreadable_pdf_rejected(client):
    import io
    from pypdf import PdfWriter
    w = PdfWriter(); w.add_blank_page(200, 200); buf = io.BytesIO(); w.write(buf)
    r = client.post("/api/upload", data={"tag": "public"}, files={"file": ("blank.pdf", buf.getvalue(), "application/pdf")},
                    headers=auth(client, "admin", "adminpass1"))
    assert r.status_code == 422


def test_audit_log(client):
    admin = auth(client, "admin", "adminpass1")
    ask(client, auth(client, "carol", "carol123"), "When is lunch served?")
    rows = client.get("/api/audit?actor=carol", headers=admin).json()
    assert any(r["action"] == "ask" and "lunch" in r["detail"] for r in rows)
    assert client.get("/api/audit", headers=auth(client, "bob", "bob123")).status_code == 403


def test_document_viewer_respects_roles(client):
    assert client.get("/api/files/hr/leave_policy.md", headers=auth(client, "carol", "carol123")).status_code == 404
    r = client.get("/api/files/hr/leave_policy.md", headers=auth(client, "alice", "alice123"))
    assert r.status_code == 200 and "24 days" in r.text
    assert client.get("/api/files/public/..%2F..%2Fx", headers=auth(client, "alice", "alice123")).status_code == 404


def test_blank_image_rejected(client):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 60), "white").save(buf, "PNG")
    r = client.post("/api/upload", data={"tag": "public"}, files={"file": ("blank.png", buf.getvalue(), "image/png")},
                    headers=auth(client, "admin", "adminpass1"))
    assert r.status_code == 422


def test_backup_and_download(client):
    import io, zipfile
    admin = auth(client, "admin", "adminpass1")
    name = client.post("/api/backup", headers=admin).json()["name"]
    assert name in [b["name"] for b in client.get("/api/backups", headers=admin).json()]
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/backups/{name}", headers=admin).content))
    assert "users.db" in z.namelist() and "docs/public/company_overview.md" in z.namelist()
    assert client.get(f"/api/backups/{name}", headers=auth(client, "bob", "bob123")).status_code == 403
    assert client.get("/api/backups/..%2Fusers.db", headers=admin).status_code == 404


def test_email_verification_then_password_reset(client, monkeypatch):
    import re
    from app import main
    sent = []
    monkeypatch.setattr(main, "send_mail", lambda to, subj, body: sent.append((to, body)))
    admin = auth(client, "admin", "adminpass1")
    r = client.post("/api/users", json={"username": "ivy", "password": "longpassword", "role": "employee", "email": "ivy@example.com"}, headers=admin)
    assert r.status_code == 200 and len(sent) == 1  # verification mail
    # unverified address: reset request is accepted but nothing is sent
    assert client.post("/api/forgot", json={"identifier": "ivy@example.com"}).status_code == 200 and len(sent) == 1
    vtok = re.search(r"#verify=(\S+)", sent[0][1]).group(1)
    assert client.post("/api/verify-email", json={"token": "wrong"}).status_code == 400
    assert client.post("/api/verify-email", json={"token": vtok}).status_code == 200
    assert client.post("/api/forgot", json={"identifier": "nobody@example.com"}).status_code == 200 and len(sent) == 1
    assert client.post("/api/forgot", json={"identifier": "ivy@example.com"}).status_code == 200 and len(sent) == 2
    tok = re.search(r"#reset=(\S+)", sent[1][1]).group(1)
    assert client.post("/api/reset", json={"token": tok, "password": "short"}).status_code == 400
    assert client.post("/api/reset", json={"token": tok, "password": "brandnewpass"}).status_code == 200
    auth(client, "ivy", "brandnewpass")
    assert client.post("/api/reset", json={"token": tok, "password": "anotherpass1"}).status_code == 400


def test_shared_ip_failure_limit(client):
    from app import main
    for _ in range(20):
        main.record_hit("failip:9.9.9.9")
    assert main.locked("failip:9.9.9.9", 20) and not main.locked("failip:8.8.8.8", 20)


def test_two_factor_login(client):
    import time
    from app import totp
    mk(client, "jo")
    h = auth(client, "jo", "longpassword")
    setup = client.post("/api/2fa/setup", headers=h).json()
    code = totp.code(setup["secret"], int(time.time() // 30))
    assert client.post("/api/2fa/enable", json={"code": "000000"}, headers=h).status_code == 400
    assert client.post("/api/2fa/enable", json={"code": code}, headers=h).status_code == 200
    r = client.post("/api/login", json={"username": "jo", "password": "longpassword"}).json()
    assert r["mfa_required"] and "token" not in r
    assert client.get("/api/chats", headers={"Authorization": "Bearer " + r["mfa_token"]}).status_code == 401
    assert client.post("/api/login/2fa", json={"mfa_token": r["mfa_token"], "code": "000000"}).status_code == 401
    assert client.post("/api/login/2fa", json={"mfa_token": r["mfa_token"], "code": code}).status_code == 401  # replay
    nxt = totp.code(setup["secret"], int(time.time() // 30) + 1)
    ok = client.post("/api/login/2fa", json={"mfa_token": r["mfa_token"], "code": nxt})
    assert ok.status_code == 200 and "token" in ok.json()
    admin = auth(client, "admin", "adminpass1")
    assert client.patch("/api/users/jo", json={"reset_2fa": True}, headers=admin).status_code == 200
    assert "token" in client.post("/api/login", json={"username": "jo", "password": "longpassword"}).json()


def test_totp_matches_rfc6238_vector():
    from app import totp
    assert totp.code("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 1) == "287082"


def test_sso_disabled_by_default(client):
    assert client.get("/api/config").json() == {"sso": False}
    assert client.get("/api/sso/login", follow_redirects=False).status_code == 404
    assert client.post("/api/sso/exchange", json={"token": "nope"}).status_code == 400


def test_redis_backed_limits(client, monkeypatch):
    fakeredis = pytest.importorskip("fakeredis")
    from app import main
    monkeypatch.setattr(main, "rds", fakeredis.FakeRedis())
    for _ in range(5):
        main.record_hit("fail:zed")
    assert main.locked("fail:zed")
    main.clear_hits("fail:zed")
    assert not main.locked("fail:zed")


def test_encrypted_backup_and_offsite(client, monkeypatch):
    import io, zipfile
    from app import crypto, main
    uploaded = []
    monkeypatch.setattr(main, "upload_offsite", lambda p: uploaded.append(p.name) or True)
    monkeypatch.setenv("BACKUP_PASSPHRASE", "correct horse battery")
    admin = auth(client, "admin", "adminpass1")
    name = client.post("/api/backup", headers=admin).json()["name"]
    assert name.endswith(".enc") and uploaded == [name]
    blob = client.get(f"/api/backups/{name}", headers=admin).content
    assert blob.startswith(b"RAGB1") and b"users.db" not in blob[:300]
    assert "users.db" in zipfile.ZipFile(io.BytesIO(crypto.decrypt(blob, "correct horse battery"))).namelist()
    with pytest.raises(Exception):
        crypto.decrypt(blob, "wrong passphrase")


def test_document_versions_and_restore(client):
    admin = auth(client, "admin", "adminpass1")

    def up(text):
        return client.post("/api/upload", data={"tag": "public"}, files={"file": ("parking.txt", text, "text/plain")}, headers=admin)

    assert up(b"Version one says parking is free for staff.").status_code == 200
    assert up(b"Version two says parking costs money.").status_code == 200
    vers = client.get("/api/docs/public/parking.txt/versions", headers=admin).json()
    assert len(vers) == 1
    assert client.post("/api/docs/public/parking.txt/restore", json={"version": "../x"}, headers=admin).status_code == 400
    assert client.post("/api/docs/public/parking.txt/restore", json={"version": vers[0]["version"]}, headers=admin).status_code == 200
    assert "free" in client.get("/api/files/public/parking.txt", headers=admin).text
    assert len(client.get("/api/docs/public/parking.txt/versions", headers=admin).json()) == 2  # restore is undoable
    client.delete("/api/docs/public/parking.txt", headers=admin)
    assert client.get("/api/docs/public/parking.txt/versions", headers=admin).json() == []


def test_audit_paging(client):
    admin = auth(client, "admin", "adminpass1")
    first = client.get("/api/audit?limit=3", headers=admin).json()
    assert len(first) == 3 and first[0]["id"] > first[-1]["id"]
    nxt = client.get(f"/api/audit?limit=3&before={first[-1]['id']}", headers=admin).json()
    assert nxt and all(r["id"] < first[-1]["id"] for r in nxt)
