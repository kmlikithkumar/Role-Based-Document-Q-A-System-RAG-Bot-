# Role-Based Document Q&A (RAG)

FastAPI + ChromaDB + Google Gemini. Each document folder is an access tag; each role maps to a set of tags.
The vector query is filtered by the caller's tags, so restricted text never reaches the LLM.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env     # set GEMINI_API_KEY, JWT_SECRET, ADMIN_PASSWORD; set APP_ENV=development
uvicorn app.main:app --reload
```
Sign in as `admin` with `ADMIN_PASSWORD`. `SEED_DEMO=1` before first start also creates alice (hr), bob (engineer), carol (employee), password `<name>123`.
Local OCR needs `tesseract` + `poppler` (`apt install tesseract-ocr poppler-utils` / `brew install tesseract poppler`).

## Sign-in and accounts
- Passwords: scrypt. Disable, password change, sign-out or 2FA reset revoke sessions server-side.
- **2FA (TOTP):** each user turns it on under "My account" (type the setup key into any authenticator app). Codes can't be replayed; 2FA secrets are encrypted at rest (`TOTP_KEY`). Admins can reset a lost device.
- **Email verification:** an address (set by an admin or by the user) must be confirmed through a link before it can receive password resets.
- **Password reset by email**, **audit log** (paged, filterable), **rate limits and lockouts** (per user, per IP).
- **Company SSO (OpenID Connect):** set `SSO_ISSUER`, `SSO_CLIENT_ID`, `SSO_CLIENT_SECRET`, register `BASE_URL/api/sso/callback` as the redirect URI. Users are matched by their IdP-verified email; `SSO_AUTO_PROVISION=1` creates non-admin accounts (limit with `SSO_ALLOWED_DOMAIN`). SSO users skip the app's 2FA, so enforce MFA at the IdP.

## Documents
`.pdf .md .txt` plus images (OCR for scans). Re-uploading keeps the old file in a version history (last `VERSIONS_KEEP`); admins can restore any version (restoring is itself undoable). "Open document" on a source shows the full file under the same role rules as search.

## Backups
Automatic zip every `BACKUP_HOURS` (users, chats, audit log, documents, version history). Set `BACKUP_PASSPHRASE` to encrypt (AES via Fernet, scrypt key; keep the passphrase safe, without it the backup is unreadable). Set `BACKUP_S3_BUCKET` (+ `AWS_*`, `S3_ENDPOINT_URL` for R2/B2/MinIO) to copy each backup off the machine; use bucket lifecycle rules for remote retention.
```bash
docker compose stop docsbot
docker compose run --rm docsbot python -m app.restore /data/backups/backup-YYYYMMDD-HHMMSS.zip.enc   # asks for the passphrase
docker compose start docsbot
```

## Scaling
`REDIS_URL` makes rate limits and lockouts shared across every app instance (compose starts Redis for you; without it, SQLite is used and shared by workers on one host). Users, chats, documents and the vector index are still local files, so run one app host (several workers are fine). Several hosts would also need Postgres, a Chroma server and shared storage.

## Test, evaluate, CI
```bash
pytest -q tests --ignore=tests/e2e     # API + security tests
pytest -q tests/e2e                    # browser tests (pip install pytest-playwright; playwright install chromium)
python -m eval.run_eval                # recall@1/k, MRR, automatic cross-role leakage checks (must be 0)
python -m eval.generate && python -m eval.run_eval eval/cases_generated.json   # benchmark built from YOUR documents (needs API key)
```
No internet for the embedding model? `EMBEDDING_BACKEND=hash` swaps in a simple offline stand-in (fine for the tests, not for judging real search quality).
`.github/workflows/ci.yml` runs the tests, the eval, the browser tests and a Docker build on every push.

## Deploy (Docker + automatic HTTPS)
```bash
cp .env.example .env     # fill in secrets, SMTP, DOMAIN and BASE_URL (your public https domain)
docker compose up -d --build
```

## Provider notes
- **SSO, Google:** `SSO_ISSUER=https://accounts.google.com`. **Okta:** `https://<org>.okta.com` (or `/oauth2/default`). Both work as-is.
- **SSO, Microsoft Entra:** `SSO_ISSUER=https://login.microsoftonline.com/<TENANT_ID>/v2.0` and `SSO_TRUST_EMAIL=1`. Entra sends no `email_verified` claim and often no `email`, so the app falls back to the UPN. Use a single-tenant directory only, since this trusts the directory for who owns an address.
- **Backups to S3:** a minimal IAM policy is `s3:PutObject` on `arn:aws:s3:::BUCKET/docsbot/*`. "Back up now" in the admin panel reports straight away whether the off-site copy worked and why not. If a non-AWS store (Backblaze B2, older MinIO) rejects uploads with a checksum error, set `AWS_REQUEST_CHECKSUM_CALCULATION=when_required`. Turn on bucket versioning or object lock so a compromised server cannot delete its own backups.
- **Offline model:** Chroma looks for its MiniLM files in `~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx/`. If the host cannot reach the download site, place `config.json model.onnx special_tokens_map.json tokenizer.json tokenizer_config.json vocab.txt` there.

## Troubleshooting
- **"The Gemini API rejected the API key"**: check `GEMINI_API_KEY` in `.env` (no quotes or spaces), create a key at aistudio.google.com/apikey, and restart.
- **"The model ... is not available for this key"** (404): set `LLM_MODEL` to a current model, e.g. `gemini-3.5-flash-lite` (cheap) or `gemini-3.8-flash` (strongest). Google restricts the older 2.5 models to existing users.
- **"quota or rate limit was reached"** (429): free-tier limits are low and a follow-up question makes two calls. Wait a minute, or enable billing on the key's Google Cloud project.
- With no key, or on any model error, retrieval still works and the matching passages are shown without a written answer.
