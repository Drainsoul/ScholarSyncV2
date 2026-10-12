# Legacy audit: ScholarSync v1

What v1 does, what it gets wrong, and which rules v2 has to keep. Audited 2026-10-11 from
https://github.com/Drainsoul/ScholarSync at commit `fa9974c` (266 commits). Every `file:line` reference below is at that
commit. v2 uses this file as its feature-parity checklist; the design lives in
`docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md`.

## 1. Overview
- **Purpose:** City of Taguig scholarship platform for two programs:
  - **TCU CEAA:** Taguig City University City Educational Assistance Allowance;
  - **LANI:** Lifeline Assistance for Neighbors In-need.
- **Roles:**
  - student;
  - `ceaa_admin`;
  - `lani_admin`;
  - `super_admin`.
- **Size:** about 81k lines.
  - Python: 9 modules; the largest are `app.py` (2,290 lines), `super_admin_routes.py` (2,393), `ceaa_admin_routes.py`
    (2,258) and `database.py` (2,037).
  - Front end: 30 JS files (up to 2,854 lines each), 27 CSS files and 35 templates.
- **Stack:**
  - Flask 2.3.3 and Werkzeug 2.3.7;
  - raw psycopg2 against PostgreSQL on Aiven;
  - Authlib for Google OIDC;
  - `smtplib` over Gmail;
  - a scikit-learn 1.6.1 pickle;
  - vanilla JS and CSS, with no build step;
  - gunicorn on Heroku, deployed by a GitHub Actions force-push;
  - domain `scholarsync.site`.

## 2. Feature inventory (parity checklist)
Status: **wired** = works end to end; **partial** = mixes real and fake data; **fake** = simulated in the browser only;
**missing** = in the v1 README but never built; **broken** = exists but fails.

