"""Tiny OpenID Connect provider for tests (discovery, JWKS/RS256, authorize, token).  python fake_idp.py PORT"""
import json, secrets, sys, time

import jwt, uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form
from fastapi.responses import RedirectResponse
from jwt.algorithms import RSAAlgorithm

PORT = int(sys.argv[1])
ISS = f"http://127.0.0.1:{PORT}"
key = rsa.generate_private_key(65537, 2048)
jwk = {**json.loads(RSAAlgorithm.to_jwk(key.public_key())), "kid": "k1", "use": "sig", "alg": "RS256"}
CFG = {"email": "sam@corp.example", "verified": "true", "claim": "email", "aud": ""}
codes: dict = {}
app = FastAPI()


@app.get("/.well-known/openid-configuration")
def conf():
    return {"issuer": ISS, "authorization_endpoint": ISS + "/authorize", "token_endpoint": ISS + "/token", "jwks_uri": ISS + "/jwks"}


@app.get("/jwks")
def jwks():
    return {"keys": [jwk]}


@app.get("/authorize")
def authorize(client_id: str, redirect_uri: str, state: str, nonce: str):
    c = secrets.token_urlsafe(8)
    codes[c] = (client_id, nonce)
    return RedirectResponse(f"{redirect_uri}?code={c}&state={state}")


@app.post("/token")
def token(code: str = Form(...), client_secret: str = Form(...), client_id: str = Form(...)):
    cid, nonce = codes.pop(code)
    assert client_secret == "s3cret"
    now = int(time.time())
    claims = {"iss": ISS, "aud": CFG["aud"] or cid, "sub": "u1", CFG["claim"]: CFG["email"], "nonce": nonce, "iat": now, "exp": now + 300}
    if CFG["verified"] != "absent":  # real IdPs differ: boolean, string, or missing (Microsoft Entra)
        claims["email_verified"] = {"true": True, "false": False, "string-true": "true"}[CFG["verified"]]
    return {"id_token": jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"}), "access_token": "x", "token_type": "Bearer"}


@app.get("/_set")
def set_(email: str, verified: str = "true", claim: str = "email", aud: str = ""):
    CFG.update(email=email, verified=verified, claim=claim, aud=aud)
    return CFG


uvicorn.run(app, port=PORT, log_level="warning")
