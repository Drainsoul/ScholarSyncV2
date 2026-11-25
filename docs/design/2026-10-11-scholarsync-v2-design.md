# ScholarSync V2: design spec

- **Revision:** 2 (2026-10-28): M3 design-system details (§3, §12, §13, §14, §15, §16), proposed for M3.
- **Revision:** 3 (2026-10-28): §12 visual redesign (UI UX Pro Max: Accessible & Ethical + Swiss; Lexend + Source Sans 3;
  navy actions, red brand mark only) after the maintainer's M3 mockup review.
- **Revision:** 4 (2026-10-30): §12 redesign on the maintainer's canvas (red primary, blue secondary, yellow accent; white
  sidebar shell; cards; status as coloured text). Boards in `docs/design/2026-10-30-redesign/`.
- **Revision:** 5 (2026-10-30): open source and self-hosting. Vercel is no longer the deployment target; the app runs
  from one `docker compose up` and on any container host with any provider (§1, §2, §5, §7, §9, §11, §14-§19, new
  M3.5). Design: `docs/design/2026-10-30-open-source-self-hosting-design.md`.
- **Revision:** 6 (2026-11-03): §12 denser after the maintainer's mockup review (14 px body, 36 px controls, 208 px
  sidebar); figures become one line under the page header; the page column is centred. Mockups approved.
- **Revision:** 7 (2026-11-03): M4 decisions: accounts, outbox, consent, areas (§3, §4.1, §4.3, §6, §9, §10, §14, §16);
  M4 final-review follow-ups (§9, §10, §14).
- **Revision:** 8 (2026-11-06): M5 decisions: files (§4.4, §7, §14, §16).
- **Revision:** 9 (2026-11-08): M6 decisions: reference data and student profile (§4.1, §4.2, §4.3, §5, §16).
- **Revision:** 10 (2026-11-10): M7 decisions: matching and student applications (§4.2, §4.5, §5, §8, §9, §16).
- **Revision:** 11 (2026-11-13): M8 decisions: application review, awards created on approval, M8b on-behalf (§4.5,
  §4.6, §5, §6, §7, §9, §16, §18).
- **Revision:** 12 (2026-11-14): M8 follow-up: bulk, queue, review-screen and head/staff decisions;
  a rejection stands for its term; the "Returned earlier" banner; the match page's held and rejected sentences (§4.5,
  §5, §6, §8, §12).
- **Revision:** 13 (2026-11-14): M8b decisions: on-behalf applications, rule override, staff uploads, read-only
  student view (§4.5, §5, §6, §7, §9, §16, §18).
- **Revision:** 14 (2026-11-16): M9 decisions: scholars, renewals, term change and rollover; import and export split
  into M9b (§4.5, §4.6, §5, §6, §8, §16, §18).
- **Revision:** 15 (2026-11-17): M9b decisions: manual and imported awards, the import purpose, direct-download
  exports (§2, §4.4, §4.6, §5, §6, §7, §16, §18).
- **Revision:** 16 (2026-11-17): M10 decisions: one live payout per term, amounts from the term's tier and confirmed
  merit, head-only approve and release, budget year from the distribution date, the student payout view (§4.7, §5,
  §6, §9, §16, §18).
- **Revision:** 17 (2026-11-17): M11 decisions: M11 split into M11 (dashboards, notifications, tasks, support), M11b
  (office management and program settings) and M11c (reports and analytics); notifications, personal tasks, the
  support inbox (§3, §4.8, §5, §9, §12, §16).
- **Revision:** 18 (2026-11-17): M11b decisions: program lifecycle, history-safe tiers and documents, staff accounts
  with a set-password email, memberships, settings, schools; cross-program scholars and the audit viewer move to
  M11c; Django admin stays out (§4.1, §4.2, §5, §6, §9, §10, §16).
- **Revision:** 19 (2026-11-18): M11c decisions: program reports and their review, staff and office notifications,
  analytics and the program summary, cross-program scholars, the audit log for the office and heads; exports stay
  direct downloads; office tasks and Chart.js are not planned (§4.4, §4.8, §5, §6, §7, §9, §12, §16).
- **Revision:** 20 (2026-11-18): M12 decisions: CSP enforced by default with no report-uri; secret URLs redacted in
  logs, the access log and Sentry; no-store on signed-in pages; sign-in events audited; file access by purpose; import
  files removed after 7 days; double posts never 500; the ASVS 5.0 L2 review; the WCAG 2.2 AA audit with axe-core;
  query budgets on every page; the hosting guide walked on a clean checkout, with backups, a runbook and HSTS preload
  guidance (§7, §10, §11, §12, §13, §16, §17, §18).
- **Revision:** 21 (2026-11-19): M13 decisions: two-factor sign-in required for staff and the office in
  production; a breached-password check; optional ClamAV scanning; idle (30/60 min) and 12-hour session limits
  with a warning; session-key rotation on reauthentication; a session list, the office's Sign out everywhere and
  `end_sessions`; unencrypted services refused in production; a least-privilege database role; request ids in
  logs; names in search URLs accepted; the numeric-password rule dropped (§6, §7, §10, §12, §14, §16).
- **Revision:** 22 (2026-11-19): settled while building M13: a clamd on another machine counts as an unencrypted
  service; the owner's database URL is removed from the environment before the app starts; email URLs use
  `submission://` or `?ssl=true` (`smtp+tls://` was never a parser scheme) and an unknown scheme stops startup;
  both reauthentication pages rotate the session key; signing out other sessions is audited; session-list rows go
  once their session ends; privacy notice version 2026-11-19 (§7, §10, §14).
- **Revision:** 23 (2026-11-19): M14 decisions: the office doesn't send program reports; summer records don't count
  toward `max_terms`; a renewal approved out of order never moves an award's tier back; a reverted payout's "ready to
  claim" notice stays (§4.6, §4.8, §9).
- **Revision:** 24 (2026-11-19): the maintainer's decisions after M14: 2FA secrets and recovery-code seeds are encrypted at
  rest (ASVS V6.5.2); V14.2.1 and the M14 decisions confirmed; the repository is published with a fresh history
  (the old GitHub repository is replaced by an empty one with the same name; the local history keeps every commit,
  rewritten so no commit contains private working notes; pushing waits for the maintainer); the specs live in `docs/design/`, and private working notes
  stay local, with `CONTRIBUTING.md` as the contributor guide (§10, §14, §19).
- **Revision:** 25 (2026-11-19): `/` has no page of its own: it sends signed-out visitors to the sign-in page and
  signed-in users to their own home, and signing out lands on the sign-in page (§5, §10).
- **Revision:** 26 (2026-11-20): student screens and account pages reworked: the student home shows profile
  completion as a small ring beside a month calendar of release days and application windows; the profile overview
  is read-only with an Edit button per section; the model hint moves to the top of Find scholarships as a compact
  note; the session list and the two-factor pages render inside the signed-in app shell, and the session list
  counts live sessions from the session table; the demo gives LANI an application window when it has none
  (§5, §10, §11, §12).
- **Revision:** 27 (2026-11-20): staff screens reworked: the staff dashboard drops "Applications by month" for a month
  calendar of the user's task due dates, the program's distribution days and its application window, with "Needs
  attention" beside it; the Tasks page lists tasks only and "Add task" opens the form in the app dialog; the office
  gets its own tasks and the same calendar on its overview; image
  documents on the review screen open in a preview dialog instead of downloading; the demo's sample PDF is a valid
  one-page document; PDF documents and report files open in the same preview dialog, drawn by pdf.js (§4.9, §5,
  §11, §12).
- **Revision:** 28 (2026-11-20): platform polish from a modern-web-guidance scan: modal dialogs fade and scale in
  (entry only), keep scrolling from reaching the page beneath, and read-only preview dialogs also close on a click
  outside them; textareas grow with their text; paragraphs and list items wrap without orphans (§12).
- **Revision:** 29 (2026-11-20): a dark theme that follows the device, with Light / Dark / System in the account
  menu; the account menu and the program and term switchers become popovers that close on an outside click or Esc;
  pages cross-fade on navigation where the browser supports it (§5, §12).
- **Revision:** 30 (2026-11-21): toasts drop the white card with a coloured left stripe for a flat, solid chip in the
  "Copied" bubble's family: ink for success and info, yellow for warnings, red for errors, each with its icon (§12).
- **Revision:** 31 (2026-11-21): the sign-in pages (auth layout) offer the same Light / Dark / System choice at the top
  right of the form column (§12).
- **Revision:** 32 (2026-11-21): on the sign-in pages the theme choice is three icon buttons (sun, moon, monitor),
  and the demo's test-account notice is collapsed behind a "Exploring ScholarSync? Use a test account" button that
  expands it (§11, §12).
- **Revision:** 33 (2026-11-21): the maintainer's answers to §18: a student holds one scholarship at a time; at-risk
  is removed; a staff member's program report goes to the program head, who approves or returns it and then sends it
  to the scholarship office; staff may file for a self-registered student found by the exact email of their account;
  no term limit (a scholar continues while enrolled and meeting the renewal rules); heads set the budget the office
  gives them; LANI's tiers and amounts follow the TCU LANI page and CEAA's renewal rule the TCU-CEAA site; retention
  follows RA 10173 and is the host's policy; every date on the calendars opens a dialog with that day's items
  (§3, §4.5, §4.6, §4.8, §5, §6, §9, §12, §16, §18).
- **Revision:** 34 (2026-11-21): settled while building M15: staff read the one-scholarship refusal in the third
  person ("This student already holds the {program} scholarship. A student can hold one scholarship at a time."),
  and reinstating an ended award is refused the same way while another is held; a draft opened before rev 33 can
  still be submitted (start and approve are refused); the office scholar list keeps its "Other programs" column for
  older rows. The email lookup answers in place (400 for a blank or invalid address, 429 at the limit), its "File an
  application" button carries a signed token valid for one hour, and the 30-a-day limit counts across all of a
  user's programs, the office included. Reports: an approve note is kept in `review_note` and an approve without a
  note leaves an earlier office return note in place; a stale approve reads "This report was already approved."; a
  staff resend says "Report sent to the head again."; the office's Returned tab can show a head's return. Day
  dialog: release rows link "Open release day", link names include the event title, and a title that only repeats
  its kind is hidden; dates in day URLs are real dates from 2000 to 2100 (`isodate`), anything else is a 404 (§4.5,
  §4.8, §12).
- **Revision:** 35 (2026-11-21): support replies (M16). Staff, heads and the office answer a student's message in
  the app or by an email written and sent from the app; the office keeps reply templates; program staff and heads
  get a support inbox for their program; students read answers under "Replies" in Help and guides; who answered and
  when is shown to staff, heads and the office only. Lifts the rule that support text is never emailed, for staff
  replies only (§4.8, §5, §6, §9, §10, §12, §16).
- **Revision:** 36 (2026-11-25): a fuller demo. Ten test accounts in three groups (students: new student, applicant,
  returned applicant, scholar due to renew, scholar on hold; program staff: CEAA staff and head, LANI staff and head;
  the scholarship office). The login notice shows them as small grouped buttons with the shared password once; a
  listed account appears only once it exists and can sign in. More sample students (LANI applicants and scholars,
  rejected and withdrawn CEAA applications), reply templates for every topic and more program reports (§11).
- **Revision:** 37 (2026-11-25): submitting a new application (a draft or a returned one, by the student or by staff
  on their behalf) is refused while the student holds an award in another program, as starting and approving are.
  This closes the rev 34 edge where a draft opened before rev 33 could still be submitted (§4.5).
- **Status:** rev 1 approved by the maintainer on 2026-10-12.
- **Inputs:**
  - `docs/legacy-audit.md` (v1 features, rules and problems);
  - The maintainer's decisions of 2026-10-11 (§19);
  - Vercel's Django and Functions documentation (checked 2026-10-11).

## 1. Goals and non-goals
**Goals**
1. **Feature parity:** reach parity with every *wired* v1 feature (`docs/legacy-audit.md` §2) and build the missing
   README features that matter: notifications, financial management, analytics, program management.
2. **One generic system:** programs are data, so TCU CEAA, LANI and any future program share one codebase, one schema
   and one set of screens.
3. **Secure by default:**
   - real authentication with verified email;
   - roles that users can't assign themselves;
   - program-scoped authorization, CSRF, CSP, and private files;
   - an audit trail;
   - compliance with RA 10173 (Data Privacy Act).
4. **One source of truth for money and eligibility:** amounts, tiers and rules live in the database, can be edited by
   authorized staff, and every change is audited.
5. **Keeps history:** applications, terms, documents and disbursements are never deleted by normal workflows.
6. **Maintainable:** typed Python, thin views, services and selectors, real tests against Postgres, CI on every push.
7. **Runs anywhere a container runs, with a one-command local run** (§11): any PostgreSQL, any S3-compatible storage,
   any email service. Open source (MIT); nobody hosts an official copy.

**Non-goals (v2.0)**
- Migrating v1 data: this is a fresh start with seed data.
- A public JSON API or SPA, a native mobile app, SMS, or payments integration (disbursement is recorded, not paid
  out).
- Real-time features (WebSockets), dark theme, multi-language UI (English only; Filipino later).
- Retraining the legacy model.
- The maintainer hosting a public demo or production instance; a packaged desktop app; one-click deploy buttons for specific
  hosts; documenting a hosting path without Docker; branding through settings (rebranding is fork-and-edit); a
  published container image or release pipeline.

## 2. Stack
Versions are pinned to the latest stable release when M2 scaffolds the project, then recorded in the docs.

| Layer | Choice | Notes |
|---|---|---|
| Language/runtime | Python 3.13, managed by **uv** (`uv.lock`) | The Docker image pins the same version |
| Framework | **Django 5.2 LTS** | Supported until April 2028 |
| Settings | One `config/settings.py` reading the environment with **environs[django]** | `.env` for developers and self-hosters, compose defaults for the explore run |
| Database | **PostgreSQL 17** (any provider), **psycopg 3** | `DATABASE_URL`; an optional unpooled URL for migrations behind a transaction pooler |
| Auth | **django-allauth** (account + Google provider), **argon2-cffi** | Email login, mandatory verification, rate limits, reauthentication |
| Templates | Django templates + **django-htmx** + **django-template-partials** | `{% partialdef %}` for HTMX fragments |
| Front-end build | **Vite** + strict **TypeScript** + **Biome**, **django-vite** | Same tooling as PersonalWebsite |
| Charts / icons / fonts | CSS bar charts with a "View as table" (no chart library; M11c), **Lucide** SVG sprite, **Fontsource** Lexend + Source Sans 3 (self-hosted) | No runtime CDNs |
| Files | Any S3-compatible store via **django-storages** (S3 backend, boto3), **Pillow**, **filetype** | Private bucket, presigned URLs |
| Import/export | stdlib `csv`, **openpyxl** + **defusedxml** | Row-by-row Django Forms with a preview; all-or-nothing |
| Email | Any SMTP server (one URL-style setting) + an `EmailOutbox` table | Provider APIs via django-anymail only if they cost nothing extra |
| Security headers | **django-csp** | Report-only from M2, enforced at launch |
| Observability | **sentry-sdk** with explicit `data_collection` opt-outs (user info, cookies, bodies, query params, DB data, frame variables off; header allowlist) + `before_send` scrubbing, JSON logs to stdout | |
| Lint/type | **ruff** (lint + format), **mypy** + **django-stubs** | |
| Tests | **pytest**, pytest-django, pytest-xdist, factory_boy, Faker (`en_PH`), time-machine, coverage, **pytest-playwright** | Real Postgres in tests |
| Local services | `compose.yaml`: web, Postgres 17, an S3-compatible store, Mailpit, a worker | `docker compose up` runs the explore copy (§11) |
| Host | Any host that runs a container (`Dockerfile`, gunicorn) | Self-hosters build the image from source; none is published (§11) |
| CI | GitHub Actions | §15 |

**Deliberately absent:**
- background workers, Celery and Redis (we use an outbox plus a worker loop);
- a state-machine library (we use an explicit transition map plus database constraints);
- numpy, pandas and scikit-learn at runtime;
- jQuery, Tailwind and any UI framework.

## 3. Architecture
```
config/            settings.py, urls.py, wsgi.py
apps/
  accounts/        User (email login, role), ConsentRecord, allauth adapters
  programs/        Program, ProgramMembership, BenefitTier, RequiredDocument, School, AcademicTerm
  students/        StudentProfile, FamilyMember, EducationRecord, ProfileInvite, invite/claim
  files/           StoredFile, upload intents, presign/confirm/download
  applications/    Application, Document, DocumentFile, review services
  awards/          Award, ScholarTerm, renewals, term rollover
  money/           DistributionSchedule, Disbursement, Budget
  matching/        eligibility engine, legacy model hint (+ data/legacy_tier_model.json)
  reports/         Report, ReportFile
  workspace/       Task, Notification, EmailOutbox
  office/          super-admin views (no models of its own)
  kit/             design kit and key-screen mockups at /_kit/ (no models; off unless DJANGO_KIT; refused in production mode)
  core/            AuditEvent, permissions, mixins, layouts, health, errors, public information pages
templates/         base.html, layouts/{public,auth,student,staff,office}.html, partials/, components/, emails/
frontend/          src/{main,nav,dialog,toast,upload,charts,bulk}.ts, src/styles/{fonts,tokens,base,layouts}.css,
                   src/styles/components/*.css, src/icons/ (sprite list + own icons), scripts/sprite.mjs
scripts/           export_legacy_model.py
tests/             permission matrix, e2e (Playwright)
```

