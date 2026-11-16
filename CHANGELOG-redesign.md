# UI redesign + Profile page

## What changed
| Area | Files | Notes |
|---|---|---|
| Design system | `static/index.html` | New light theme (indigo/teal on soft grey-blue), optional dark theme in navy (never black), Inter font with Kannada fallback, CSS variables for every colour, 150 ms transitions, `prefers-reduced-motion` respected. Theme choice is remembered and defaults to the system setting. |
| Layout | `static/index.html` | Sticky header with brand, theme switch and avatar; chat as bubbles; source cards; floating question bar; login hero. Every existing element ID, form field and `data-` hook is unchanged. |
| Profile page | `static/index.html`, `app/main.py` | Click the avatar. View mode, Edit mode, inline validation, Save disabled until valid and changed, unsaved-changes warning, read-only fields with lock icon, photo upload with square crop and preview, toasts, skeleton while loading. |
| Profile API | `app/main.py` | `GET/PATCH /api/profile`, `POST/GET/DELETE /api/profile/avatar`. Always the signed-in user; unknown or read-only fields are rejected with 422; field-level error messages; 20 edits/min and 5 uploads/min limits. |
| Photos | `app/main.py` | PNG/JPEG/WebP only, 2 MB, real type read from the bytes, 25 MP cap, centre-cropped to 512x512, re-encoded to WebP (drops EXIF and hidden payloads), random file name in the data folder, private to the owner. |
| Database | `app/main.py` | One new table `profiles` (created with `create table if not exists`). Nothing existing is altered. Deleting a user deletes their profile and photo. |
| Backups | `app/main.py`, `app/restore.py` | Photos are included in backups and restored. |
| Security headers | `app/main.py` | CSP now allows `img-src 'self' blob: data:` (needed for the avatar preview). |
| Audit | `app/main.py` | `profile_update` (field names only, never values), `avatar_update`, `avatar_remove`. |

## Configuration
`DEPARTMENTS=CSE,ISE,AIML,ECE,EEE,ME,CV,Other` (comma list) sets the department choices.
Editable: full name, department, semester (1 to 8), section, phone, about me, photo.
Read-only (shown with a lock): username, email, role.

## How to roll back
- UI only: restore the previous `static/index.html` (from your earlier download or version control). The new API endpoints are harmless without it.
- Profile feature: remove the `# ---------- profile` section of `app/main.py`. To delete the data too: `DROP TABLE profiles;` and delete `data/avatars/`. No other table depends on it.
- Nothing else was changed in the database, the routes or the request shapes.

## Verification
- Full suite: API tests, profile tests (17), integration tests, and browser tests (8) all pass with the real MiniLM model. The previous tests were not edited to make them pass.
- Contrast: every text/background pair in both themes is checked against WCAG AA (>= 4.5:1) by `tests/test_profile.py::test_theme_colours_meet_wcag_aa`.
- axe-core (WCAG 2.1 A/AA) found 0 violations on login, chat, admin panel, profile view and profile edit with an error showing, in light and dark. (Run it yourself: `npm i axe-core`, then `AXE_JS=node_modules/axe-core/axe.min.js pytest tests/e2e/test_a11y.py`.)
- Screenshots at 390, 768 and 1280 px are in `screenshots/before` and `screenshots/after` (after includes dark mode, profile view/edit and the admin panel).

## Not done / worth knowing
- The photo "crop" is an automatic centre crop with preview, not a drag-to-position cropper.
- There was no feature flag for the old look. The previous `index.html` is the way back.
- Tested in Chromium only; no real-device check.