| Area | Feature | v1 status | v2 milestone |
|---|---|---|---|
| Auth | Email sign up / sign in | wired (but role self-assignable, no verification) | M4 |
| Auth | Google sign-in | wired (wipes the profile on every login) | M4 |
| Auth | Forgot / reset password | wired | M4 |
| Auth | OTP at signup | removed (tests still reference it) | dropped (allauth email verification instead) |
| Student | Home: distribution and claim info (times claimed, received, remaining, next date, location) | partial (`publish` flag ignored; amounts hard-coded in JS) | M10 |
| Student | Profile: personal, family, education, photo, completion tracker | wired (photo as base64 in a TEXT column) | M6 |
| Student | AI scholarship match | wired but fragile (see §4) | M7 |
| Student | Choose program (`scholarship_choice`) | wired (student sets their own `scholarship_type`, which drives LANI pay) | M7 (eligibility decides) |
| Student | Program pages with benefits | partial (benefits hard-coded in `index.js`, `lani.js`) | M6/M7 |
| Student | Apply to CEAA / LANI with documents | wired (two near-identical 180-line handlers) | M7 |
| Student | Application status | wired | M7 |
| Student | Help center: FAQ and guides | wired (static) | M12 |
| Student | Help center support form | fake (`setTimeout` + `alert`) | M11 |
| Public | Footer newsletter | fake | dropped unless requested |
| Public | FAQ / privacy / terms pages | missing (links to `#`) | M12 |
| Staff | Dashboard: stats, chart, tasks, distribution settings, report upload | CEAA wired; LANI partial (localStorage fallback) | M11 |
| Staff | Applications: list, filter, edit, approve → scholar, reject | wired (approve deletes the application) | M8 |
| Staff | Application documents: review, approve/decline, view, upload on behalf | CEAA wired; LANI upload fake | M8 |
| Staff | Scholars: list, filter, paginate, edit, delete, year level | wired | M9 |
| Staff | Scholar documents: approve/decline, download | wired; "sample" download fake (`ceaa_admin_scholars.js:1881-1918`) | M9 |
| Staff | CSV import of scholars | fake (browser only, nothing saved) | M9 |
| Staff | CSV export / "PDF" export | partial (browser CSV; PDF is `window.print()`) | M9 |
| Staff | Allowance records: approve/reject/revert (password check), batch | wired (N+1; LANI batch sends no email) | M10 |
| Staff | Distribution settings (date, frequency, location, publish) | wired (CEAA admin can write LANI rows) | M10 |
| Staff | Tasks | wired (super admin: localStorage only) | M11 |
| Staff | Reports upload | wired (LANI writes to Heroku's ephemeral disk) | M11 |
| Staff | Documents module page | broken (`/ceaa_admin_documents` renders a missing template) | M8/M9 (built into review screens) |
| Staff | Notifications center | missing (unused mock JS only) | M11 |
| Staff | Financial management (budget, committed, utilization) | missing | M10 |
| Office | Dashboard: cross-program stats, 2 charts | partial (seeded sample scholars, localStorage tasks) | M11 |
| Office | Scholars across programs: CRUD, bulk delete, update year levels, documents | wired (responses embed every file as base64) | M9/M11 |
| Office | Admin accounts CRUD | wired (can edit or delete any user, including students) | M11 |
| Office | Reports review | wired (can't download LANI report files) | M11 |
| Office | Program management (add programs) | missing | M11 (programs are data) |
| Office | Analytics (trends, success rate, approval time, top feeder school) | missing | M11 |
| Office | Admin permissions | missing | M4 (memberships: head / staff) |
| Email | Application confirmation, allowance approved, password reset | wired (sync SMTP per message, unescaped `str.replace`) | M4 (infra), M7/M10 (messages) |

## 3. Business rules v2 must settle
The sources contradict each other. v2 keeps one source of truth (`BenefitTier` and the `Program` rules), seeded from the
**admin** rate tables, and Kenneth confirms the amounts (`STATE.md` → Open questions).

| Rule | v1 source |
|---|---|
| CEAA allowance per semester: 10,000 with merit, 5,000 without | `ceaa_admin_routes.py:1714, 1857`; `ceaa_admin_allowance.js:37` |
| LANI allowance per semester (without / with merit) | `lani_admin_routes.py:925-938`, copied in `lani_admin_allowance.js:169-176` |
| — honors, premier, priority | 20,000 / 25,000 |
| — basic plus | 10,000 / 15,000 |
| — basic, SUC/LCU | 7,500 / 12,500 |
| — review | 15,000 / 20,000 |
| — lead | 30,000 / 50,000 |
| — unknown types | fall back to "basic" |
| Same amounts shown to students, "per semester" | `templates/scholarship_choice.html:379-544` |
| ML tier amounts that **disagree**: CEAA merit 10,000 / basic 5,000; LANI merit 15,000 / basic 10,000 | `app.py:290-296` (dropped in v2) |
| Merit is a checkbox the student ticks, not derived from GWA | `app.py:1569-1577, 1986-1991`; `tcu_ceaa.js:181, 249` |
| GWA input must be 1–100 | `app.py:1850`; `ceaa_admin_routes.py:128, 720` |
| Grading scales differ: CEAA stores a percentage; LANI uses 1.0–5.0 (lower is better) | `ceaa_admin_database.py:26` (INTEGER); `database.py:412` (NUMERIC) |
| Terms: 1 = 1st semester, 2 = 2nd, 3 = summer | `app.py:1579-1586`; `ceaa_admin_allowance.js:42-44` |
| CEAA renewal (shown as text only): GWA ≥ 80% and ≥ 15 units | `templates/tcu_ceaa.html:168` |
| LANI renewal (text only): SWA "not lower than 2.5" (ambiguous on a 1–5 scale), ≥ 15 units, no failing/incomplete/dropped subjects | `templates/lani.html:101-157` |
| Allowance requirements are "complete" only when every scholar document is approved | `ceaa_admin_routes.py:1581-1587` |
| Distribution settings: date, `frequency_per_year`, claim location, per scholarship type | `ceaa_admin_database.py:147-160` |
| Required documents: jhsCert, validId, birthCert, votersCert, the `*Renewal` variants, alsCert, deathCert | `templates/lani.html:307-390`; `templates/tcu_ceaa.html:298-381` |
| Residency is calculated for display only; voter status and residency are never enforced | `lani.js:939`; `tcu_ceaa.js:380` |
| Dead client-side rules (never loaded): pass 75%, merit 90%, ≥ 3 years residency, TCU → CEAA, others → LANI | `static/scripts/scholarship_matcher.js:7-165` |

## 4. The "AI" matcher
- `scholarship_tier_model.pkl` (2.9 KB, added in `e7309b6`) is a scikit-learn `Pipeline`:
  - `StandardScaler` on `grade` and `income`;
  - `OneHotEncoder(handle_unknown='ignore')` on `school_name` and `school_type`;
  - a multinomial `LogisticRegression`.
- **Known categories:** schools Taguig City University, University of Santo Tomas and University of the Philippines;
  types public and private. Any other school encodes as all zeros.
- **Classes:** `CEAA_Basic`, `CEAA_Merit`, `LANI_Basic`, `LANI_Merit`, `NotEligible`.
- **There is no training code or data anywhere in the history.** Treat it as a toy model.
- **Flow** (`POST /match`, `app.py:592-647`):
  1. The form takes a free-text school and a GWA on the 1–100 scale.
  2. The GWA becomes `1.0 + (gwa - 70) * 0.1`, clamped to 1–4 (`app.py:272`).
  3. `income` comes from `family_background`, but no code ever writes it, so it is always 0.
  4. `school_type` comes from one arbitrary education row.
- **Unused:** course, residency and voter status.
- **Dead or broken:**
  - `/generate_scholarship_match` always errors (`app.py:1839-1875`);
  - `confidence_display` is never set.
- **v2:** program rules decide eligibility. The model is ported to pure Python as an advisory hint (program + merit only),
  with a parity test.

## 5. Data model (v1)
- **Schema setup:** there are no migrations. `CREATE TABLE IF NOT EXISTS` and guarded `ALTER`s run at import in every
  worker (`app.py:91-190`), and some run inside request handlers (`ceaa_admin_routes.py:2043` and others). On a fresh
  database the order is broken: LANI tables are created before `users`.
- **Core tables:**
  - `users`;
  - `user_profiles`, with the photo stored as base64 TEXT;
  - `family_background`, whose `income` is never written;
  - `education_records`, which are deleted and reinserted on every save;
  - `password_reset_tokens`, stored in plaintext;
  - `user_sessions`, never used;
  - `user_documents` / `document_files`, queried but never created.
- **One copy of each table set per program:** applications, documents, files (BYTEA), scholars, scholar documents,
  reports and tasks.
  - The copies differ in PK names (`application_id` vs `id`), columns (`scholar` vs `full_name`, `student_number` vs
    `student_id`), GWA type (INTEGER vs NUMERIC), reason columns (`decline_reason` vs `rejection_reason`), and storage
    (BYTEA vs disk paths).
  - `lani_application_documents` and `distribution_and_claim` are each defined twice, with different columns.
- **Approval** copies the application row and every file blob into the scholar tables, then **deletes the application**
  (`ceaa_admin_database.py:1141-1331`, `lani_admin_database.py:529-727`).

## 6. Routes (v1, ~158)
- **Auth** (`app.py`):
  - `/auth`;
  - `/login/google` and its callback;
  - `/forgot_password`, `/reset_password/<token>`;
  - `/logout`, `/force_logout`.
- **Student pages:** `/`, `/profile`, `/scholarship`, `/scholarship_choice`, `/tcu_ceaa`, `/lani`, `/help_center`,
  `/match`.
- **Student JSON:**
  - `/api/profile/{load,summary,save}`;
  - `/api/ceaa/{apply,status}`, `/api/lani/{apply,status}`;
  - `/api/distribution/user`;
  - `/api/update_scholarship_type`.
- **CEAA admin** (`/api/ceaa/admin/...`, POST plus verbs in URLs): applications, documents, scholars, scholar documents,
  allowance (+ batch, + revert with `verify-password`), tasks, reports, distribution.
- **LANI admin** (`/api/lani_admin/...`, PUT, a different URL layout): the same feature set, plus `stats/*`; no endpoint
  to list reports.
- **Super admin** (`/api/super_admin/...`): scholars (combined, bulk delete, `update_years`), documents, admins, reports,
  stats.
- **Misc:**
  - `/debug/scholarship-type` returns tracebacks to any role;
  - `/api/health/db` is public.
- **Shape and auth:** HTML pages are empty shells; all data loads from JSON, and each program returns a different
  response shape.

## 7. Problems, ranked
**Security**
1. **Role self-assignment:** signup accepts `account_type=super_admin` (`app.py:717, 737-747`).
2. **Secrets exposure** (§8).
   - The fallback `SECRET_KEY='please-set-a-secret-key-in-env'` (`app.py:33`) lets anyone forge a session if the
     environment variable is missing.
3. **Stored XSS:**
   - About 260 `innerHTML` writes render student names and courses unescaped in admin tables
     (`ceaa_admin_scholars.js:772`, `super_admin_scholars.js:233`, …).
   - Uploads are served inline with the MIME type the client sent (`ceaa_admin_routes.py:377-412`).
4. **Leaked password hash:** `password_hash` is returned by `/api/profile/save` (`app.py:1486, 1510`).
5. **No CSRF and weak session handling:**
   - no CSRF protection anywhere;
   - an open redirect via `next` (`app.py:702`);
   - no login throttling or password policy;
   - `email_verified` is never checked;
   - the role is read from a client-side session cookie, and sessions can't be revoked;
   - `Secure` cookies are off by default.
6. **Authorization gaps:**
   - a CEAA admin can write LANI distribution rows;
   - students set their own `scholarship_type`;
   - the super admin "admins" API edits any user;
   - report PUT accepts any column name;
   - the uploader ID is taken from a form field.
7. **No upload controls:** no type allowlist (`lani_admin_routes.py:1321`), no global size limit, and the MIME type
   comes from the client.
8. **PII in logs:** about 570 `print`s, including emails, request payloads and a reset-token prefix; 616 `console.*`
   calls.

**Structure and performance**
- **Duplication:** CEAA and LANI are 67–99% copies across templates, CSS and JS; backend overlap is about 25% (routes) to
  45% (DB layer), and the copies have drifted.
- **Connection handling:**
  - 3 connection pools per worker (up to 30 connections);
  - connections leak on exceptions;
  - when the pool is exhausted, `get_connection` sleeps and returns `None`.
- **N+1 queries:** in allowance records and document lists, plus repeated `information_schema` lookups on every request.
- **Error handling:** about 420 broad `except` blocks, and about 118 places return `str(e)` to the client.
- **Blocking I/O in requests:** SMTP and the Google picture download run inside requests, hidden by gunicorn's
  `--timeout 300`.
- **History lost on approval**, and blobs copied around inside Postgres.

**Frontend**
- **No base layout:** each page repeats its own `<head>`. `navbar.js` loads twice and polls `/api/profile/load` every
  5 s, with the base64 photo in the response.
- **Global functions:** about 70 exported on `window`, about 350 inline `onclick` handlers, and silent duplicate
  definitions.
- **Copied utilities:** for example, `showNotification` exists in 9 copies.
- **CSS:** conflicting `:root` tokens and about 1,900 `!important`s.
- **CDN dependencies:** a Font Awesome beta, two FA versions, the Tailwind runtime CDN, and no SRI hashes.
- **Accessibility:** no `alt` text, nav items built from `div`s, `outline: none`, and about 120 `alert`/`confirm` calls.

**Ops and tests**
- **Tests:** about 106 `unittest` tests, all mocked; none touch Postgres, and the model is never exercised.
- **Stale CI:** the OTP tests target deleted routes, so CI likely fails, and with it the deploy. CI runs Python 3.9 (end
  of life) while runtime uses 3.12.
- **Junk committed to git:** `__pycache__/`, `tempCodeRunnerFile.py`, Windows `.lnk` shortcuts, five 2.1 MB uploaded
  PNGs, and GitHub Pages `CNAME` leftovers.

## 8. Secrets exposure (values deliberately not copied here)
| Kind | Where | Commits |
|---|---|---|
| Aiven Postgres host + password | hard-coded fallbacks in `database.py` and `main.py` | `f2e1e2f` → `43cdc4e`; `709f525`. **Still in the current tree** inside `__pycache__/database.cpython-312.pyc`, with the same password as before the "rotated keys" commit |
| Google OAuth client ID + secret | `app.py` | `e895486` → `43cdc4e` |
| Gmail SMTP user + app password | `app.py` fallbacks | `4c05f50`, `3dc56e5`, `d29792b`, `447b14c`, `bfe11e6` → `43cdc4e` |
| Flask `SECRET_KEY` | `app.py` fallbacks | `2d8d6c7`, `1348d97`, `3d838b5`, `b6e9fe6` |

The repo is public. All four must be rotated or revoked, the old database deleted, and the repo made private or its
history purged. This is Kenneth's action; v2 never touches the legacy repo.

## 9. Dependencies (v1)
**Outdated or vulnerable:**
- gunicorn 20.1.0 (CVE-2024-1135, CVE-2024-6827);
- Werkzeug 2.3.7 (CVE-2023-46136, CVE-2024-34069, CVE-2024-49766/49767);
- requests 2.31.0 (CVE-2024-35195, CVE-2024-47081);
- Authlib 1.3.0 (CVE-2024-37568 and later issues);
- Flask 2.3.3.

**Unused or near-unused:**
- email-validator (never imported);
- Flask-Login (no `LoginManager`);
- pandas (one DataFrame for the model);
- scikit-learn (pinned only so the pickle loads).