**Layers inside each app**
- `models.py`: fields, constraints, `TextChoices`. No business logic beyond invariants.
- `services.py`: every write, as functions with keyword-only arguments. Each is `@transaction.atomic`, validates
  transitions, writes an `AuditEvent`, and queues notifications.
- `selectors.py`: every non-trivial read. Querysets are scoped and use `select_related`/`prefetch_related`.
- `views.py`: class-based or function views that parse input with Forms, call a service or selector, and render a full
  page or an HTMX partial.
- `forms.py`, `urls.py`, `templates/<app>/`, `tests/`.

**Request flow (staff example):** `/staff/<program>/applications/` → `ProgramStaffRequiredMixin` resolves the `Program`
and checks the membership → a selector returns applications filtered by that program → the template renders the full
page, or only the table partial when `request.htmx`.

**State transitions:** each stateful model declares `TRANSITIONS: dict[Status, set[Status]]`. The service calls
`assert_transition(obj, new_status)`, and a `CheckConstraint` guards the allowed values.

## 4. Domain model
Every model gets `created_at`/`updated_at`. Money is `DecimalField(max_digits=12, decimal_places=2)` in PHP. Times are
aware (`USE_TZ=True`, `TIME_ZONE="Asia/Manila"`).

### 4.1 accounts
- **`User`** (`AbstractBaseUser` + `PermissionsMixin`):
  - fields: `email` (unique, login), `full_name`, `role` ∈ {`student`, `staff`, `super_admin`}, `is_active`,
    `is_staff` (unused: there is no Django admin), `last_login`;
  - signup always creates `role=student`;
  - only a super admin (via a service) or `create_office_admin` can create staff or super admins;
  - emails are stored stripped and lower-cased, and are unique on `Lower(email)`;
  - `create_superuser` exists only for Django's interface: `is_staff` + `is_superuser`, `role=staff`, no memberships.
    Django admin is not installed (M11b): it would let writes bypass services and audit events.
  - **Accounts in the app (M11b):** the office creates staff and office accounts (full name required); the person gets
    a `staff_welcome` email with a set-password link (allauth's reset-from-key URL, valid 3 days). An email that
    already has an account is a form error. Deactivating ends the account's sessions; nobody deactivates their own
    account or the last active office account.
- **`ConsentRecord`:**
  - fields: `user` FK, `notice_version`, `consented_at`, `ip_hash`;
  - recorded at signup and whenever the privacy notice changes;
  - it hangs off the user because a profile does not exist at signup; staff-created profiles record consent when the
    student claims them (M6).
- **`ProfileInvite`** (lives in `apps/students`, so claim services sit beside the profile and `accounts` never imports
  `students`):
  - fields: `profile` FK, `email` (lower-cased), `token_hash`, `expires_at`, `claimed_at`, `claimed_by`, `created_by`;
  - lets the owner of a staff-created `StudentProfile` claim it by verifying that email;
  - the link expires after 14 days; only the sha256 hash of the token is stored;
  - a link works once; sending it again expires every older link of that profile;
  - only a student whose account has a verified email equal to the invite's, and who has no profile yet, can claim;
  - consent is recorded at claim (`ConsentRecord`, §4.1 above); the claimant's `User.full_name` is set from the profile.

### 4.2 programs
- **`School`:** `name` (unique), `type` ∈ {public, private, SUC, LCU}, `grading_scale` ∈ {percent, one_to_five,
  four_point}, `is_in_taguig`.
- **`AcademicTerm`:**
  - fields: `school_year_start` (e.g. 2026), `term` ∈ {1, 2, 3 (summer)}, `starts_on`, `ends_on`, `is_current`;
  - `sort_key`: a generated column, `school_year_start * 10 + term`, for ordering and "latest ≤" lookups;
  - constraints: unique (`school_year_start`, `term`); at most one current term (partial unique).
- **`Program`:**
  - identity: `slug` (e.g. `tcu-ceaa`, `lani`), `name`, `description`, `is_active`;
  - window and limits: `applications_open_on`, `applications_close_on`, `max_terms`, `claim_location_default`; a
    blank open date means already open and a blank close date means no closing date (the seed sets neither);
  - **eligibility rules:**
    - `min_gwa_percent`, `max_gwa_one_to_five` (scale-aware thresholds), `min_units`;
    - `min_residency_years`, `requires_registered_voter`;
    - `allowed_school_types` (array), `allowed_schools` (M2M `School`, empty means any);
  - **renewal rules:** `renewal_min_gwa_percent`, `renewal_max_gwa_one_to_five`, `renewal_min_units`,
    `renewal_no_failing_grades`;
  - **merit rules:** `merit_min_gwa_percent`, `merit_max_gwa_one_to_five`.
- **`ProgramMembership`:**
  - fields: `user` (role=staff), `program`, `level` ∈ {head, staff};
  - constraint: unique (`user`, `program`).
- **`BenefitTier`:**
  - fields: `program`, `code` (e.g. `honors`), `name`, `base_amount`, `merit_amount`, `effective_from` FK
    `AcademicTerm`, `is_active`, `sort_order`;
  - constraint: unique (`program`, `code`, `effective_from`);
  - lookup: the amount for a term is the row with the latest `effective_from` ≤ that term;
  - **changes are history-safe (M11b):** adding, re-pricing or stopping a tier writes a row effective from the
    current term or later; a row any award, term record or application points to is never edited ("Records already
    use the {term} amounts for {tier}. Pick a later term."). Existing term records keep their row.
- **`RequiredDocument`:**
  - fields: `program`, `code`, `label`, `help_text`, `applies_to` ∈ {new, renewal, both}, `is_required`,
    `accepted_types` (pdf/jpg/png), `max_bytes`, `sort_order`, `is_active` and `required_since` (M11b);
  - **switched off, never deleted (M11b):** an inactive requirement leaves every open application;
  - **settings changes never block an application in review (M11b):** a draft follows the program's current list;
    once submitted, an application answers only to requirements whose `required_since` is on or before its
    `first_submitted_at`, plus any it already has an upload for (`applications.selectors.applicable_requirements`).
    `required_since` starts at creation and moves to "now" when a requirement is restored, made required, or asked
    of more applicants (`applies_to` widened);
  - caps: `max_bytes` is at most 10 MB (10,485,760), because the M5 document rule caps uploads there;
  - constraint: unique (`program`, `code`).

**Seed data** (`seed_programs`):
- TCU CEAA, with one tier `standard` (5,000 base / 10,000 merit).
- LANI, with tiers honors / premier / priority (20,000 / 25,000), basic plus (10,000 / 15,000), basic and SUC/LCU
  (7,500 / 12,500), review (15,000 / 20,000) and lead (30,000 / 50,000).
- The required documents from the v1 templates: both programs get the same list; rows with the same label and help
  text are merged into `applies_to=both`; every row takes at most 10 MB.
- Schools: Taguig City University (LCU, percent, in Taguig), University of the Philippines (SUC, 1-5) and University
  of Santo Tomas (private, 1-5), the three names in v1's model.
- Terms, if none exist: the school year containing today, starting 1 August. Term 1 runs 1 Aug-31 Dec, term 2 runs
  1 Jan-31 May and the summer term runs 1 Jun-31 Jul; the one containing today is current.
- Rules, from v1's forms (all pending §18 Q3/Q4):
  - CEAA: new GWA ≥ 80%, TCU only; renewal ≥ 80% and ≥ 15 units;
  - LANI: new GWA ≥ 75%, or ≤ 3.00 on the 1-5 scale (3.00 is the passing mark there, as 75% is on the percent
    scale; without it every UP and UST student is locked out under the §8 scale rule); renewal 1-5 GWA ≤ 2.50,
    ≥ 15 units, no failing grades.
  - The seed never overwrites an existing program, so an existing database needs `docker compose down -v` (or the
    settings page, M11b) to pick up new values.
- **Program lifecycle (M11b):** the office creates a program inactive (slug fixed from then on) and configures it;
  its settings pages open to the office only while it is inactive. Opening needs a tier in force and an active
  required document; closing is refused while applications wait for review (submitted, under review or returned,
  since a returned one may be resubmitted) or payouts are prepared or approved.
- These are the v1 admin values (`docs/legacy-audit.md` §3), pending the maintainer's confirmation.

### 4.3 students
- **`StudentProfile`:**
  - `user` (nullable, unique): null for staff-created or imported records until they are claimed;
  - name fields; `birth_date`; `sex`; `phone`;
  - the name fields are the source of truth: saving them also sets `User.full_name`;
  - address: `address_line`, `barangay` (choices: the list below, plus "I don't live in Taguig"); there is no
    `district` (v1 had a free choice with no barangay mapping, the EMBO districting is still changing and no rule uses
    it; add it when a rule needs it);
  - `residing_since` (year); `is_registered_voter`; `monthly_household_income`;
  - `photo` FK `StoredFile`;
  - `created_by`, and `created_for` (the `Program` a staff member created the profile for; null for self-created
    profiles). `/staff/<slug>/students/` lists only the unclaimed profiles created for that program;
  - `completion` is computed from required fields.
- **`FamilyMember`:** `profile`, `relation` ∈ {father, mother, guardian, sibling}, name, `occupation`,
  `monthly_income`, `contact`.
- **`EducationRecord`:** `profile`, `level` ∈ {elementary, jhs, shs, als, college}, `school` FK (nullable), `course`,
  `year_level`, `gwa` (Decimal), `gwa_scale` (a listed school's scale always applies; it is chosen only on the "not listed" fallback), `units`, `year_from`, `year_to`,
  `is_current`.
  - Fallback for schools not in the list (every elementary, JHS and SHS school, and colleges the office has not
    added): `school_name`, `school_type` and `gwa_scale`. Exactly one of `school` or `school_name` is set.
- **Barangays** (38, source "PSA PSGC, checked by the maintainer 2026-11-26; EMBO included per the maintainer, 2026-11-08"): Bagumbayan, Bambang,
  Calzada, Cembo, Central Bicutan, Central Signal Village, Comembo, East Rembo, Fort Bonifacio, Hagonoy, Ibayo-Tipas,
  Katuparan, Ligid-Tipas, Lower Bicutan, Maharlika Village, Napindan, New Lower Bicutan, North Daang Hari, North Signal
  Village, Palingon, Pembo, Pinagsama, Pitogo, Post Proper Northside, Post Proper Southside, Rizal, San Miguel,
  Santa Ana, South Cembo, South Daang Hari, South Signal Village, Tanyag, Tuktukan, Upper Bicutan, Ususan, Wawa,
  West Rembo, Western Bicutan. Ten of them are the EMBO barangays (transferred from Makati by the Supreme Court).
- **`ConsentRecord`:** lives in `accounts` (§4.1), because a profile does not exist at signup.

### 4.4 files
- **`StoredFile`:**
  - fields: `id` (UUID, so ids are never guessable), `key` (object-store key), `status` ∈ {pending, ready, rejected},
    `rejected_reason`, `original_name`, `declared_type`, `sniffed_type`, `size`, `sha256`, `uploaded_by`,
    `purpose` ∈ {document, photo, report, export, import};
  - `export` is reserved and unused (M11c): office-wide exports are direct downloads like M9b's (§7), so no export
    file is ever stored; M12 decides whether the choice is removed;
  - flow: §7.

### 4.5 applications
- **`Application`:**
  - fields:
    - `profile`, `program`, `term`, `kind` ∈ {new, renewal}; `award` (FK `Award`, renewal only; constraint
      `applications_renewal_has_award`: a new application has no award, a renewal has one), and
      `declares_no_failing` (nullable bool: the renewal declaration of no failing, incomplete or dropped subjects);
    - `requested_tier` FK `BenefitTier`;
    - academic: `school` (nullable FK), `school_name`, `school_type`, `course`, `year_level`, `gwa`, `gwa_scale`,
      `units`; the school fallback matches `EducationRecord`, and exactly one of the FK or the name is set once
      submitted;
    - the academic snapshot is copied from the current education record at submit, not at start, and the checks are
      re-run under the lock; the draft page shows the live profile values;
    - `match_snapshot` (JSON: eligibility result and model hint at submit time), `status`;
    - `submitted_at`, `first_submitted_at` (nullable; the first submit sets it and a resubmit leaves it, backfilled
      from `submitted_at`; the staff queue sorts by it, oldest first, so a returned application keeps its place),
      `decided_at`, `decided_by`, `decision_reason`, `created_by` (the student or staff);
    - `decision_reason` keeps the latest reason only. Return sets it and nothing else, since it isn't a decision;
      reject also sets `decided_at` and `decided_by`. Reasons are free text, so they stay out of audit `data`.
  - transitions:
    - `draft` → `submitted` (all required documents uploaded) or `withdrawn`;
    - `submitted` → `under_review` or `withdrawn`;
    - `under_review` → `returned` (needs fixes; reason required), `approved` or `rejected` (reason required);
    - `returned` → `submitted` or `withdrawn`;
    - `TRANSITIONS` is declared in full. The student drives start (creates a `draft`), submit (`draft` or `returned`
      → `submitted`) and withdraw (`draft`, `submitted` or `returned` → `withdrawn`);
    - staff drive start review (`submitted` → `under_review`, an explicit POST; the student can't withdraw after it),
      return, approve and reject. Return and reject need `under_review` and a reason of at most 1,000 characters;
    - approval needs:
      - `under_review`;
      - every required document `approved` (none `pending` or `declined`; a declined document means staff return
        the application);
      - a tier in force for the application's term (the requested tier is preselected);
      - no active `Award` for the same profile and program;
    - starting an application is refused ("You already hold this scholarship.") when the profile has an `approved`
      application for the program in that term, or an active award in the program;
    - a rejection stands for its term: starting is also refused ("This application wasn't approved for {term}. You
      can apply again next term.") when the profile has a `rejected` application for the program in that term. The
      check runs under the profile lock, beside the held check. Decided 2026-11-14 (M8); the maintainer to
      confirm;
    - an approval refused for a document names it: "{label} was never uploaded. Return the application so the
      student can add it." when a required document has no upload at all (named first, since deciding the others
      can't help), otherwise "Approve or decline every document first: {label}.";
    - **bulk actions** are "Start review" and "Approve" only, because return and reject need a reason per student:
      - each selected row runs the single-row service in its own transaction, in `profile_id` order, so every
        precondition is re-checked under that row's locks; bulk approve uses each application's requested tier;
      - at most 100 rows per request ("Choose at most 100 applications at a time.");
      - a row that fails is skipped with its reason: the summary reads "Approved 3 applications. Skipped 2." (or
        "Started review of …"), then one "{name}: {reason}" message per skipped row;
      - with HTMX the page reloads and the messages show after the reload (a toast would die with the page); without
        JS the POST redirects back to the queue with its filters kept;
      - "Approve" is offered only under the Waiting and Under review filters, since approval needs `under_review`;
    - resubmitting a returned application keeps the first snapshot and the requested tier, skips the window check
      (staff asked for fixes) and re-checks the documents only.
  - constraint: at most one *open* application (draft, submitted, under_review or returned) per (`profile`, `program`,
    `term`), as a partial unique index. A student may hold open applications to several programs (CEAA and LANI) in
    one term, but **one scholarship at a time** (rev 33, §18 Q6): while the student holds an `active` or `suspended`
    award in a program, starting an application to another program (the student or staff on their behalf) is refused
    with "You already hold the {program} scholarship. A student can hold one scholarship at a time.", and Find
    scholarships shows it as an unmet check. Submitting a new application (rev 37; never overridable on behalf),
    approving an application, adding a scholar by hand, importing a scholar
    and reinstating an ended award are refused the same way (staff read it as "This student already holds…", rev 34) when the student holds an award in another program, so of two open applications
    only the first approved one stands. The check runs under the `StudentProfile` row lock (the services' lock order),
    so two approvals can't race. It is a service rule, not a database constraint: rows from before rev 33 stay.
  - Approved applications are kept: they're the history.
  - **On behalf (M8b, decided 2026-11-14):**
    - two more fields: `on_behalf` (bool; `created_by` is then the staff member) and `override_reason` (text, at most
      1,000 characters), with constraint `applications_override_only_on_behalf`: a reason is stored only on an
      on-behalf row;
    - staff file for profiles created for their program (`created_for=program`), claimed or not, and (rev 33, §18
      Q16) for a self-registered student found by the exact email of their account. "File for a student" has a
      "Find a student by account email" form: a POST (the address never goes into a URL or a log), an exact,
      case-insensitive match on an active student account that has a profile, at most 30 lookups per staff member a
      day ("You've looked up 30 addresses today. Try again tomorrow."). A match shows the student's name and "File
      an application"; no match says "No student account uses that email." Each lookup is audited as
      `application.email_lookup` with the program and whether it matched, never the address. The later filing steps
      are scoped by the on-behalf application's program, not by the profile's `created_for`, and staff still never
      write the student's profile. Imports and manual scholars keep matching within the program's own students;
    - staff drive the whole application: start (a `draft`), school and grades (draft only), documents (draft or
      returned, with the student-side rules), submit and resubmit (a resubmit keeps the snapshot and tier and
      re-checks the documents only), and withdraw (draft or returned). After submit it goes through the unchanged M8
      review, and the staff member who filed it may also review it (separation of duties waits for §18 Q7);
    - **academics** live on the application only: staff never write the student's profile. A staff form fills them on
      the draft and they freeze at submit, as for students: "The school and grades are frozen once the application is
      submitted." The form requires a school (a listed one, or a typed name
      with its type and grading scale), because `applications_submitted_has_school` would refuse the submit
      otherwise; course, year level, GWA and units are optional, and a blank one shows as a missing check;
    - **override:** staff see the live checklist. When any check is `unmet` or `missing`, submitting needs a reason
      ("This student doesn't meet every rule. Say why you're filing anyway."). Every check is overridable, including
      the window; the school check is always met. No current term is never overridable ("Applications aren't open: the
      scholarship office hasn't set up the current school term."). The reason is free text, so it stays out of audit
      `data`, which (like the snapshot) holds only the overridden check codes; an eligible application stores no
      reason. Submitting on behalf skips the "personal details" completion check, since staff are the contact;
    - **tier:** it comes from `tiers_in_force(program, term)`, never from `result.tier_candidates` (empty when a rule
      fails). One tier is chosen automatically, otherwise staff pick; a program with no tiers can't be filed for ("This
      program has no allowance tiers set up yet.");
    - **start refusals,** checked under the profile lock: the program isn't active (404); the student holds the
      scholarship ("This student already holds this scholarship."); rejected this term ("This student's application wasn't approved for {term}. They can apply again
      next term."); the student's own open application for the program and term ("This student already has an
      application for {program} this term. They need to finish or withdraw it."). An open on-behalf application is
      returned, not duplicated, and a race with a student start is caught on `applications_one_open_per_term`;
    - **the student's view is read-only**: a student who has claimed the profile sees it in
      `/me/applications/` with "{program} staff filed this application for you.", with upload, submit and withdraw
      hidden. The student services refuse an on-behalf row whatever the template shows ("The scholarship office filed
      this application for you. Contact them to change it."), and starting from `/me/applications/new/<slug>/` while
      an on-behalf one is open lands on it.
  - **Renewals (M9, decided 2026-11-16):**
    - a renewal is an `Application` with `kind=renewal` and `award` set. It shares
      `applications_one_open_per_term` with new applications, and reuses the student pages, documents (`applies_to`
      renewal or both), withdraw, resubmit, emails and the M8 review;
    - **due** when the award is `active`, a current term exists and is a semester (term 1 or 2), the award has no
      `ScholarTerm` for it, and no open, approved or rejected renewal of that award exists for it. The summer term
      never needs a renewal (§18 Q8). Starting needs the program's application window open;
    - start refusals: "This scholarship isn't active, so it can't be renewed. Contact the scholarship office.",
      "Scholarships aren't renewed for the summer term.", "Your scholarship is already renewed for {term}.", "Your
      renewal wasn't approved for {term}. Contact the scholarship office.", "You already have an application for
      {program} this term. Finish or withdraw it first.", or the window sentence; an open renewal is returned;
    - submit evaluates the renewal rules (§8) on the current education record and freezes it, as for new
      applications; the tier is the in-force row with the award's tier code ("Your allowance tier is no longer
      offered. Contact the scholarship office.");
    - approval needs the award `active` ("This award is on hold. Reinstate it before approving the renewal." / "This
      award has ended, so the renewal can't be approved.") and no term record for the term ("This scholar already has
      a record for {term}."); it creates the next `ScholarTerm` and sets the award's tier to the chosen one, but
      only when the renewal's term sorts after every term the award already has a record for: approving an older
      term's renewal late never moves the award back to an older tier (rev 23);
    - **holding** includes a `suspended` award: starts, approval and the match page treat an award on hold as held;
    - **tiers are matched by code:** approval falls back from the requested row to the in-force row with the same
      code, so a re-price never makes staff re-pick (new applications too).
- **`Document`:**
  - fields: `requirement` FK `RequiredDocument`; `application` FK; `status` ∈ {pending, approved, declined};
    `decline_reason`; `reviewed_by`; `reviewed_at`;
  - renewal documents live on the renewal application; `Document` has no `scholar_term` (M9);
  - constraint: unique (`requirement`, `application`);
  - transitions: `pending` → `approved` or `declined`; `declined` → `pending` (re-upload);
  - rules:
    - documents change only while the application is `draft` or `returned`;
    - staff decide a document only while the application is `under_review`. A decline needs a reason of at most 500
      characters, an approved document stays approved, and a declined one reaches the student through the return;
    - an `approved` document can't be replaced, and re-uploading a `declined` one moves it back to `pending`;
    - the service checks the requirement's own `accepted_types` and `max_bytes`, because the upload field applies only
      the purpose-wide limit;
    - a `StoredFile` backs at most one `DocumentFile`;
    - students download their own files through `/files/<id>/`; staff access is in §7.
- **`DocumentFile`:** `document`, `file` FK `StoredFile`, `version`, `is_current`. A document holds one or more files,
  and re-uploads add a version.

### 4.6 awards
- **`Award`** (a scholar in a program):
  - fields: `profile`, `program`, `tier`, `student_number`, `status` ∈ {active, suspended, inactive, graduated},
    `source` ∈ {applied, imported, manual}, `source_application` (nullable one-to-one), `started_term`, `ended_term`,
    `notes`, `status_reason` (the latest hold or end reason; free text, kept out of audit `data`);
  - transitions: `active` → `suspended`, `inactive` or `graduated`; `suspended` → `active`, `inactive` or `graduated`;
    `inactive` → `active`; `graduated` is final. Labels: "Put on hold", "Reinstate", "End award", "Mark graduated";
    hold and end need a reason (at most 1,000 characters); ending or graduating sets `ended_term` to the current
    term and reinstating clears it; reinstating catches `awards_one_active_per_program`;
  - constraint: at most one active award per (`profile`, `program`). Since rev 33 a student holds one scholarship
    at a time across programs, checked by the services (§4.5); the review screen names the other program's award
    when there is one, and Approve is refused.
- **`ScholarTerm`:**
  - fields: `award`, `term`, `year_level`, `course`, `school`, `gwa`, `gwa_scale`, `units`, `merit` (bool),
    `merit_confirmed_by`, `compliance` ∈ {incomplete, complete}, `tier` (FK `BenefitTier`, the tier the term is paid
    at; backfilled from the award);
  - the school fallback matches `Application`: `school` (nullable FK), `school_name` and `school_type`, with exactly
    one source set;
  - constraint: unique (`award`, `term`);
  - `merit` is proposed by the program's merit rule and confirmed by staff;
  - `compliance` is `complete` on approval (every document was approved), or set by staff on a term record
    ("Renewal documents checked");
  - **term records (M9):** staff add or edit a `ScholarTerm` by hand (walk-ins, terms recorded outside the app): the
    term has no record and is no later than the current term; the school is required, the rest optional; merit is
    proposed by the merit rule; a graduated award takes no new record;
  - **merit confirmation:** shown as Proposed, Confirmed or No; "Confirm merit" and "No merit" set `merit` and
    `merit_confirmed_by`. M10 pays the merit amount only on confirmed merit.
- **Lifecycle:**
  - An approved new application creates an `Award` (`source=applied`, `status=active`, the tier staff chose,
    `started_term` = the application's term, `source_application`) and the first `ScholarTerm`.
    - The `ScholarTerm` copies the frozen academics from the application.
    - `merit` is `True` only when the snapshot's `merit_likely` is `True`; `merit_confirmed_by` stays empty until M9
      confirms it.
    - `compliance` is `complete`, because every document was approved.
    - An optional approval note goes in `decision_reason`.
  - An approved renewal application creates the next `ScholarTerm`.
  - Import or manual creation makes an `Award` + `ScholarTerm` with `source=imported` or `source=manual` (M9b):
    - **who:** staff pick from, and imports match only within, the program's own students: profiles created for the
      program, holding an award in it, or with a submitted application to it. Imports never search every student
      (the email lookup of rev 33 is only for on-behalf applications);
    - **one import row = one scholar:** an award starting in the row's term (blank = the current term; the term must
      exist and be no later than the current one) plus that term's record. The tier is the row with the code in
      force for the start term, else the earliest row with that code;
    - **matching:** first name, last name (case-insensitive, whitespace collapsed) and birth date. No match creates
      an unclaimed profile for the program with no invite; several matches, or a match that holds an award in the
      program, is a row error;
    - **all or nothing:** a preview checks every row with the same Form rules as manual creation; Import appears only
      when every row passes (at most 500 rows, 2 MB). The commit re-reads the file and re-validates under locks
      (program row, so imports into one program run one at a time; then the file row; then profiles in pk order);
  - **`ScholarImport`** (M9b): `program`, `file` (one-to-one `StoredFile`, so a file imports once), `imported_by`,
    `row_count`, `created_at`. `Award.import_batch` (nullable FK) links imported awards to it.
- **At-risk** is gone (rev 33, §18 Q5: the maintainer, "they don't mean anything"): no figure, scholar tab, drawer
  reasons or "Needs attention" row. Renewal rules still decide each renewal.
- **Term change and rollover (M9):**
  - the scholarship office moves the current term on `/office/terms/`: it adds the next school year (three terms, the
    seed's dates) and makes a later term current ("The current term can only move forward."); the old flag is cleared
    before the new one is set;
  - making a term current runs `awards.services.rollover(term)` for every program in the same transaction: `draft`
    and `returned` applications of earlier terms are withdrawn (`application.expired`; submitted and under-review
    rows stay for staff); `active` and `suspended` awards with at least `program.max_terms` term records of the
    first and second semesters graduate (summer records don't count, since summer never renews; rev 23; blank means
    no limit, and the seeded programs leave it blank: rev 33, §18 Q8, a scholar continues while enrolled and meeting
    the renewal rules; "final year" graduation is a manual status change);
  - `year_level` is not advanced automatically: a renewal freezes the student's own updated education record, and a
    staff term record prefills year level + 1 in a later school year;
  - it replaces v1's bulk `update_years`.

### 4.7 money
- **`DistributionSchedule`:** `program`, `term`, `distribution_date`, `claim_location`, `notes`, `frequency_label`
  (display text only, e.g. "Once a semester"), `is_published` (students only see published schedules), `created_by`.
- **`Disbursement`:**
  - fields: `scholar_term`, `schedule`, `amount` (snapshot at generation), `merit` (whether the amount paid merit),
    `status` ∈ {pending ("Prepared"), approved, rejected, released}, `approved_by`, `approved_at`, `released_at`,
    `decision_reason`;
  - constraints: unique (`scholar_term`, `schedule`); **one live payout per term (M10):** unique (`scholar_term`)
    where status is pending, approved or released. A second schedule in the same term (a make-up claim day) picks up
    only scholar terms with no live row;
  - transitions:
    - `pending` → `approved` or `rejected` (a reason, at most 1,000 characters);
    - `approved` → `released`, or back to `pending` (revert; needs reauthentication, and only before release);
    - `rejected` → `pending` (revert, needs reauthentication; refused when the term has a live payout elsewhere);
    - `released` is final.
  - **amount:** the term's tier (`ScholarTerm.tier`, else the award's tier). Merit confirmed (`merit` and
    `merit_confirmed_by` set) and `merit_amount > 0` pays `merit_amount` (the full amount with merit, not an add-on);
    otherwise `base_amount`. A proposed merit is not paid.
  - **generation** (staff) creates a pending row for every scholar term of the schedule's program and term whose award
    is `active`, whose `compliance` is `complete` and which has no live payout. It reports what it skipped and how many
    have merit to confirm. Generating again adds newly eligible rows and recalculates the amount of the schedule's
    pending rows; other rows never change, and nothing is deleted (an ineligible pending row is flagged and rejected
    by a head). One summary audit event per run.
  - **re-checks under the lock:** approve needs an active award, complete compliance and a published schedule;
    release needs an active award and `today >= distribution_date`.
  - **a schedule freezes once money moves:** with an approved or released row, its term and date are fixed and it
    stays published; with any row, its term is fixed.
  - **batch:** selected rows (at most 100) or "all prepared" / "all approved" (at most 500 per click), each row in its
    own savepoint; refused rows are reported.
- **`Budget`:** `program`, `fiscal_year` (City fiscal year, January–December), `amount`, `updated_by`.
  - a disbursement counts in the year of its schedule's `distribution_date`;
  - spent = released disbursements in that year;
  - committed = approved but not released;
  - remaining = amount − spent − committed;
  - utilization = (spent + committed) / amount ("—" with no budget or a zero budget);
  - over budget is shown ("Over budget by ₱{n}"), never blocked (§18 Q9).
- **Student view** (`/me/scholarships/`, published schedules and the student's own awards only): times claimed
  (released rows), total received, still to come this school year (pending + approved rows of the current school
  year's terms), the next published distribution of the program (date ≥ today, for a term the award has a record in),
  and each payout's status: "Being prepared", "Ready to claim", "Received {date}", or "Not paid" with the reason.

### 4.8 reports, workspace, core
- **`Report`** (M11c): a program's periodic report to the scholarship office.
  - fields: `program`, `title` (1–200), `period_start`, `period_end` (≥ start: "The period must end on or after its
    start."), `description` (≤ 2,000, optional), `status` ∈ {with_head, approved, submitted, accepted, returned},
    `submitted_by`, `submitted_at`, `head_reviewed_by`, `head_reviewed_at` (rev 33), `sent_by`, `sent_at` (rev 33),
    `reviewed_by`, `reviewed_at`, `review_note` (≤ 1,000), `created_at`;
  - reports come from programs: only program staff and heads submit or resubmit; the services refuse the office, and
    the report pages hide "Send a report" from it (rev 23);
  - **the head reviews first (rev 33, §18 Q7):** a staff member's report starts `with_head` ("Waiting for the head");
    a head of the program approves it (`approved`, "Approved, not sent yet") or returns it with a note; an approved
    report shows the head "Send to the scholarship office", which makes it `submitted` ("Waiting for the office") and
    sets `sent_by`/`sent_at`. A head's own report is sent to the office at once. A program with no active head keeps
    staff reports waiting, and the report page says "This program has no head yet. Ask the scholarship office to add
    one.";
  - transitions: `with_head` → `approved` or `returned` (a head of the program); `approved` → `submitted` (a head);
    `submitted` → `accepted` or `returned` (office only); `returned` → `with_head` (a staff member resubmits) or
    `submitted` (a head resubmits); `submitted_by` becomes the resubmitter. `reviewed_by`, `reviewed_at` and
    `review_note` hold the latest return or acceptance, by the head or the office. Accepted is final. Every
    transition locks the row; a second decision is refused with "This report was already {status label}.";
  - the office sees only reports that were sent at least once (`sent_at` set); its counts and "Reports to review"
    count `submitted` only;
  - returning needs a note ("Say what the program should change."); an accept or approve note is optional;
  - audited as `report.submitted`, `report.resubmitted`, `report.head_approved`, `report.head_returned`,
    `report.sent`, `report.accepted`, `report.returned` (report id and program; never the title, description or
    note).
- **`ReportFile`** (M11c): `report` (CASCADE), `file` (one-to-one `StoredFile`, PROTECT), `created_at`. Each
  submission carries one PDF of the `report` purpose; a resubmission may add a new version, and every version stays
  downloadable, newest first. A file already attached to a report can't be attached again ("Upload the file again.").
- **`Task`** (M11): `owner`, `program` (nullable), `title`, `notes` (≤ 2,000), `due_on`, `done_at`.
  - A personal to-do of one staff member in one program. M11's screens always set `program`. Rev 27: the office has
    tasks too, with no `program` (`/office/tasks/`, the same screens and rules: owner only, audited without the
    title, Add task in the dialog); the office nav gains "Tasks" with the same due count.
  - Only the owner sees, edits, completes or deletes it; anyone else, heads and the office included, gets a 404.
    Deleting is allowed (a to-do is not a record). Every change is audited with the id and program, never the title.
  - `tasks/` has Open (overdue first, then by due date, undated last) and Done (newest first) tabs, 25 a page; the
    staff nav item "Tasks" counts open tasks due on or before today.
  - (rev 27) `tasks/` lists tasks only; "Add task" opens `tasks/new/` in the app dialog (a page of its own without
    JavaScript). `?due=YYYY-MM-DD` pre-fills the due date (the calendar day dialog's "Add task for this day", rev 33) and `?from=dashboard`
    sends Cancel and a no-JavaScript save back to the dashboard.
- **`Notification`** (M11): `recipient` (CASCADE), `kind`, `title`, `body`, `url` (site-relative), `read_at`,
  `created_at`.
  - Title, body and url come from the app, never from free text: a reason is never stored on a notification.
  - A profile with no user gets neither a notification nor an email.
  - `workspace.services.notify()` writes the row and, given an email context, the outbox row.
- **`SupportRequest`** (M11): `sender` FK User, `topic` ∈ {account, profile, application, allowance, other},
  `program` (nullable), `message` (1–2,000 characters), `status` ∈ {open, answered}, `answered_by`, `answered_at`,
  `created_at`.
  - Students only, at most 5 per student in any 24 hours ("You've sent 5 messages today. The office will reply by
    email; try again tomorrow.").
  - Messages go to the office inbox `/office/support/`; the office replies by email from its own mail client.
    (Rev 35: replies are written in the app; see `SupportReply`.)
  - Audited as `support.sent` and `support.answered` (ids, topic, program id), never the message.
  - (Rev 35) Who sees a request: the office sees every request; the staff and heads of a program see the requests
    whose `program` is that program, including requests sent before rev 35 (no cutoff). A request with no program
    is the office's alone. Moving a request to another program is a non-goal. The student form says so under the
    Program field: "Messages about a program go to that program's staff and the scholarship office." The success
    toast becomes "Message sent. You'll find the answer under Replies." and the daily-limit message "You've sent 5
    messages today. Try again tomorrow."

  - (Rev 35) "Mark as answered" stays, for a question answered some other way (a phone call, at the counter); it
    adds no reply.
- **`SupportReply`** (rev 35, M16): `request` FK SupportRequest (CASCADE, `related_name="replies"`), `author` FK User
  (PROTECT), `channel` ∈ {app, email}, `subject` (email only, 1–150 characters, one line; blank for app), `body`
  (1–4,000 characters), `template` FK ReplyTemplate (nullable, SET_NULL; the template it started from, for the
  record), `email` FK EmailOutbox (nullable, SET_NULL; for its delivery status), `created_at`, `read_at` (nullable;
  when the student first saw it).
  - A request can have many replies, oldest first. The first reply on an open request marks it answered
    (`answered_by` and `answered_at` from that reply) through the same path as "Mark as answered", so it also
    records `support.answered` and the dashboard feeds keep showing answers; later replies leave those as they were.
  - A double submit can't send twice: the service locks the request row and refuses a reply whose author, channel
    and body match one saved in the last 60 seconds ("This reply was already sent.").
  - An emailed reply that ends `failed` shows "Failed" with "Write it again", which opens the email form filled
    from that reply's subject and body; sending it is a new reply. There is no resend route.
  - "Compose email" is hidden, and the email route refuses ("This student's account is closed. Reply in the app
    instead."), when the sender's account is inactive; an in-app reply is still allowed, for the record.
  - Replies are final: no edit or delete. A wrong reply is corrected by another reply.
  - **In the app:** saved, and the student gets a `support_replied` notification (no email).
  - **By email:** saved, and an `EmailOutbox` row of kind `support_reply` goes to the sender's account email (§9),
    plus the same `support_replied` notification. The student also reads an emailed reply in the app.
  - Anyone who can see the request can reply: the office, and the program's staff and heads (§6). Replies can be
    added to an answered request too.
  - The student sees the body, "Sent by email" for an email, and the date. The author's name is shown only to staff,
    heads and the office; the student sees "The scholarship office" when the author is a super admin, otherwise the
    program's name.
  - Audited as `support.replied` (request id, reply id, channel, template id, program id), never the text.
- **`ReplyTemplate`** (rev 35, M16): `title` (1–80 characters, unique among active templates), `topic` (nullable:
  any topic; else one of `SupportRequest.Topic`), `program` (nullable: every program; else one program), `subject`
  (optional, up to 150 characters; the email subject to start from), `body` (1–4,000 characters), `is_active`,
  `created_by`, `updated_by`, `created_at`, `updated_at`.
  - Managed by the office only (`/office/support/templates/`): list, add, edit, deactivate and activate. No delete,
    so an old reply's template link stays meaningful; inactive templates are hidden from the picker. Activating a
    template whose title an active one already uses is refused ("An active template already has this title.").
  - One set serves both channels: the same template fills the in-app reply and the email.
  - The picker on a request lists active templates whose topic is the request's topic or any, and whose program is
    the request's program or every program; topic-specific first, then by title.
  - Placeholders, filled when the template is picked: `{first_name}` (the first word of the sender's
    `full_name`, or "there" when blank; never the email address) and `{program}` (the request's program name, or "the scholarship office"). Any other text in braces is
    left as written. The filled text is only a start: staff edit it freely before sending.
  - Audited as `support_template.created`, `.updated`, `.deactivated`, `.activated` (ids, changed field names).
- **`EmailOutbox`:** `to`, `kind`, `context` (JSON, whitelisted strings only; see §9), `status` ∈ {queued, sent, failed}, `attempts`,
  `last_error`, `provider_message_id`, `sent_at`.
- **`AuditEvent`:** `actor`, `action` (dotted, e.g. `application.approved`), `program` (nullable), `target_type`,
  `target_id`, `data` (JSON diff, no secrets), `ip_hash`, `at`. Append-only: no update or delete views.

## 5. URL map
| Area | URL | Who |
|---|---|---|
| Public | `/` (redirects: the sign-in page, or the user's own home when signed in), `/programs/` (M6), `/programs/<slug>/` (M6), `/about/`, `/help/`, `/privacy/`, `/terms/`, `/cookies/`, `/contact/` (the six information pages; footer disclaimer in §11) | anyone |
| Health | `/healthz` (database ping, no details) | anyone |
| Accounts | `/accounts/…` (allauth: signup, login, logout POST, email confirm, password reset, Google), `/accounts/claim/<token>/`, `/accounts/theme/` (POST, rev 29: sets the theme cookie) | anyone |
| Student | `/me/` (dashboard; rev 33: `/me/calendar/<YYYY-MM-DD>/`, the day dialog), `/me/profile/` (+ `personal/`, `family/`, `family/<id>/` + `…/delete/`, `education/`, `education/<id>/` + `…/delete/`, `photo/`) | student (own records only) |
| Student | `/me/match/`, `/me/applications/`, `/me/applications/new/<slug>/` (GET: confirm page; POST: creates the draft), `/me/applications/<id>/`, `/me/applications/<id>/documents/<requirement>/` (POST), `…/submit/` (POST), `…/withdraw/` | student (own records only) |
| Student | `/me/scholarships/` (awards, terms, renewals, payouts and the next distribution), `/me/scholarships/<award>/renew/` (POST), `/me/notifications/` (+ `<id>/`, which marks it read and redirects; `read/` POST), `/me/support/` (M11), `/me/support/replies/` (rev 35) | student |
| Staff | `/staff/<slug>/` (dashboard; rev 33: `calendar/<YYYY-MM-DD>/`, the day dialog) | program staff/head |
| Staff | `students/` (unclaimed profiles created for this program), `students/new/`, `students/<id>/invite/` | program staff/head |
| Staff | `applications/` (queue), `applications/<id>/` (review), `applications/<id>/start/`, `applications/<id>/documents/<document>/approve/`, `applications/<id>/documents/<document>/decline/`, `applications/<id>/documents/<document>/preview/` (rev 27, PNG/JPEG/PDF), `applications/<id>/decide/` (approve, return or reject), `applications/bulk/` (start review, approve; POST) | program staff/head |
| Staff | `applications/new/` (in progress + profile picker; POST starts; rev 33: `applications/new/find/` POST, the email lookup), `applications/behalf/<id>/` (filing page), `…/academics/`, `…/documents/<requirement>/`, `…/submit/`, `…/withdraw/` (POST) | program staff/head |
| Staff | `scholars/`, `scholars/<award>/`, `…/edit/`, `…/status/`, `…/terms/new/`, `…/terms/<term>/`, `…/terms/<term>/merit/` (POST); `scholars/new/`, `scholars/import/`, `scholars/import/template/`, `scholars/export/` (M9b) | program staff/head |
| Staff | `schedules/`, `schedules/new/`, `schedules/<id>/`, `schedules/<id>/publish/` (POST); `disbursements/`, `disbursements/<schedule>/`, `…/generate/` (POST), `…/bulk/` (POST), `…/<id>/reject/`, `…/<id>/revert/` (POST); `budget/`, `budget/edit/` | program staff/head (see §6) |
| Staff | `support/` (rev 35: Open and Answered tabs for this program), `support/<id>/` (the request, its replies and the reply forms), `support/<id>/reply/` (POST, in the app), `support/<id>/email/` (POST), `support/<id>/answer/` (POST) | program staff/head |
| Staff | `tasks/` (+ `new/` rev 27, `<id>/`, `<id>/done/` POST, `<id>/delete/` POST; owner only, M11), `reports/` (M11c: + `new/`, `<id>/`, `<id>/resubmit/` POST; rev 27: `<id>/files/<file>/preview/`; rev 33, head only: `<id>/approve/`, `<id>/return/`, `<id>/send/` POST), `notifications/` (M11c: + `<id>/`, `read/` POST), `audit/` (M11c), `settings/` (rules and window; `tiers/`, `tiers/new/`, `tiers/<code>/`; `documents/`, `documents/<id>/`, `documents/<id>/active/` POST; M11b) | staff; `settings/` and `audit/` are head (and office) only |
| Office | `/office/` (dashboard; rev 33: `calendar/<YYYY-MM-DD>/`, the day dialog); M11b: `programs/` (+ `new/`, `<id>/`, `<id>/active/` POST), `staff/` (+ `new/`, `<id>/`, `<id>/active/`, `<id>/welcome/`, `<id>/memberships/` POST), `memberships/<id>/` POST, `schools/` (+ `new/`, `<id>/`); `terms/` (M9: list, `add/` POST, `<term>/current/`), `support/` (+ `<id>/answer/` POST; M11; rev 35: `<id>/`, `<id>/reply/` POST, `<id>/email/` POST, `templates/` (+ `new/`, `<id>/`, `<id>/active/` POST)); M11c: `scholars/` (+ `export/`), `reports/` (+ `<id>/`, `<id>/decide/` POST), `analytics/` (+ `export/`), `audit/`, `notifications/` (+ `<id>/`, `read/` POST); rev 27: `tasks/` (+ `new/`, `<id>/`, `<id>/done/` POST, `<id>/delete/` POST; owner only), `reports/<id>/files/<file>/preview/` | super admin |
| Files | `POST /files/uploads/` (intent), `POST /files/uploads/<id>/confirm/`, `GET /files/<id>/` (authorize → 302) | owner or authorized staff |

- **The staff queue** (`applications/`, M8):
  - it lists only applications with `submitted_at` set, so drafts the student hasn't submitted stay private;
  - status filter: **Waiting** (submitted + under review; the default), then Submitted, Under review, Returned,
    Approved, Rejected, Withdrawn, and All;
  - also a term filter and a name search, where every word must match the first or last name;
  - sorts: `submitted` (`first_submitted_at`, oldest first; the default) and `name`;
  - 25 rows per page; unknown values fall back to the defaults, never an error;
  - the staff nav item "Applications" counts `submitted` applications only (the ones nobody has started);
  - the queue header has a "File for a student" button, which opens `applications/new/` (M8b).
- **Filing on behalf** (M8b):
  - `applications/new/` lists "In progress" (the program's on-behalf applications that are draft or returned), then a
    searchable list of the program's profiles with a "File an application" button (POST starts); the students list
    has the same button on each row;
  - `applications/behalf/<id>/` is the filing page. A returned on-behalf application's review screen links to it with
    "Fix and resubmit", and the filing page redirects to the review screen for any other status;
  - the review screen shows "Filed by {staff name} for the student." and lists overridden checks under "Overridden by
    staff" with the reason.
- **The scholar list** (`scholars/`, M9): tabs Active (default), Suspended, Inactive, Graduated, Not renewed
  (due this term), All (rev 33: the At risk tab is gone); a name search (every word matches first or last name) and a tier filter by code; 25 rows a
  page, unknown values fall back to the defaults; columns scholar, school, tier, GWA (latest term), terms, status;
  `?scholar=<id>` opens a drawer with the facts, renewal status and "Open record". The staff nav has
  "Scholars" after Applications; the student nav has "Scholarships".

## 6. Authorization
- **Roles:** `User.role` decides which area a user can enter. Staff powers come from `ProgramMembership`, and a super
  admin can do everything in `/office/` and act in any program.
- **Access rules:**
  - anonymous → redirect to login, with `next`;
  - signed in with the wrong role or no membership → 403;
  - unknown program slug → 404;
  - a super admin passes every program.
- **Login lands on the role's home:** student `/me/`; staff their first program (by name), or a "no programs yet"
  page; super admin `/office/`.
- **Mixins and decorators:**
  - `StudentRequiredMixin`, `ProgramStaffRequiredMixin(level=staff|head)`, `SuperAdminRequiredMixin`;
  - object access always goes through a scoped selector (e.g. `applications_for_program(program)`), never through a
    bare `Model.objects.get(pk=…)`.
- **Head vs staff split** (confirmed in rev 33, §18 Q7: heads set the budget the office gives them, and staff report
  to their head):

| Capability | Student | Staff | Head | Super admin |
|---|---|---|---|---|
| Own profile, applications, scholarships | ✓ | — | — | view |
| Review applications and documents, return/approve/reject | — | ✓ | ✓ | ✓ |
| Create applications or scholars on a student's behalf, import (M8b: applications only for profiles created for the staff member's program) | — | ✓ | ✓ | ✓ |
| Edit scholars, terms, merit confirmation | — | ✓ | ✓ | ✓ |
| Generate and approve disbursements | — | prepare | approve | ✓ |
| Release and revert disbursements (reauth) | — | — | ✓ | ✓ |
| Schedules (create/publish) | — | ✓ | ✓ | ✓ |
| Program settings: tiers, documents, rules, window, budget | — | — | ✓ | ✓ |
| Program reports (rev 33) | — | write and send to the head | review, approve, return, send to the office | accept or return |
| Programs, staff accounts, memberships, schools, terms | — | — | — | ✓ |
| Audit log | — | — | own program | all |

- **M8:** head and staff may both do everything in application review (queue, review, document
  decisions, return, approve, reject, bulk), as the table above proposes. The split stays open (§18 Q7).
- **M9:** head and staff may both do everything on scholars, as the table proposes (§18 Q7 open); moving the
  current term is office-only.
- **M9b:** head and staff may both add, import and export scholars. Like every staff screen, all of them answer 404
  for an inactive program (`ProgramStaffRequiredMixin`); `create_award` and `import_scholars` re-check it.
- **M10:** staff manage schedules and generate; heads (and the office) approve, reject, release, revert and set the
  budget; release, revert and the budget ask for the password again.
- **M11b:** the office manages programs, accounts, memberships and schools; heads and the office edit program
  settings (staff get 403 and no Settings link); settings open for an inactive program to the office only. The
  audit-log viewer screens arrive in M11c.
- **M11c:** program staff and heads send and resubmit reports; only the office accepts or returns them (rev 33: a
  staff member's report goes to a head of the program first, who approves or returns it and sends it to the office). Analytics,
  the program summary and cross-program scholars are office-only. The audit log is office (every event) and head
  (only the program's events; events with no program are office-only); staff get 403 and see no link.
- **Rev 35 (support):** the office answers every support request; program staff and heads answer their own
  program's (another program's request, or one with no program, is a 404). Head and staff have the same powers
  here. Reply templates are office-only: staff and heads get 403 and see no link, and use templates in the picker.
- **Permission-matrix test:** `tests/test_permission_matrix.py` enumerates `get_resolver()` and checks each URL name
  against an expected-access table for anonymous, student, other-student, staff, other-program staff, head and super
  admin. A new URL fails the test until it's added to the table.

## 7. Files
- **Constraints:**
  - The app is stateless: no persistent local disk, and large bodies stay out of it.
  - Files therefore never pass through Django; they go straight to a private bucket on any S3-compatible service. The
    design works on every host.
- **Upload flow:**
  1. **Intent:** the browser calls `POST /files/uploads/` with purpose, name, declared type and size. The service checks
     the purpose's allowlist (never SVG or HTML) and its size limit. It then creates a `StoredFile(status=pending)` and
     returns a presigned PUT for `pending/<uuid>` that signs `ContentType` and `ContentLength`.
  2. **Upload:** `upload.ts` PUTs the file straight to the bucket, with a progress bar.
  3. **Confirm:** the browser calls `POST /files/uploads/<id>/confirm/`. Confirm locks the row and is idempotent.
     - The server copies `pending/<id>` to `files/<purpose>/<id>` first, because a presigned PUT stays valid for
       10 minutes and the pending object can change meanwhile.
     - It checks the copy only: a HEAD (size), a 4 KB sniff of the type with `filetype`, and a streamed sha256. On a
       mismatch the file is `rejected`, with `rejected_reason`.
     - It then deletes the pending object, and the file becomes `ready`.
     - Photos are read once (the whole object), checked, EXIF-transposed, re-encoded without metadata and capped at
       40 megapixels.
  4. **Housekeeping:** a 1-day lifecycle rule on `pending/` deletes abandoned uploads.
- **Purposes:**

  | Purpose    | Types          | Largest | Who                   |
  |------------|----------------|---------|-----------------------|
  | `document` | PDF, JPEG, PNG | 10 MB   | any role              |
  | `photo`    | JPEG, PNG      | 5 MB    | any role              |
  | `report`   | PDF            | 20 MB   | staff and office only |
  | `import`   | CSV, XLSX      | 2 MB    | staff and office only |

  `import` (M9b) accepts `text/csv`, `application/vnd.ms-excel` (what Windows browsers with Excel declare for `.csv`)
  and XLSX; `upload.ts` declares the type from the extension when the browser gives none. Confirm sniffs XLSX; CSV
  must have no known signature and no NUL byte in its first 4 KB. Import files are never downloadable. An XLSX file is
  refused before it is read when its archive holds more than 100 entries or unpacks to more than 10 MB (M12, ASVS
  V5.1.1, V5.2.3).

  A student may start at most 20 uploads per hour. Staff may start 100 (`STAFF_STARTS_PER_HOUR`), since five documents
  for each of five walk-ins would otherwise hit the limit (M8b).
- **Download:** `GET /files/<id>/` checks access, writes an `AuditEvent` (`file.viewed`), and 302s to a presigned GET
  valid for 5 minutes with `ResponseContentDisposition=attachment; filename=…` and the sniffed `ResponseContentType`.
  Files are never served inline from the app origin.
  - In M5 the uploader and the super admin may download. Later milestones widen access in the selector. No access
    answers 404.
  - From M8, active staff of an application's program can download every version of every document on a submitted
    application, and so can the office. Anyone else gets 404.
  - From M8b, active staff of the program can also download every version of an on-behalf application's
    documents before it is submitted, and a student can download the files of their own applications, including files
    staff uploaded for them.
  - The redirect carries `Cache-Control: no-store`.
  - Names are cleaned (no path parts or control characters, at most 255 characters) and sent as an ASCII fallback plus
    RFC 6266 `filename*`. The extension follows the sniffed type.
- **Errors:** storage not configured or unavailable answers 503 with a sentence; anonymous POSTs answer 401 JSON.
- **Exports (M9b):** a program's scholar list (at most a few thousand rows) is built in the request and sent as an
  attachment with `Cache-Control: no-store`. Birth dates are left out; string cells starting with `=`, `+`, `-`, `@`,
  a tab or a carriage return get a leading `'`; the audit event records format, tab, tier and row count, never the
  name search.
- **Exports (M11c):** the office's program summary (`/office/analytics/export/`) and cross-program scholar list
  (`/office/scholars/export/`) follow M9b: built in the request, sent as an attachment with `Cache-Control:
  no-store`, nothing stored. `StoredFile.Purpose.EXPORT` stays unused.
- **Report files (M11c):** active staff of the report's program (the `staff_can_download` rule) and the office may
  download every version, even after the uploader leaves; anyone else gets 404. The `file.viewed` event names the
  report's program.
- **Malware scanning (M13, optional):** with `CLAMAV_HOST` (and `CLAMAV_PORT`, default 3310), confirm streams the
  copied object to clamd (`INSTREAM`) before the file is ready: `FOUND` rejects it (reason `malware`, "This file can't
  be accepted. Upload a different one."); clamd unreachable answers 503 ("Files can't be checked right now. Try again
  in a few minutes.") and leaves the file pending. clamd's protocol has no TLS, so production refuses a
  `CLAMAV_HOST` on another machine like any unencrypted service (rev 22).
- **Access by purpose (M12):** `import` files are never downloadable, by anyone, the office included; `report` files
  answer the office and active staff of the report's program only (no uploader shortcut); `document` and `photo`
  files keep the rules above.
- **Retention (M12, while §18 Q10 is open):** `cleanup` deletes the storage object of every `import` file older than
  7 days, and its row unless a `ScholarImport` points at it (that row becomes `rejected`, reason `expired`). Nothing
  happens without storage; an object already gone counts as deleted; a storage error leaves the row for the next run.
  An expired file reads "Upload the file again.".
- **Bucket:** private; CORS allows PUT and GET from the app's origins only; encryption at rest is the provider's.
- **Public endpoint:** presigned URLs must point at an address the browser can reach. An optional public endpoint
  setting covers the case where the app reaches storage by an internal name (inside compose); CSP `connect-src` and
  `img-src` include the storage origin from settings.

## 8. Matching
- **Eligibility, deterministic**
  (`matching.eligibility.evaluate(profile, program, academic, *, today, term, tiers, allowed_schools)`):
  - the caller passes the term, the tiers and the allowed schools, so `evaluate` makes no queries; the allowed-schools
    rule text is built from `allowed_schools`;
  - returns `EligibilityResult(eligible, reasons: list[str], tier_candidates, merit_likely)`;
  - checks the application window, residency years, voter registration, school/type allowlist, minimum units, and GWA
    against the scale-aware threshold;
  - every rule must be met, and each check is `met`, `unmet` or `missing`; `missing` means the profile lacks the
    data, and the reason says what to add, with a link to the profile section;
  - scale rule: a GWA rule that exists for another scale but not the student's is `unmet` ("This program has no grade
    rule yet for schools that grade on a {scale} scale. Ask the scholarship office."), for example a percent-only
    program and a student graded 1-5 or on four points; only a program with no GWA rule at all passes every scale;
  - the term is `application_term(today)`: the term flagged `is_current`, else the term whose dates contain `today`,
    else `None`, which closes applying with a sentence (the M9 rollover owns the flag);
  - `tier_candidates` are every tier in force for the program in that term (LANI tier criteria are §18 Q3); the
    student requests one, and a lone tier is chosen for them; a program with no tiers can't be submitted to;
    `merit_likely` is `None` unless the program has a merit threshold for the student's scale;
  - every failed check adds a human-readable reason;
  - this is the only thing that gates applying. Submitting also needs the "Personal details" completion section done
    (§16 M7).
- **Renewal rules (M9)** (`matching.eligibility.evaluate_renewal`, pure): the window; a current school; the renewal
  GWA, scale-aware (`renewal_min_gwa_percent` or `renewal_max_gwa_one_to_five`; a scale with no renewal rule is
  `unmet`; no renewal GWA rule at all means no check); `renewal_min_units`; and, when `renewal_no_failing_grades` is
  on, the student's declaration "I have no failing, incomplete or dropped subjects this term." Residency, voter and
  school allowlists are not re-checked. Every rule must be met to submit; no tier candidates.
- **Model hint, advisory** (`matching.legacy_model.suggest(...)`):
  - It is a pure-Python port of v1's pickle. `scripts/export_legacy_model.py`, run once in a throwaway sklearn 1.6.1
    environment, exports the scaler means/scales, one-hot categories, coefficients, intercepts and classes to
    `apps/matching/data/legacy_tier_model.json`. Inference is the same transform followed by a softmax.
  - **Inputs:**
    - `grade = round(clamp(1 + (gwa_percent − 70) × 0.1, 1, 4), 2)` (as v1); only shown when a percent GWA exists;
    - `income`, now actually collected: the monthly household income in pesos as typed; v1's units are undocumented,
      so the page says it is advisory and that the model's income units are unknown (rev 26: a "Hint:" note above
      the program cards);
    - the school name, matched exactly (v1's one-hot encoder is case-sensitive);
    - school type public/private, with SUC and LCU mapped to public.
  - **Missing inputs:** the hint appears only with a percent current GWA, a household income, and a known school name
    and type. Otherwise it says why: "The legacy model only reads percent grades." / "Add your household income to
    see it."
  - **Output:** a suggested program plus merit (`CEAA_Merit`, …, `NotEligible`) and a probability. It never suggests a
    LANI tier.
  - **Parity test:** about 30 fixture vectors, including unknown schools and edge grades, generated by the export
    script with sklearn's own `predict_proba`. The port must match within 1e-9.
- **Match page:** `/me/match/` lists every active program with ✓/✗, the reasons, the tier candidates, and the hint
  ("Suggested by the legacy model; advisory"). The student applies only to eligible programs and requests a tier; staff
  confirm the tier on approval. The result is saved in `Application.match_snapshot` at submit time.
  - A card's action, in order: "Continue your application" when an open application exists; else "You already hold
    this scholarship." when the profile holds it (an approved application this term or an active award); else "This
    application wasn't approved for {term}. You can apply again next term." when it was rejected this term (§4.5);
    else "Apply" when eligible. The held and rejected flags come from `Exists` annotations on the page's one program
    query, so they add no queries.

## 9. Email, notifications, background jobs
- **Sending email:**
  - `workspace.services.notify(user, kind, …)` creates a `Notification` and, when emailed, an `EmailOutbox` row.
  - `transaction.on_commit` tries the send through the configured SMTP transport with a 5-second timeout. On failure the row is
    `failed`, with `last_error` set.
  - Inside a web request the commit only queues the row id (a per-request `ContextVar`); a `request_finished` receiver
    sends it after the response, so SMTP never delays a page or times a password reset. Outside a request (commands,
    the worker, the demo loader) it sends on commit.
  - Batch actions (bulk approvals, disbursements) send one batched call over the same transport.
  - allauth emails go through the outbox too. A row stores `kind` (the allauth template name, e.g.
    `email_confirmation_signup`) and only whitelisted string values in `context`; `context` is emptied once the row is
    `sent` or reaches 5 attempts.
  - Sending locks the row (`select_for_update(skip_locked=True)`) so it goes out once. The message's `Message-ID` is
    stored as `provider_message_id`.
- **Notifications (M11):** each of the five student emails is also a notification, through `notify()`:

  | Kind | Title | Body | Url |
  |---|---|---|---|
  | `application_received` | "We received your {program} application" | "We'll email you when it's reviewed." | the application |
  | `application_returned` | "{program} returned your application" | "Open it to see what to fix." | the application |
  | `application_decided` (approved) | "Your {program} application was approved" | "" | the application |
  | `application_decided` (not approved) | "Your {program} application was not approved" | "Open it to see the reason." | the application |
  | `allowance_approved` | "Your {program} allowance is ready to claim" | "{amount} for {term}. Claim it on {claim date} at {location}." | `/me/scholarships/` |
  | `allowance_released` | "Your {program} allowance was released" | "{amount} for {term}." | `/me/scholarships/` |
  | `support_replied` (rev 35; never emailed itself) | "The scholarship office answered your message" or "{program} answered your message" | "" | `/me/support/replies/` |

  A student's support message is never emailed (free text). Rev 35: a staff reply sent "by email" is, on purpose
  (`support_reply` below); an in-app reply is only a notification. Notifications are a record of what was said: reverting a payout
  leaves its "ready to claim" notice in place, and the scholarship page shows the payout's current status (rev 23).
- **Staff and office notifications (M11c):** in the app only, never emailed. Centres at `/staff/<slug>/notifications/`
  (all of the user's notifications; the program only picks the layout) and `/office/notifications/`; the bell shows on
  every staff and office page.

  | Kind | To | Title | Body | Url |
  |---|---|---|---|---|
  | `report_submitted` | every active office account | "{program} sent a report for review" | "{period}." | the office report |
  | `report_submitted` (resubmit) | every active office account | "{program} sent a returned report back" | "{period}." | the office report |
  | `report_accepted` | `submitted_by` | "The office accepted your {program} report" | "" | the staff report |
  | `report_returned` | `submitted_by` | "The office returned your {program} report" | "Open it to see what to change." | the staff report |

  | `report_for_head` (rev 33) | every active head of the program | "A {program} report is waiting for your review" | "{period}." | the staff report |
  | `report_head_approved` (rev 33) | `submitted_by` | "The head approved your {program} report" | "" | the staff report |
  | `report_head_returned` (rev 33) | `submitted_by` | "The head returned your {program} report" | "Open it to see what to change." | the staff report |

  `{period}` reads "1 August 2026 to 31 October 2026". The report title and the reviewer's note are free text and
  never go into a notification. The office's accept or return also tells `sent_by` when that head isn't the author.
- **Templates:** `templates/emails/<kind>.{html,txt}`, autoescaped.
  - v1 messages to port: application received, application decided, allowance approved/released, password reset (from
    allauth).
  - New: invite/claim, application returned.
  - **On-behalf applications (M8b):** emails go only to `profile.user.email`, and only when the profile
    has a user. `application_received` goes out on submit and resubmit, and `application_decided` on approve or reject
    (unchanged). There is no `application_returned` for an on-behalf application, because staff fix it, not the
    student.
  - M7 sends only `application_received`, on submit and on resubmit. Its context whitelist is `full_name`,
    `program_name` and `application_url` (a name is allowed because the address is verified).
  - M8 adds:
    - `application_returned`, whose whitelist is `full_name`, `program_name` and `application_url`;
    - `application_decided`, the same keys plus `outcome` ∈ {`approved`, `not approved`}.
  - M10 adds `allowance_approved` (`full_name`, `program_name`, `term_label`, `amount`, `claim_date`,
    `claim_location`, `scholarships_url`) and `allowance_released` (`full_name`, `program_name`, `term_label`,
    `amount`, `scholarships_url`). None on generate, reject or revert.
  - M11b adds `staff_welcome` ("Your ScholarSync account is ready"; `full_name`, `role_label`, `set_password_url`),
    sent when the office creates an account and again on request until the first sign-in.
  - Rev 35 adds `support_reply`: the subject is the staff-written subject; the body is the staff-written text
    (autoescaped, line breaks kept) under "Hi {full_name}," with the footer "This address doesn't take replies. To
    ask something else, sign in and open Help and guides." and a link to `/me/support/replies/`. Whitelist:
    `full_name`, `subject`, `body`, `replies_url`. It goes to the sender's account email (verified), from
    `DEFAULT_FROM_EMAIL`, with no Reply-To. Like every outbox row, the context (and so the text) is emptied once the
    row is sent or gives up; the text stays in `SupportReply.body`. The staff member's name is not in the email.
  - The staff reason is never in the email (free text; the student reads it signed in). A profile with no user gets no
    email.
  - There is no separate "document declined" email: the student can't re-upload until the application is returned, so
    the return covers it.
- **Background jobs:** two management commands, run on a loop by the `worker` service (or from any cron or scheduler):
  - `send_outbox` retries `failed` rows, up to 5 attempts, and also picks up `queued` rows older than 5 minutes;
  - `cleanup` runs `clearsessions`, deletes expired invites, and purges `sent` outbox rows and exhausted `failed` rows
    (5 attempts) older than 90 days.
- **Scope:** both commands are idempotent. There are no HTTP cron endpoints and no `CRON_SECRET`.

## 10. Security and privacy
- **Authentication:**
  - allauth with email as the login and `ACCOUNT_EMAIL_VERIFICATION="mandatory"`;
  - Google OIDC links to the account only when the Google email is verified;
  - Google sign-in is for students only: staff and office accounts sign in with their password, and the social
    adapter's `pre_social_login` refuses both a Google login and a Google connect that would reach one;
  - emails greet the user by name only when the address they go to is verified (anyone can type a name and someone
    else's address into the signup form);
  - `ACCOUNT_SIGNUP_REDIRECT_URL` sends a new student to `/me/` after email confirmation;
  - allauth rate limits (Django database cache, via `createcachetable`);
  - reauthentication before revert/release, membership and role changes, and program money settings (M11b: tier
    changes, account creation and (de)activation, membership add, change and removal);
  - Argon2 first in `PASSWORD_HASHERS`; validators: minimum length 10, common, numeric, similarity;
  - Google signup shows the signup form (no auto signup), so the consent box is always ticked by a person;
  - unknown-account emails are off;
  - tests use the local-memory cache; deployments use the database cache.
- **Sessions:**
  - database-backed; `Secure`, `HttpOnly`, `SameSite=Lax`; 12-hour age;
  - `ACCOUNT_SESSION_REMEMBER = True`, so there is no "remember me" checkbox;
  - logout is POST only and lands on the sign-in page.
- **CSRF and redirects:**
  - Django CSRF on every form; HTMX sends `X-CSRFToken` through `hx-headers` on `<body>`;
  - redirects are validated with `url_has_allowed_host_and_scheme`.
- **Headers:**
  - HSTS: 1 year, includeSubDomains; preload after launch;
  - `nosniff`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin`, a strict `Permissions-Policy`;
  - `Cache-Control: no-store, private` on every response to a signed-in request and on the secret routes (claim,
    email confirmation, password reset), unless the view set its own (M12).
- **CSP:**
  - `default-src 'self'`; `script-src 'self'`; `style-src 'self'`;
  - `img-src 'self' data: <storage-origin>`; `connect-src 'self' <storage-origin> <sentry-ingest>`;
  - `frame-ancestors 'none'`; `form-action 'self'`;
  - enforced by default; report-only only with `VITE_DEV_MODE` (the Vite dev server serves scripts from another
    origin) or `CSP_REPORT_ONLY=true` while debugging; no `report-uri`, because browsers would post full page URLs
    and Referers straight to Sentry, past `scrub_event` (M12);
  - htmx config (a `<meta name="htmx-config">`): `allowEval: false`, `allowScriptTags: false`,
    `includeIndicatorStyles: false`, `selfRequestsOnly: true`, and `historyCacheSize: 0` so page snapshots holding
    personal data never land in `localStorage`; no `hx-on`, no inline scripts or styles.
- **Errors:** `DEBUG=False` in every deployment; custom 400/403/404/500 pages; nothing internal reaches the client.
- **Logging:**
  - JSON to stdout, with user IDs but no names, emails or document contents;
  - Sentry's `before_send` scrubs request bodies and cookies;
  - secret URLs (`/accounts/claim/<token>/`, `/accounts/confirm-email/<key>/`,
    `/accounts/password/reset/key/<uidb36>-<key>/`) read `…/[redacted]/` in log lines, the gunicorn access log
    (request line, path, query and Referer; `RedactingLogger`) and Sentry events (URL, transaction, Referer) (M12).
- **M13 additions:**
  - **Two-factor sign-in:** TOTP and recovery codes (`allauth.mfa`), required for program staff and the office when
    `MFA_REQUIRED_FOR_STAFF` (default on in production, off in developer and explore modes); a required account
    without an authenticator reaches only the 2FA, reauthentication and sign-out pages. The office can remove a staff
    account's authenticator (password asked again; `mfa.removed`). Staff and the office can't remove their own while
    it is required.
  - **2FA secrets at rest (rev 24):** TOTP secrets and recovery-code seeds are stored as `fernet:` tokens
    (`apps/accounts/mfa_secrets.py`): Fernet keys derived with HKDF-SHA256 from `DJANGO_SECRET_KEY` and each key in
    `DJANGO_SECRET_KEY_FALLBACKS`, so a rotated key keeps working while the old one is a fallback;
    `manage.py reencrypt_mfa_secrets` (audited `mfa.secrets_reencrypted`) re-encrypts every authenticator under the
    current key before the old one is dropped. Migration `accounts.0003` encrypts existing rows; rolling back past it
    first needs `migrate accounts 0002` on the new image (its reverse decrypts) — the one exception to
    expand/contract, recorded in `docs/HOSTING.md`. A lost key makes authenticators unreadable.
  - **Breached passwords:** Have I Been Pwned's k-anonymity range API (5 hex characters of the SHA-1 leave the
    server), on when `PASSWORD_BREACH_CHECK` (default on in production); 3 s timeout; fails open, logging no password
    data.
  - **Session limits:** idle 30 minutes for staff and the office, 60 for students (`SESSION_IDLE_MINUTES_STAFF`,
    `SESSION_IDLE_MINUTES_STUDENT`); 12 hours from sign-in whatever the activity; a warning dialog 2 minutes before an
    idle sign-out with "Stay signed in" (`POST /accounts/session/keep-alive/`), and 5 minutes before the absolute
    limit; the session key rotates after reauthentication, by password or by authenticator code (rev 22).
  - **Sessions:** `/accounts/sessions/` lists one's sessions with "Sign out other sessions" (`allauth.usersessions`;
    behind the password; audited `user.other_sessions_ended`); the office's "Sign out everywhere" on a staff account
    (`user.sessions_ended`); `manage.py end_sessions --email`. Each row keeps the start time, IP address and browser
    string, and goes once its session has ended (`cleanup`, and at once when sessions are ended); the privacy notice
    (version 2026-11-19) says so.
  - **Encrypted services:** production refuses an email URL without STARTTLS or TLS, `http://` storage endpoints, a
    database URL without `sslmode=require|verify-ca|verify-full` and a `CLAMAV_HOST`, except for loopback,
    single-label service names and `host.docker.internal`, or with `ALLOW_PLAINTEXT_SERVICES=true`.
  - **Least privilege:** migrations run with `DATABASE_URL_MIGRATIONS` when set, and the entrypoint unsets it (and
    `DATABASE_URL_UNPOOLED`) before the app starts; the runtime role has DML only and no `UPDATE`/`DELETE`/`TRUNCATE`
    on audit events; the app code is root-owned in the image.
  - **Request ids:** an `X-Request-ID` (kept when valid, else generated) and the user id on every log line and in
    the access log.
  - **Accepted:** name searches stay in `GET ?q=` on signed-in, `no-store` staff pages (dropped from logs).
  - **Passwords:** the all-numeric rule is dropped (common list, length, site words and the breach check cover it).
- **Audit of sign-ins (M12):** `user.signed_in` and `user.signed_out` (the user, with `ip_hash`) and
  `user.sign_in_failed` (no actor, empty data: the typed email is never stored). They appear in the audit log's
  Accounts group, not in the overview feed.
- **Robustness (M12):** double posts never answer 500. A unique clash inside a savepoint becomes the form error;
  `create_account` also refuses any user's allauth `EmailAddress`; deactivation locks every active office account
  first, so one always stays active; an upload to a switched-off requirement answers 404.
- **ASVS (M12):** `docs/security/asvs-l2.md` reviews OWASP ASVS 5.0.0 Level 1 and 2, with evidence per requirement;
  open gaps are listed there and in the project's known issues.
- **Dependencies:** `pip-audit` (on `uv export`) and `npm audit` in CI; Dependabot.
- **RA 10173 (Data Privacy Act):**
  - a privacy notice and a consent record;
  - collect only what eligibility needs;
  - program-scoped access, with an audit of every document view;
  - a private bucket;
  - a retention period (open question);
  - "download my data" and account-deletion requests, handled by the office in v2.0.
- **Staff-written email (rev 35):** a support reply by email is the only email whose body is free text. It goes
  only to the account email of the student who asked, never to a typed-in address; the subject is one line (the
  form refuses newlines, and Django refuses header newlines anyway); the body is autoescaped in the HTML part and
  its links are not made clickable. Reply text is never logged, never in audit `data` and never in a notification.

## 11. Running and hosting
Summary of `docs/design/2026-10-30-open-source-self-hosting-design.md` §4-§8, which is the detail.
- **Intent:** the repository is public (MIT). Explorers run one command and click through sample data; self-hosters use
  their own `.env` and providers. Nobody hosts an official copy.
- **One command:** `docker compose up` from the repository root. Services: `web` (gunicorn, built from the
  `Dockerfile`, Vite bundle built inside the image) on `http://localhost:8000`, `db` (Postgres 17), `storage`
  (S3-compatible), `mail` (Mailpit inbox on `http://localhost:8025`) and `worker` (§9). No `.env` is needed. First run
  migrates, creates the cache table and bucket, and loads the demo only if the database has no users. Host ports are
  overridable (`APP_PORT`, `MAIL_PORT`, `DB_PORT`, `STORAGE_PORT`). `docker compose down -v` resets.
- **Modes:**

| Mode | Selected by | Debug | HTTPS-only | Demo | Kit `/_kit/` |
|---|---|---|---|---|---|
| Developer | `DJANGO_DEBUG=true` | on | off | active | on by default |
| Explore | `SCHOLARSYNC_EXPLORE=true` (set by compose) | off | off | active | on |
| Production | neither (fail-closed default) | off | on | inactive | refused |

  - Explore mode is for the visitor's own machine: ports bind to `127.0.0.1`, and settings refuse explore mode with any
    host other than `localhost`/`127.0.0.1`.
  - Startup fails fast on a missing required variable in production mode.
- **Demo:** everything demo-only (test accounts, sample data, login-page notice) lives in `apps/demo/`. (rev 32) The
  login-page notice is a `<details>`, closed by default: its summary button reads "Exploring ScholarSync? Use a test
  account" and opens the accounts, the shared password and the fill buttons. (rev 36) The accounts are grouped
  (Students, Program staff, Scholarship office) as small buttons, each named so it reads alone ("LANI head"); the
  password is shown once; without JS the groups list each name and email instead. A listed account appears only once
  it exists with a usable password, so a load that skipped a sample (no storage, summer) shows no dead button. Every
  listed account, including the sample ones (returned applicant, scholars), signs in with the shared password.
  Deleting that
  folder removes it with no other edit; the app reaches it only through an optional hook, never by import. It is
  inactive in production mode even if present, and `check --deploy` fails while the folder exists. Programs
  (`seed_programs`) are not demo material, and the demo leaves their settings alone with one exception (rev 26):
  when LANI has no application window, the demo gives it one through the office account (from 14 days before the
  load to 30 days after), so the student home's calendar has dates to show.
- **Providers:** any PostgreSQL 17 (`DATABASE_URL`), any S3-compatible storage, any SMTP server, Google sign-in when
  keys are set, Sentry when a DSN is set.
- **Proxy settings:** `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`; hosts and CSRF origins come from
  `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`; allauth reads the client IP from the forwarded header with
  a trusted-proxy count.
- **Migrations:** expand/contract only; the entrypoint runs `migrate` against the unpooled URL when set.
- **Guides:** `README.md` (quick start, test accounts), `docs/SETUP.md` (local run, developer workflow) and
  `docs/HOSTING.md` (self-hosting checklist, M12). `compose.production.yaml` (web and worker only) is the hosting
  example.
- **Proven guide (M12):** the guide is walked through on a fresh clone with local stand-ins (PostgreSQL 17, MinIO,
  Mailpit, Caddy with `tls internal`) and the walk is recorded in `docs/hosting-walkthrough.md`. It gains a tested
  restore, a runbook (deploy, roll back, restore, rotate each secret and what that breaks) and HSTS preload guidance
  (off by default; only once every subdomain is HTTPS for good).
- **Public information pages:** `/about/`, `/privacy/` (RA 10173), `/terms/`, `/cookies/`, `/help/`, `/contact/`, linked
  from a footer on every layout with the line "Independent portfolio project. Not affiliated with or endorsed by the
  City of Taguig. All sample people and data are fictional." They are template text, not legal advice. In production,
  `SITE_OPERATOR_NAME` and `PRIVACY_CONTACT_EMAIL` are required and shown on them. `SECURITY.md` covers vulnerability
  reports.
- **History:** the M1 spike tested Vercel, Neon, R2 and Resend. Vercel is no longer a target; see §19.

## 12. Frontend
- **Design direction (rev 4, 2026-10-30):** The maintainer asked for a redesign on the layout of a Dribbble admin
  dashboard ("Cark: User management platform"), with red as the main colour, blue second and yellow third, using the
  UI UX Pro Max skill. He reviewed and edited the result on a design canvas; its boards are kept in
  `docs/design/2026-10-30-redesign/` and are the visual reference for this section. Rev 4 replaces rev 3's
  navy-led, unboxed look. The maintainer's rulings from the canvas review:
  - figures are plain number + label pairs, no icons, captions or progress bars (rev 6, 2026-11-03: the maintainer
    dropped the box; they are now one line under the page header);
  - status is bold coloured text, never a pill or tinted tag; tiers are plain text with no colour;
  - no decorative coloured circles (timeline dots, icon chips); no subtitle lines that repeat the obvious;
  - "needs attention" items are whole-row links with no underline, an arrow on the right and a hover state, and their
    detail line is coloured by severity;
  - review progress is a single progress bar, not step pills.
- **Brand:** the graduation-cap logo in a red rounded square, the "ScholarSync" wordmark (Lexend 700) and the
  "City of Taguig" label. A 4 px stripe in red (half), blue and yellow (a quarter each) tops the sidebar in the app
  shells and the page in the public and auth layouts.
- **Tokens** (`frontend/src/styles/tokens.css`; every text pair ≥ 4.5:1, checked by `tests/test_tokens.py`):
  - **red (primary)** `#b8132a`: main buttons, current nav item, brand mark, current page in pagination, current
    tab underline, budget bars; white on it 6.6:1; hover `#9b1022`; tint `#fbe7ea` (red on tint 5.6:1);
  - **blue (secondary)** `#1f4e9e`: links, program identity, info, selected rows, progress toward a goal, the
    soft secondary button; white on it 8.0:1; hover `#163a78`; tint `#e4ebf6`;
  - **yellow (accent)** `#f2b705`: fills only (focus halo, nav counts, callout tints `#fef8e1`/`#fcefc4`), never text
    on white (1.8:1); ink on yellow 9.5:1; **gold text** `#8f6500` (5.2:1 on white) for warning-tone status;
  - **neutrals:** ink `#0e1b2c`, muted `#5b6472` (6.0:1 on white), secondary text `#3d4654`, border `#e4e7ec`,
    control border `#d0d5dd`, ground `#f5f6f8`, table header `#fafafb`, hover `#f1f2f5`;
  - **status text:** success `#11663a`, warning `#8f6500`, info `#1f4e9e`, danger `#9b1022`, neutral `#3d4654`;
  - **danger** `#9b1022`, darker than the primary red; danger buttons are outlined in it, with an icon and a verb;
  - **focus:** 3 px ink outline plus a yellow halo outside it;
  - **type:** Lexend 600/700 headings, Source Sans 3 400/600/700 body at 14 px (inputs 16 px on touch screens so
    phones don't zoom), line height 1.5, tabular figures for money; captions and table headers 12 px; headings h1 23,
    h2 21, h3 19, h4 17 px (rev 6, 2026-11-03: the maintainer found rev 4 too big and asked twice for a denser design);
  - **shape:** radius 8 px (controls, buttons, nav items), 10 px (small blocks), 12 px (cards, drawer
    edges); pills (999 px) only for counts; shadows only on floating layers (drawer, dialog, menus; toasts are flat, rev 30).
  - (rev 29) **Light and dark themes.** Role tokens hold both values with `light-dark()`; the palette tokens stay
    hex. `:root` is `color-scheme: light dark`, so by default the app follows the device. The account menu offers
    Light, Dark and System (the current one marked): a plain POST to `accounts/theme/` sets a `theme` cookie (one
    year, `HttpOnly`, `SameSite=Lax`; "System" deletes it) and redirects back to a safe `next`. The server writes
    `data-theme` on `<html>` and `<meta name="color-scheme">` from the cookie, so the page paints in the chosen
    theme with no script and no flash (the CSP rules out the usual inline script). Signed-out pages follow the
    cookie too; (rev 31) the auth layout (log in, sign up, password reset) offers the same control at the top
    right of its form column (`components/theme_choice.html`, shared with the account menu); (rev 32) there it
    is three icon buttons (sun, moon, monitor) whose names stay as visually hidden text, with a matching
    `title`; the account menu keeps the words. The dark ground is a deep navy-grey, cards a step lighter; red, blue and gold
    lighten to keep 4.5:1 as text, while solid red buttons keep white text; the auth panel stays red.
    `tests/test_tokens.py` checks every pair in both themes.
- **Components** (`templates/components/` + CSS):
  - **buttons:** 36 px tall (32 px inside tables), radius 8. Primary = solid red; secondary = white with a `#d0d5dd` border; soft = blue
    tint with a blue border; ghost = no border, hover tint; danger = white, outlined in `#9b1022`. Icons only where
    they carry meaning (download, add, mail, close, menu, sign out, pause);
  - **cards:** white, 1 px border, radius 12, a title row with an optional link on the right. Page sections are
    cards on the grey ground; a card never sits inside another card;
  - **figures:** one line of Lexend number + label pairs under the page header, divided by 1 px rules, with a
    rule below; pairs wrap on narrow screens;
  - **status:** bold text in its tone colour (`.status--success` etc.), no background; **counts:** small pills (nav
    counts in yellow with ink text, tab counts grey or red tint on the current tab);
  - **avatars:** initials in a circle, tinted red, blue or yellow by position;
  - **table:** 12 px bold muted headers on `#fafafb`, 1 px row rules, row hover, numbers right-aligned in tabular
    figures; toolbar of search + filter selects above; numbered pagination with the current page in red;
  - **tabs:** bold text with a 3 px red underline on the current tab and a count pill;
  - **drawer:** a slide-over detail panel (white, left border, shadow) opened by a link, so a list keeps its place;
    server-rendered, closed by a link;
  - **progress:** 8 px rounded bar on `#eef0f3`;
  - **row links:** whole-row links for task lists (no underline; hover background, underlined title, arrow);
  - **banners:** tinted box with radius 12 and an icon for warning and danger; **feedback:** dialog, toast, empty
    state as before.
- **Layouts:**
  - **app shell (staff, office, student):** a white 208 px sidebar (stripe, brand, a context block, grouped nav with
    an icon per item and counts, an optional callout, a user card with the account menu and sign out at the bottom)
    beside a column with a white top bar (search for staff and office, term chooser, notifications) and the page on
    the grey ground, at most 72rem wide and centred in that column (rev 6). The context block is the program switcher for staff and "Scholarship office" for the office.
    (rev 29) The account menu, program switcher and term chooser are a `<button popovertarget>` followed by a
    `popover="auto"` list of links (navigation, not an ARIA menu): the browser closes them on an outside click or
    Esc and returns focus, with no script. They sit against their button with CSS anchor positioning; where that
    is missing, `menus.ts` places them on open (without script they open centred).
    The current nav item has a red tint and red text;
  - **public:** a white top bar with the brand and text navigation, the stripe on top, content max 72rem;
  - **auth:** the split panel, now flat red with white text (a design choice; not on the canvas), the stripe on top;
  - navigation collapses behind a toggle (`nav.ts`) below 64rem and is fully visible without JS.
- **Icons:** `scripts/sprite.mjs` builds `static/dist/icons.svg` from the Lucide names listed in `src/icons/icons.json`
  plus our own SVGs (the logo); templates use `{% icon "name" %}`. A misspelt name fails the build.
- **Design kit:** `/_kit/` (every component in every state) and `/_kit/mockups/` (key screens with Faker sample data)
  live in `apps/kit`. They answer 404 unless `DJANGO_KIT` is on (default: `DJANGO_DEBUG`), settings refuse to load
  with the kit on in production mode, and kit responses carry `X-Robots-Tag: noindex`.
- **HTMX patterns:**
  - filters use `hx-get` + `hx-push-url` and swap a `{% partialdef table %}`;
  - forms use `hx-post`: re-render the form partial on error, `HX-Redirect` or `HX-Trigger` on success;
  - dialogs load content into `<dialog>`, and `dialog.ts` opens them; (rev 28) a modal dialog fades and scales in
    (no exit animation: the shared dialog empties on close), contains scrolling so the page beneath stays put, and
    only a read-only fragment (`data-light-dismiss`, the file previews) also closes on a click outside it
    (`closedby="any"`, with a click fallback where unsupported); form dialogs never do, so a stray click can't
    discard typing;
  - (rev 29) pages cross-fade on same-origin navigation (`@view-transition`, off for reduced motion;
    `<link rel="expect" href="#main" blocking="render">` so the fade never lands on a half-parsed page); the
    sidebar and top bar hold still (their own `view-transition-name`); browsers without it navigate as before;
  - (rev 28) textareas grow with their text (`field-sizing: content`, 3 to about 12 lines) where supported; paragraphs
    and list items use `text-wrap: pretty`, headings keep `balance`;
  - toasts come from `HX-Trigger: {"toast": …}`, read by `toast.ts` into an `aria-live` region; (rev 27) they sit
    at the top right under the top bar, compact; success and info hide after 3 s (paused while hovered or
    focused), warnings and errors stay until dismissed; a small action such as copy gets no toast, only a brief
    "Copied" bubble at the pointer; (rev 30) a toast is a flat solid chip with no shadow or stripe, like that
    bubble: success and info are ink with light text (inverted in dark), a warning is the civic yellow with ink
    text, an error is the solid danger red; an icon leads each (check, info, triangle, circle alert), so the tone
    is never colour alone;
  - bulk actions are a form with checkboxes;
  - every form also works as a normal POST without JS.
- **Dashboards (M11):**
  - **student** (`/me/`, the approved mockup, reworked in rev 26): returned banners (not on-behalf), one award card
    per active or suspended award ("To renew:" from the program's renewal rules); then a calendar beside a narrow
    column with the profile ring and the next dates; then the 5 newest applications, the 3 newest payouts with M10's
    student labels, the 3 newest notifications; the bell shows the unread count on every student page;
    - **profile ring:** an SVG circle (`pathLength="100"`, the dash set by attributes, never an inline style, for the
      CSP) with the percent in its middle, "Next: {section}" and the profile link; the percent is also text;
    - **calendar:** one month (`?month=YYYY-MM`, anything invalid falls back to the current month; Previous/Next
      swap only the calendar with HTMX and work as plain links), Monday first, today marked, each date with events
      marked by a dot **and** a visually hidden label, the day's events listed under the grid's day number on wide
      screens; events are (a) **release days**: published distribution schedules of programs where the student holds
      an active or suspended award, in terms the student is a scholar in (as the award card's "Next release";
      "{program} allowance release", the claim place) and (b) **application windows**:
      `applications_open_on` / `applications_close_on` of active programs the student qualifies for on Find
      scholarships or has an unfinished application in ("{program} applications open/close"); nothing else
      (no term dates, no deadlines staff haven't entered);
    - **next dates:** the next 5 events from today, as a list (also the calendar's text alternative on phones);
    - **day dialog (rev 33, every calendar: student, staff, office):** each day of the grid, in the month or not, is
      clickable (the whole cell; links inside a cell keep their own target) and opens the app dialog with that day:
      the date as the heading ("Saturday, 21 November 2026"), then every event in full, one row each, with its kind
      (the legend's words and colour), its whole title, its detail (the claim place, the program) and its link ("Open
      task") when it has one; an empty day says "Nothing on this day.". Staff and office dialogs end with "Add task
      for this day", which loads the Add task form into the same dialog. The day is a GET page of its own
      (`…/calendar/<YYYY-MM-DD>/`, a full page without JavaScript, the dialog body with HTMX) built from the same
      event selectors as the grid, so the two never disagree; a cell's accessible name is the date and its number
      of items ("21 November 2026, 2 items");
  - **student profile** (`/me/profile/`, rev 26): read-only. One card per section (personal details, family,
    education, photo) shows what is on file as a description list (family members and education records as rows,
    the photo as a thumbnail), "Not given" for an empty field, and a "Missing" note naming what is still needed;
    each card's Edit button opens that section's existing form, which returns to the overview on save;
  - **find scholarships** (`/me/match/`, rev 26): the model hint, when there is one, comes first as a compact note
    (one line plus the advisory sentence), above the program cards;
  - **account pages** (rev 26): the session list (`/accounts/sessions/`), the two-factor pages (`/accounts/2fa/…`:
    overview, set up the authenticator app, turn it off, recovery codes) render in the user's own app shell
    (student, staff with their first program, or office) with project wording; the other allauth "manage" pages
    (email addresses, password change) use the same shell with allauth's own form markup; the
    sign-in, two-factor-at-sign-in and reauthentication pages keep the sign-in layout. The two-factor overview has
    one card per method with its state ("On" / "Off"), what it does, and its action; setting up the app is three
    numbered steps (install an app, scan the code or type the key, enter the 6-digit code). The session list shows
    every live session of the user from the session table: the ones allauth recorded with their browser and
    address, and any other as "Another browser (details not recorded)", so the count and "Sign out other sessions"
    never miss one;
  - **staff** (`/staff/<slug>/`, kit figures and attention rows): "Active scholars", "Applications waiting",
    "Released this year" (rev 33: "At risk" is gone); "Needs attention" (waiting over 7 days from `submitted_at`, own
    overdue tasks, prepared payouts, approved payouts, the window; rev 33, heads only: reports waiting for their
    review and approved reports not sent yet); "Your tasks" (the 5 next open tasks and "Add task").
    Rev 27: "Applications by month" is gone; a month calendar (the student calendar's grid, navigation and
    accessibility rules) fills the wide column and "Needs attention" sits beside it. Its events are the user's own
    open tasks with a due date (links to the task), the program's distribution days (published or not; "Allowance
    release", the claim place) and its `applications_open_on` / `applications_close_on`. Rev 33: a day opens the
    day dialog (below), which has "Add task for this day";
  - **office** (`/office/`, the approved mockup; rev 27: "Applications by month" gives way to a month calendar
    with "Needs attention" beside it, as on the staff dashboard. Its events are the user's own open office tasks
    with a due date, every active program's distribution days ("{program} allowance release", drafts marked) and
    application windows; a day opens the day dialog with "Add task for this day" (rev 33); the 12-month chart stays on Analytics): figures Scholars, Applications, Waiting over 7 days and Reports
    to review (M11c; support stays in "Needs attention" and the nav count); needs attention: "{n} program report(s)
    is/are waiting for your review" ("Oldest sent {n} days ago" or "Sent today"), per program waiting over 7 days and
    budget used ≥ 75 %, and open support requests; recent activity from audit events in `FEED_ACTIONS` with a
    sentence, where a student actor reads "A student"; "Download report" downloads the program summary for the
    current school year as XLSX (M11c).
- **Support (rev 35, M16):**
  - **Inboxes** (`/office/support/`, `/staff/<slug>/support/`): tabs Open (count) and Answered; 25 a page. Each card
    shows the sender, the account email with the copy button (the `mailto:` link goes), topic, program, date and
    message, then "Reply", "Compose email" and, while open, "Mark as answered". Answered cards add "Answered by
    {name} · {date}" and the number of replies. The staff nav gets "Support" with the program's open count, after
    Reports; the staff dashboard's "Needs attention" gets "{n} support request(s) waiting".
  - **The request page** (`…/support/<id>/`): the message, then every reply oldest first ("{author} · In the app" or
    "By email" · date; an email also shows Queued, Sent or Failed), then the two forms. "Reply" and "Compose email"
    on a card open the request page at the matching form (`#reply`, `#email`); with JavaScript they open in the app
    dialog instead, and the page works without it.
  - **The forms:** a template picker, then for email "To" (read-only: the sender's account email) and "Subject"
    (prefilled "Re: your message about {topic}", or the template's subject), then "Message". Picking a template
    fills the fields: with JavaScript at once (text already typed is replaced only after a confirm); without it,
    a "Use template" button reloads the form filled, always replacing the message, and says so in its hint
    ("Replaces what you've typed"). Buttons "Send reply" and "Send email"; toasts
    "Reply sent." and "Email queued to {email}."
  - **Templates** (`/office/support/templates/`): a table (title, topic, program, status) with Add, Edit and
    Activate/Deactivate; the office inbox header links to it ("Reply templates").
  - **Student:** `/me/support/` gets tabs "Contact the office" and "Replies" (unread count); under "Your messages"
    each message shows how many replies it has, with a link. `/me/support/replies/` lists every reply newest first,
    each under its question (topic, program, the question's first 200 characters), with "From {The scholarship
    office or program}", "Sent by email" when emailed, and the date. Unread replies are marked "New"; opening the
    page marks them read. 25 a page. The student nav's "Help and guides" shows the unread count.
- **Analytics** (`/office/analytics/`, M11c): filters school year (default the current term's) and program; new
  applications only (`kind=new`, ever submitted, term in the school year). Figures: Applications, Approved, Success
  rate = approved ÷ (approved + rejected) (whole percent), Median days to approve (`decided_at −
  first_submitted_at`, one decimal); "—" with no data. "Applications by month" (12 months, every kind, CSS bars +
  "View as table"); a by-program table; top 10 listed schools by approved then applications then name, and a note
  for applications naming an unlisted school. The program summary download has the by-program columns plus active
  scholars and the amount released for the school year's terms.
- **Audit log** (`/office/audit/`, `/staff/<slug>/audit/`, M11c): filters action group, from/to (Manila dates), who
  (an account id) and, for the office, program; 50 a page, newest first; columns When, Who (a student reads "A
  student"), What (sentence + action code), Program, Record, Details (`data`); `ip_hash` never shown.
- **Staff review screens (M8):**
  - the queue (§5) is a filter toolbar over a table with a checkbox column; the bulk form wraps the table, and the
    count above it is a live region outside the swapped partial;
  - the review screen follows the approved mockup (`kit/mockups/application_review.html`), with these changes:
    - **removed:** the tabs, because every section fits on one page; the "review checks" bar, which becomes "{n} of
      {m} documents approved";
    - **corrected:** income is "a month", because the field is `monthly_household_income`;
    - **header:** a pager shows "{n} of {m} waiting" with previous and next links, over the Waiting set in queue
      order;
    - **eligibility card:** the frozen snapshot, "As checked on {date}", plus the advisory hint;
    - **decision card**, by status: submitted shows "Start review"; under review shows the decision form; otherwise
      a decision summary. On a resubmission (submitted or under review with an earlier reason) a warning banner
      above it reads "Returned earlier: {decision_reason}", autoescaped, so the reviewer sees what was asked.
    - **image preview** (rev 27): a document file whose sniffed type is PNG or JPEG has a "Preview" link beside its
      download link. It opens the picture in the app dialog (a page of its own without JavaScript); the `<img>`
      loads through `files:download`, so access checks, the `file.viewed` audit and the presigned attachment GET
      are unchanged (browsers ignore `Content-Disposition` for images). Nothing loads until Preview is opened, so
      a page view writes no audit rows. A PDF document also has "Preview": the view audits `file.viewed` and hands
      the page a presigned GET (still `attachment`), and `pdf-preview.ts` (a lazy chunk with `pdfjs-dist` and its
      worker, both from `'self'`, so the CSP is unchanged; the bucket's CORS already allows `GET`) fetches the bytes
      and draws the first 20 pages on canvases (`role="img"`, "Page n of m"). Without JavaScript the dialog page
      says to download the file. The PDF is never served inline.
    - **report files** (rev 27): each file version on a report page (staff `reports/<id>/files/<file>/preview/`,
      office `/office/reports/<id>/files/<file>/preview/`) has the same "Preview"; one helper
      (`apps/files/preview.py`) and one template (`components/file_preview.html`) serve every preview.
- **TypeScript modules:**
  - `main.ts`: imports and configures htmx;
  - `dialog.ts`, `toast.ts`, `upload.ts` (presigned PUT + confirm), `bulk.ts` (select-all, count);
- **Budget:** JS + CSS ≤ 100 KB gzipped, excluding lazy chunks (the chart chunk, the pdf.js preview) and fonts. CI checks it.
- **Accessibility:**
  - target WCAG 2.2 AA;
  - landmarks, one `h1`, a skip link, visible focus;
  - every input labelled; controls at least 32 px (2.5.8 asks for 24);
  - status shown as text, not colour alone;
  - `prefers-reduced-motion` respected;
  - tables with `th scope`;
  - checked in M12 by `axe-core` (pinned npm dev dependency) on every key screen at 1280 and 375 px (tags
    `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`; injected in a `bypass_csp` test context) and by hand in
    `docs/accessibility/wcag-22-aa.md` (keyboard, focus, target size, zoom, reflow, motion, names).

## 13. Testing
- **Database:** tests run against real Postgres 17 (compose locally, a service container in CI), in parallel with
  pytest-xdist. Nothing mocks the ORM.
- **Unit tests:**
  - services: transitions, audit events, amounts;
  - selectors: at-risk, utilization, scoping;
  - the eligibility engine;
  - legacy-model parity;
  - constraints, e.g. one open application.
- **View tests:** Django test client for every page and HTMX partial (full vs partial render), the permission matrix
  (§6), and `django_assert_max_num_queries` on every list view.
- **End to end:** pytest-playwright from M3 (design-kit behaviours: toasts, dialogs, bulk bar, nav, no-JS fallbacks, phone
  width, enforced CSP), run with `config/e2e_settings.py` (HTTP live server, enforced CSP, kit on); user flows from M4:
  - sign up → verify → profile → match → apply;
  - staff review → approve → award;
  - disbursement generate → approve → release;
  - office creates a program and a staff member.
- **Test data:** factory_boy + Faker `en_PH` only; time-machine for terms, windows and fiscal years.
- **Coverage:** at least 90% on `services`, `selectors` and `matching`; at least 80% overall.
- **Every page (M12):** a rendered-page scan of every GET route for every persona (no inline script or style, no
  `on…=` attribute, no `javascript:` URL) and a query budget of at most 25 queries per page, both over a seeded
  world; exceptions carry their reason in the test.

## 14. Settings and environment variables (names only)
- **Mode:** `SCHOLARSYNC_EXPLORE` (set by compose only), `DJANGO_DEBUG`.
- **Core:** `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `SITE_URL`.
- **Security (M13):** `MFA_REQUIRED_FOR_STAFF`, `PASSWORD_BREACH_CHECK`, `SESSION_IDLE_MINUTES_STAFF`,
  `SESSION_IDLE_MINUTES_STUDENT`, `ALLOW_PLAINTEXT_SERVICES`, `CLAMAV_HOST`, `CLAMAV_PORT`,
  `DATABASE_URL_MIGRATIONS`.
- **Proxy:** `TRUSTED_PROXY_COUNT` (default 0; set to the number of proxies in front of the app, usually 1).
- **Database:** `DATABASE_URL`, `DATABASE_URL_UNPOOLED` (optional).
- **Files (S3-compatible):** `S3_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT_URL` (optional), `S3_REGION`, `S3_BUCKET`,
  `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ADDRESSING_STYLE`. `.env.example` carries the local compose storage
  values; production refuses the explore storage secret `scholarsync-explore-secret`.
- **Email:** `EMAIL_URL` (SMTP, URL-style), `DEFAULT_FROM_EMAIL`. Production requires a real SMTP `EMAIL_URL`: blank,
  `console://`, `memory://`, `dummy://` and `file://` refuse to start. STARTTLS is `submission://` (or `?tls=true`),
  implicit TLS `smtp://...:465?ssl=true`; a scheme the parser doesn't know stops startup in every mode (rev 22).
- **Google sign-in (optional):** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.
- **Operator (required in production):** `SITE_OPERATOR_NAME`, `PRIVACY_CONTACT_EMAIL`. In explore and developer modes
  they default to "This local copy" and no email.
- **Ops:** `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`, `CSP_REPORT_ONLY`, `DJANGO_KIT` (design kit; defaults
  to `DJANGO_DEBUG`).
- **Compose only:** `APP_PORT`, `MAIL_PORT`, `DB_PORT`, `STORAGE_PORT`.
- **Rules:**
  - `.env.example` documents every variable (what it is, whether production needs it, format, where to get it), with
    safe placeholders and no secrets.
  - Startup fails fast on a missing required variable in production mode. No insecure fallbacks, ever: v1's
    `SECRET_KEY` default is the lesson.

## 15. CI/CD
GitHub Actions on push and pull request, with read-only permissions, concurrency cancel and timeouts:
- **python:** `uv sync --locked`; then:
  - `ruff check`, `ruff format --check`, `mypy`;
  - `manage.py check --deploy` (production-like environment);
  - `makemigrations --check --dry-run`;
  - `pytest -n auto --cov` on a Postgres 17 service;
  - `pip-audit`.
- **frontend:** `npm ci`, `tsc --noEmit`, `biome check`, `vite build`, budget.
- **e2e** (from M3): build, install Chromium, `pytest -m e2e --ds=config.e2e_settings --browser chromium`.
- **hosting-path** (from M3.5): delete `apps/demo/`, then run the test suite and `manage.py check --deploy` in
  production mode, proving the hosting guide.
- **compose smoke** (from M3.5): `docker compose up` detached, wait for health, check that the login page answers on
  the app port and shows the notice.
- There is no deploy job: self-hosters build the image from source.

## 16. Milestones
Each milestone is broken into small steps (TDD, one commit per step) before work
starts, and ends with every acceptance item checked.

**M0: Planning docs**
- [ ] The contributor guide (now `CONTRIBUTING.md`), `docs/legacy-audit.md`, this spec and `README.md` committed.
- [ ] Spec approved by the maintainer.

**M1: Vercel go/no-go spike** (historical, superseded by revision 5; throwaway branch `spike/vercel`, kept local)
- [ ] Minimal Django + Vite page deployed to a Vercel preview in `sin1`; static files served from the CDN; the
  django-vite manifest resolves at runtime.
- [ ] Build runs Vite → collectstatic → `migrate` + `createcachetable` on the unpooled URL; the runtime uses the pooled
  URL.
- [ ] Neon preview branch forked from `preview-base`.
- [ ] Browser PUT to R2 with signed length/type; confirm sniffs it; presigned GET downloads it as an attachment.
- [ ] Resend send via anymail; cron endpoint called with `CRON_SECRET`.
- [ ] Client IP seen correctly (allauth rate-limit key); cold-start time measured.
- [ ] Production-gating method chosen.
- [ ] Go or no-go recorded. On a no-go, the fallback host is chosen.

**M2: Scaffold + tooling**
- [ ] uv project, Django 5.2, `config/settings.py` (environs), `apps/core`, `/healthz`, JSON logging, Sentry, CSP
  report-only.
- [ ] `compose.yaml` (Postgres, MinIO), `.env.example`, `.gitattributes` (`eol=lf`).
- [ ] ruff, mypy, pytest (+ xdist, factory_boy); Vite + TS + Biome + django-vite; base layout.
- [ ] CI green; `vercel.json` (region, function config, crons; removed in M3.5).

**M3: Design system**
- [ ] Tokens, fonts, icons, components and layouts (§12); `/_kit` page shows every component in every state
  (development only, `DJANGO_KIT`).
- [ ] htmx wired (config, CSRF header, toasts, dialogs, bulk bar); Playwright e2e harness + CI job.
- [ ] Key-screen mockups (student dashboard, apply, staff application review, disbursements, office dashboard)
  **approved by the maintainer** (gate).

**M3c: Redesign (rev 4)**
- [ ] Tokens, components, the white-sidebar app shell (staff, office, student), public and auth layouts, and every
  kit mockup restyled to `docs/design/2026-10-30-redesign/`; a new Scholars mockup with the drawer; full gate green.

**M3.5: Open-source packaging** (before M4)
- [ ] This spec revision (rev 5).
- [ ] Modes in settings (developer, explore, production); the kit refused in production mode.
- [ ] Vercel removed (`vercel.json`, `build.py`, host detection, `VERCEL_ENV` checks).
- [ ] The `apps/demo/` skeleton, its optional hook and the failing deploy check.
- [ ] Runtime commands (`send_outbox`, `cleanup`, worker loop, entrypoint).
- [ ] Provider-neutral settings, `.env.example`, `Dockerfile`, `compose.yaml`, `compose.production.yaml`.
- [ ] CI jobs (hosting-path, compose smoke).
- [ ] README, `docs/SETUP.md`, `docs/HOSTING.md`; the contributor guide (now `CONTRIBUTING.md`) updated.
- [ ] `/about/`, `/privacy/`, `/terms/`, `/cookies/`, `/help/`, `/contact/`, the footer disclaimer, the two
  operator settings, `SECURITY.md`.
- [ ] GitHub Codespaces (optional).
- [ ] Publication (history scan, document review, Vercel/Neon/R2 teardown, repository made public).
- [ ] `docker compose up` shows the existing pages; deleting `apps/demo/` leaves the full suite and `check --deploy`
  green.

**M4: Accounts, email, minimal Program**
- [ ] Custom `User`, `AuditEvent`, allauth (verification, Google, reset, rate limits, reauth), roles; signup only ever
  makes students.
- [ ] Minimal `Program` + `ProgramMembership`; scoping mixins; permission-matrix test.
- [ ] `EmailOutbox` + SMTP transport + `send_outbox` command (email proven through Mailpit in the compose smoke);
  privacy notice (page from M3.5) + `ConsentRecord`.
- [ ] `seed_programs`, `create_office_admin`; first Playwright flow.
- [ ] Demo: one test account per role (student, program staff, program head, scholarship office), the login-page
  notice with one-click filling, and the first sample data, all in `apps/demo/`.

**M5: Files**
- [ ] `StoredFile` intent → PUT → confirm → final; allowlists; sniffing; EXIF strip; attachment downloads with audit;
  `upload.ts`; the compose storage container locally, any S3-compatible service in deployments. A presigned
  upload/download round trip joins the compose smoke test.
- [ ] The live uploader runs on `/_kit/demo/upload/` until M6 (photo) and M7 (documents) use it.

**M6: Reference data + student profile**
- [ ] Full `Program` config, `BenefitTier` (effective-from), `RequiredDocument`, `School`, `AcademicTerm`.
- [ ] Profile sections, photo, completion tracker; staff-created profiles + invite/claim.
- [ ] Profile forms are plain POST/redirect; reference data is seeded, editable from M11.
- [x] The barangay list (38, EMBO included) is checked against PSA PSGC (the maintainer, 2026-11-26).
- [ ] Extend the demo loader for this milestone's screens.

**M7: Matching + student applications**
- [ ] Eligibility engine; legacy model exported to JSON parameters (`apps/matching/data/`, advisory hint only) + parity
  test; `/me/match/`.
- [ ] Apply flow at `/me/applications/` (documents, submit with `match_snapshot`, withdraw, returned → resubmit); status
  page; `application_received` email on submit and resubmit.
- [ ] Submitting needs the personal details section complete ("Finish your personal details before you submit.").
- [ ] Extend the demo loader for this milestone's screens.

**M8: Application review**
- [ ] Staff queue (filters, sorting, pagination), review screen, document approve/decline, return, approve → `Award` +
  first `ScholarTerm`, reject, bulk start review and approve.
- [ ] Extend the demo loader for this milestone's screens.

**M8b: On-behalf applications**
- [ ] Staff form with academics, rule override with a required reason, staff document uploads and submit, student
  read-only view.
- [ ] Extend the demo loader for this milestone's screens (a walk-in profile with an overridden on-behalf application
  and a staff draft).
- Profiles created for the program only; the email lookup arrives in M15 (rev 33, §18 Q16).

**M9: Scholars, terms and renewals**
- [ ] Scholar list and detail, edit, status changes, `ScholarTerm` history, staff term records, merit by rule +
  confirmation, at-risk selector (removed in M15).
- [ ] Renewal applications; office terms page (add school year, make current) with rollover + graduation.
- [ ] Extend the demo loader for this milestone's screens.

**M9b: Import and export**
- [ ] `import` upload purpose (CSV, XLSX); table reading and writing (openpyxl + defusedxml).
- [ ] Manual award creation (`scholars/new/`) through `create_award`.
- [ ] CSV/XLSX import with an all-or-nothing preview (`scholars/import/`, template download).
- [ ] CSV/XLSX export of the filtered scholar list (`scholars/export/`).
- [ ] Extend the demo loader for this milestone's screens.

**M10: Money**
- [ ] Schedules (publish); disbursement generation from tiers; approve/reject/release/revert (reauth); batch; budget,
  spent, committed, utilization; student distribution view; emails.
  - Scope: models + head guard, generation, decisions + emails,
    schedules screens, disbursement screens with reauthenticated release, budget, student payouts.
- [ ] Extend the demo loader for this milestone's screens.

**M11: Dashboards, notifications, tasks and support**
- [ ] Notifications and `notify()`; the student notification center and bell; personal staff tasks; the staff,
  student and office dashboards; the student support form and the office inbox.
- [ ] Extend the demo loader for this milestone's screens.

**M11b: Office management and program settings**
- [ ] Spec rev 18; the M9 fixes (Renew for an inactive program; term changes serialised by an advisory lock).
- [ ] Office: programs (create inactive, edit, activate, deactivate), staff and office accounts with a set-password
  email, memberships (reauth), schools; the overview's budgets in two queries.
- [ ] Program settings at `/staff/<slug>/settings/` (rules and window; history-safe tiers with reauth; required
  documents switched off, never deleted).
- [ ] Extend the demo loader for this milestone's screens.

**M11c: Reports and analytics**
- [ ] Reports (`Report`, `ReportFile`, staff upload at `reports/`, office review); office analytics (trends, success
  rate, approval time, top feeder school); office-wide exports (`StoredFile.Purpose.EXPORT`); staff and office
  notification centers; the office overview's "Reports to review" and "Download report"; cross-program scholars and
  the audit viewer (office: all; head: own program), moved from M11b.
- [ ] Extend the demo loader for this milestone's screens.

**M15: The maintainer's answers (rev 33)**
- [ ] The calendar day dialog on the student, staff and office calendars.
- [ ] At-risk removed; one scholarship per student; the office's "In two or more programs" tab removed.
- [ ] Program reports reviewed by the head before they go to the office.
- [ ] On-behalf filing for a self-registered student found by account email.
- [ ] Seeds: LANI tiers and amounts from the TCU LANI page; CEAA's renewal rule refuses failing grades.
- [ ] Extend the demo loader and the kit for this milestone's screens.

**M16: Support replies (rev 35)**
- [ ] `SupportReply` and `ReplyTemplate`; replies in the app and by email (`support_reply`); the `support_replied`
  notification.
- [ ] The staff and head support inbox and request page; the office request page and reply templates.
- [ ] The student Replies tab and unread counts.
- [ ] Permission matrix; extend the demo loader (templates and an answered request). No kit change: the
  screens reuse cards, lists, tabs, forms and the app dialog.

**M13: Security follow-ups**
- The ASVS gaps and WCAG 2.2.1 left by M12
  (§10 M13 additions).

**M12: Hardening + hosting guide**
- One milestone (the maintainer, 2026-11-18): enforced CSP,
  secret-URL redaction, no-store, sign-in audit, file access by purpose, import retention, double posts, the ASVS L2
  review, the WCAG audit, page query budgets, information pages, the hosting walk, runbook and HSTS preload.
- [ ] Security review (OWASP ASVS L2 checklist), CSP enforced, headers, `check --deploy` clean in production mode.
- [ ] WCAG 2.2 AA audit; query budgets; Playwright suite green; the information pages (M3.5) reviewed against the
  finished product.
- [ ] Hosting checklist in `docs/HOSTING.md`, walked through once on a clean machine:
  - delete `apps/demo/`; copy `.env.example` to `.env` and fill it in;
  - set `SITE_OPERATOR_NAME` and `PRIVACY_CONTACT_EMAIL`; read and adapt the privacy policy, terms and FAQ;
  - provision PostgreSQL, a private S3-compatible bucket (CORS for the site's origin, a 1-day lifecycle rule on
    `pending/`) and email; optionally a Google OAuth client and Sentry;
  - build and run the image behind HTTPS; run the worker or schedule `send_outbox` and `cleanup`;
  - create the first scholarship-office account, then `seed_programs` or create programs in the office screens;
  - run `manage.py check --deploy`.
- [ ] Backups (database dumps or the provider's point-in-time restore) and a short runbook (deploy, roll back, restore,
  rotate secrets) in the hosting guide.

## 17. Risks
| Risk | Mitigation |
|---|---|
| A secret in git history or a document not meant for the public becomes visible when the repo opens | Scan the full history and review every tracked document before publishing (M3.5); rotate, then rewrite history if needed |
| A forgotten `apps/demo/` (published test passwords) in a real deployment | Demo inactive in production mode, and `check --deploy` fails while the folder exists |
| Explore mode exposed beyond the visitor's machine | Ports bound to `127.0.0.1`; settings refuse explore mode with any other host |
| A bad migration can't be rolled back | Expand/contract migrations only; database backups |
| Large bodies reach the app | Direct-to-bucket uploads and exports (§7) |
| Presigned URLs signed for an internal hostname fail in the browser | A public storage endpoint setting; round trip covered by the compose smoke from M5 |
| Rate limits key on the proxy IP | Trusted forwarded-header configuration with a proxy count (§11) |
| The S3-compatible container's image or licence changes | Code speaks only the S3 API; swapping the image is a compose change |
| The legacy model is a toy trained on unknown data | Advisory only, clearly labelled; rules decide; retire or retrain when real data exists |
| Business rules are still unclear (amounts, LANI tier criteria, at-risk) | Rules are data, editable by heads; open questions tracked in §18 |

## 18. Open questions
Answered by the maintainer on 2026-11-21 (rev 33) unless marked otherwise. Sources: the TCU LANI page
(`https://tcu.edu.ph/lani-scholarship`, figures from SY 2015-16) and the TCU-CEAA site (`https://tcu-ceaa.taguig.gov.ph/`),
both read on 2026-11-21.
1. ~~Leaked v1 secrets~~ Resolved 2026-10-12: the maintainer confirmed every v1 key had already been rotated.
2. **Benefit amounts.** LANI's page gives amounts per school year; the app pays per term, so the seeds halve them,
   and a tier's merit amount is the top of the page's range (as v1 read it):

   | LANI tier | Per school year (page) | Seed per term: base / with merit |
   |---|---|---|
   | Premier | ₱40,000–₱50,000 | ₱20,000 / ₱25,000 |
   | Full (v1 called it Honors) | ₱40,000–₱50,000 | ₱20,000 / ₱25,000 |
   | Priority | ₱40,000–₱50,000 | ₱20,000 / ₱25,000 |
   | Basic Plus (Basic + SUC/LCU) | ₱15,000 | ₱7,500 / none |
   | SUC/LCU | ₱10,000 | ₱5,000 / none |
   | Basic | ₱10,000 | ₱5,000 / none |
   | Review (one-time, first-time takers) | ₱10,000 | ₱10,000 / none, paid once (never renewed) |
   | Review, retake | ₱5,000 | ₱5,000 / none, paid once |
   | LEAD | not stated | v1's ₱30,000 / ₱50,000 kept, confirmed by the maintainer (2026-11-26) |

   The merit incentive is for Premier, Full and Priority scholars with a semestral weighted average of 1.75 or better
   (or its school's cum laude equivalent). The CEAA site states no amount: v1's ₱5,000 / ₱10,000 stays. Every amount
   is data a head can change in the program settings.
3. **LANI tier criteria** (the page): Premier: UP System (Luzon) or a CHED Center of Excellence in the NCR; Full and
   Priority: a DOST priority course in a DOST-listed school, a PWD endorsed by the city PDAO, or law or medicine in a
   listed top school; Basic Plus: a Taguig (or nearby) public high school graduate at an SUC/LCU in the NCR; SUC/LCU:
   a private high school graduate at an SUC/LCU in the NCR; Basic: a public high school graduate not at an SUC/LCU;
   Review: a graduate preparing for a board or bar exam; LEAD: master's or doctoral study for Taguig government
   employees and private-school teachers with three years' service, 50 or younger. Every applicant: a Taguig resident
   for three years, a registered voter if 18 or older with a parent who is one. Staff pick the tier on approval; the
   app doesn't derive it.
4. **Renewal criteria.** CEAA (the site): GWA of at least 80% with no failing, incomplete, blank or dropped subjects
   and at least 15 units a semester; the seed adds the no-failing-grades rule. CEAA's merit incentive is for renewing
   scholars with an SWA of 88.75% or better. LANI's page states no renewal threshold: v1's "SWA not lower than 2.5"
   stays, on the 1.0–5.0 scale (the page's merit threshold, 1.75, is on that scale). Staff confirm merit.
5. **At-risk:** removed (rev 33).
6. **One scholarship per student** (rev 33, §4.5); this reverses the M8 default.
7. **Head vs staff:** heads set the budget, and staff report to their head (§6; program reports go through the head,
   §4.8).
8. **Term limit:** none; a scholar continues while enrolled and meeting the renewal rules. `max_terms` stays an
   optional program setting, blank in the seeds.
9. **Budget:** the scholarship office gives each program its budget, and the program's head enters and manages it
   (as built in M10). The budget year stays the distribution day's calendar year.
10. **Retention:** what RA 10173 requires, which each host sets as its own policy (`docs/HOSTING.md`). The app keeps
    its M12 default: import files leave storage after 7 days, everything else is kept until the host removes it.
11. **Staff and student accounts:** as built: staff create profiles for their program and invite the student, who
    claims the account.
12. ~~Vercel plan~~ Obsolete (revision 5): nobody hosts an official copy.
13. ~~Domain and sender domain~~ Obsolete (revision 5): each host configures its own.
14. **v1:** not in use by the City; there is no cut-over.
16. **Email lookup:** yes, staff can file for a self-registered student found by the exact email of their account
    (rev 33, §4.5).

## 19. Decisions (2026-10-11 → 2026-10-30)
| Decision | Why |
|---|---|
| Rewrite in a new private repo (`ScholarSyncV2`); legacy stays a read-only reference | v1's structure can't be fixed incrementally |
| Django 5.2 LTS | The maintainer's choice; auth, ORM, migrations, CSRF and forms built in; LTS until April 2028 |
| Fresh start with seed data | The maintainer's choice; no v1 data migration |
| Django templates + HTMX + a little TypeScript | The maintainer's choice; replaces 30 global-JS files with server-rendered partials |
| Host on Vercel (superseded 2026-10-30 by the open-source decision below) | The maintainer's choice; designed around its limits, with an M1 spike and a fallback |
| Rules decide eligibility; the legacy model only advises | The maintainer's choice; auditable decisions for a public benefit |
| Programs are data | Removes the 67–99% CEAA/LANI duplication; new programs need no code |
| `ScholarTerm` per award per term; applications kept after approval | v1 overwrote term data and deleted applications, losing history |
| S3-compatible storage for files (R2 was the first choice) | Private, presigned, swappable; any provider works since revision 5 |
| Outbox + a small worker loop instead of Celery (was daily cron on Vercel) | Retries without a broker or new infrastructure |
| Region `sin1` + Neon Singapore (historical, M1 spike only) | Users are in Taguig; no longer a target |
| A short contributor guide (`CONTRIBUTING.md`) is tracked; personal notes and tool settings stay local | The maintainer's request (2026-10-12, revised 2026-11-19) |
| Redesign rev 4: red primary, blue secondary, yellow accent; Cark-style white sidebar shell (2026-10-30) | The maintainer's choice after reviewing and editing the design canvas |
| Open source, one-command run, provider-neutral self-hosting; Vercel dropped (2026-10-30, revision 5) | The maintainer's portfolio project: nobody hosts an official copy, visitors run it on localhost with test accounts, self-hosters bring their own providers. Design: `docs/design/2026-10-30-open-source-self-hosting-design.md` |
| Public information pages and a not-affiliated footer disclaimer (2026-10-30) | The repo is public and anyone can host it; the pages say it isn't an official City service, what happens to data, and who is responsible |
