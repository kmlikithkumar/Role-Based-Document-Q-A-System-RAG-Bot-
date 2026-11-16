import io, re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def auth(client, user, pw):
    r = client.post("/api/login", json={"username": user, "password": pw})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


def png(w=1200, h=800, exif=False):
    buf = io.BytesIO()
    img = Image.new("RGB", (w, h), (30, 120, 200))
    if exif:
        ex = Image.Exif(); ex[0x010E] = "secret camera note"
        img.save(buf, "JPEG", exif=ex)
    else:
        img.save(buf, "PNG")
    return buf.getvalue()


def test_requires_login(client):
    assert client.get("/api/profile").status_code in (401, 403)
    assert client.patch("/api/profile", json={"bio": "x"}).status_code in (401, 403)


def test_user_without_profile_loads(client):
    r = client.get("/api/profile", headers=auth(client, "carol", "carol123")).json()
    assert r["username"] == "carol" and r["role"] == "employee" and r["full_name"] is None and r["has_avatar"] is False
    assert "CSE" in r["choices"]["departments"] and r["choices"]["semesters"] == list(range(1, 9))


def test_edit_persists_trims_and_normalises(client):
    h = auth(client, "bob", "bob123")
    r = client.patch("/api/profile", json={"full_name": "  Bob Rao ", "department": "CSE", "semester": 5, "section": "A",
                                           "phone": "98765 43210", "bio": "Hello"}, headers=h)
    assert r.status_code == 200
    got = client.get("/api/profile", headers=h).json()
    assert (got["full_name"], got["semester"], got["phone"], got["section"]) == ("Bob Rao", 5, "9876543210", "A")
    cleared = client.patch("/api/profile", json={"bio": ""}, headers=h).json()
    assert cleared["bio"] is None and cleared["full_name"] == "Bob Rao"      # only the sent fields change


@pytest.mark.parametrize("body", [{"role": "admin"}, {"username": "admin"}, {"email": "x@y.z"}, {"avatar": "../../etc/passwd"}], ids=["role", "username", "email", "avatar"])
def test_read_only_fields_are_rejected(client, body):
    assert client.patch("/api/profile", json=body, headers=auth(client, "carol", "carol123")).status_code == 422


@pytest.mark.parametrize("body,field", [({"phone": "123"}, "phone"), ({"semester": 9}, "semester"), ({"department": "Astrology"}, "department"),
                                        ({"full_name": "A"}, "full_name"), ({"bio": "x" * 281}, "bio"), ({"section": "A B!"}, "section")])
def test_invalid_input_gives_clear_errors(client, body, field):
    r = client.patch("/api/profile", json=body, headers=auth(client, "carol", "carol123"))
    assert r.status_code == 422 and field in r.json()["errors"] and isinstance(r.json()["detail"], str)


def test_users_cannot_touch_each_others_profiles(client):
    a, c = auth(client, "alice", "alice123"), auth(client, "carol", "carol123")
    client.patch("/api/profile", json={"full_name": "Alice Hegde"}, headers=a)
    assert client.get("/api/profile", headers=c).json()["full_name"] != "Alice Hegde"
    assert client.get("/api/profile?username=alice", headers=c).json()["username"] == "carol"


def test_avatar_rules(client):
    h = auth(client, "alice", "alice123")
    assert client.post("/api/profile/avatar", files={"file": ("a.png", b"not an image", "image/png")}, headers=h).status_code == 400
    assert client.post("/api/profile/avatar", files={"file": ("a.png", b"x" * (2 * 1024 * 1024 + 1), "image/png")}, headers=h).status_code == 413
    gif = io.BytesIO(); Image.new("RGB", (20, 20)).save(gif, "GIF")
    assert client.post("/api/profile/avatar", files={"file": ("a.png", gif.getvalue(), "image/png")}, headers=h).status_code == 400
    assert client.post("/api/profile/avatar", files={"file": ("p.jpg", png(exif=True), "image/jpeg")}, headers=h).status_code == 200
    r = client.get("/api/profile/avatar", headers=h)
    img = Image.open(io.BytesIO(r.content))
    assert r.status_code == 200 and img.size == (512, 512) and img.format == "WEBP" and len(img.getexif()) == 0   # square, re-encoded, no metadata
    assert client.get("/api/profile", headers=h).json()["has_avatar"] is True
    assert client.get("/api/profile/avatar", headers=auth(client, "bob", "bob123")).status_code == 404            # photos are private
    assert client.delete("/api/profile/avatar", headers=h).status_code == 200
    assert client.get("/api/profile/avatar", headers=h).status_code == 404


def test_audit_records_field_names_not_values(client):
    h, adm = auth(client, "carol", "carol123"), auth(client, "admin", "adminpass1")
    client.patch("/api/profile", json={"phone": "9123456780"}, headers=h)
    rows = client.get("/api/audit?actor=carol&action=profile_update", headers=adm).json()
    assert rows and "phone" in rows[0]["detail"] and "9123456780" not in rows[0]["detail"]


def test_deleting_a_user_deletes_their_profile(client):
    adm = auth(client, "admin", "adminpass1")
    client.post("/api/users", json={"username": "temp1", "password": "longpassword", "role": "employee"}, headers=adm)
    t = auth(client, "temp1", "longpassword")
    client.patch("/api/profile", json={"full_name": "Temp One"}, headers=t)
    client.post("/api/profile/avatar", files={"file": ("p.png", png(), "image/png")}, headers=t)
    assert client.delete("/api/users/temp1", headers=adm).status_code == 200
    client.post("/api/users", json={"username": "temp1", "password": "longpassword", "role": "employee"}, headers=adm)
    again = client.get("/api/profile", headers=auth(client, "temp1", "longpassword")).json()
    assert again["full_name"] is None and again["has_avatar"] is False


def _lum(hexcol):
    c = [int(hexcol[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_theme_colours_meet_wcag_aa():
    css = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text()
    themes = {n: dict(re.findall(r"--([a-z0-9-]+):(#[0-9A-Fa-f]{6})", body)) for n, body in
              (("light", re.search(r":root\{(.*?)\}", css, re.S).group(1)), ("dark", re.search(r"\[data-theme=dark\]\{(.*?)\}", css, re.S).group(1)))}
    full = {"light": themes["light"], "dark": {**themes["light"], **themes["dark"]}}
    pairs = [("ink", "bg"), ("ink", "surface"), ("mute", "bg"), ("mute", "surface"), ("on-primary", "primary"), ("primary", "surface"),
             ("primary", "bg"), ("on-primary", "public"), ("on-primary", "hr"), ("on-primary", "engineering"), ("danger", "surface"), ("ok", "surface")]
    bad = [(t, a, b, round(_ratio(v[a], v[b]), 2)) for t, v in full.items() for a, b in pairs if _ratio(v[a], v[b]) < 4.5]
    assert not bad, bad
