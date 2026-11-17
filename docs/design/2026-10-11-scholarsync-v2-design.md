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
| Charts / icons / fonts | **Chart.js** (lazy chunk), **Lucide** SVG sprite, **Fontsource** Lexend + Source Sans 3 (self-hosted) | No runtime CDNs |
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
  awards/          Award, ScholarTerm, renewals, term rollover, at-risk selector
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
- **Barangays** (38, source "PSA PSGC, not yet verified; EMBO included per the maintainer, 2026-11-08"): Bagumbayan, Bambang,
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
  - `export` files are written by the server only and never go through an upload intent;
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
    one term; one student may hold awards in two programs at once (§18 Q6).
  - Approved applications are kept: they're the history.
  - **On behalf (M8b, decided 2026-11-14):**
    - two more fields: `on_behalf` (bool; `created_by` is then the staff member) and `override_reason` (text, at most
      1,000 characters), with constraint `applications_override_only_on_behalf`: a reason is stored only on an
      on-behalf row;
    - staff file only for profiles created for their program (`created_for=program`), claimed or not. Finding a
      self-registered student by the exact email of their account is not built (§18 Q16). Until the maintainer decides, such a
      student asks the office, and the office creates a staff profile only for someone with no account;
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
      a record for {term}."); it creates the next `ScholarTerm` and sets the award's tier to the chosen one;
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
  - constraint: at most one active award per (`profile`, `program`). A student may hold awards in two programs at
    once (§18 Q6); the review screen notes it.
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
      program, holding an award in it, or with a submitted application to it. The app never searches every student
      (as §18 Q16);
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
- **At-risk** is derived, never stored (a proposal pending §18 Q5): an `active` award is at risk when its latest term
  record's GWA misses the renewal GWA rule for its scale (no rule for that scale: not flagged), or its units are under
  `renewal_min_units`, or its renewal is due and the program's window has closed.
- **Term change and rollover (M9):**
  - the scholarship office moves the current term on `/office/terms/`: it adds the next school year (three terms, the
    seed's dates) and makes a later term current ("The current term can only move forward."); the old flag is cleared
    before the new one is set;
  - making a term current runs `awards.services.rollover(term)` for every program in the same transaction: `draft`
    and `returned` applications of earlier terms are withdrawn (`application.expired`; submitted and under-review
    rows stay for staff); `active` and `suspended` awards with at least `program.max_terms` term records graduate
    (blank means no limit; "final year" graduation is a manual status change, §18 Q8);
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
- **`Report`:**
  - fields: `program`, `title`, `period_start`, `period_end`, `description`, `status`, `submitted_by`, `reviewed_by`,
    `review_note`;
  - transitions: `submitted` → `accepted` or `returned`; `returned` → `submitted`.
- **`ReportFile`:** `report`, `file` FK `StoredFile`.
- **`Task`** (M11): `owner`, `program` (nullable), `title`, `notes` (≤ 2,000), `due_on`, `done_at`.
  - A personal to-do of one staff member in one program. M11's screens always set `program`; a program-less (office)
    task waits for M11c.
  - Only the owner sees, edits, completes or deletes it; anyone else, heads and the office included, gets a 404.
    Deleting is allowed (a to-do is not a record). Every change is audited with the id and program, never the title.
  - `tasks/` has Open (overdue first, then by due date, undated last) and Done (newest first) tabs, 25 a page; the
    staff nav item "Tasks" counts open tasks due on or before today.
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
  - Audited as `support.sent` and `support.answered` (ids, topic, program id), never the message.
- **`EmailOutbox`:** `to`, `kind`, `context` (JSON, whitelisted strings only; see §9), `status` ∈ {queued, sent, failed}, `attempts`,
  `last_error`, `provider_message_id`, `sent_at`.
- **`AuditEvent`:** `actor`, `action` (dotted, e.g. `application.approved`), `program` (nullable), `target_type`,
  `target_id`, `data` (JSON diff, no secrets), `ip_hash`, `at`. Append-only: no update or delete views.

## 5. URL map
| Area | URL | Who |
|---|---|---|
| Public | `/`, `/programs/` (M6), `/programs/<slug>/` (M6), `/about/`, `/help/`, `/privacy/`, `/terms/`, `/cookies/`, `/contact/` (the six information pages; footer disclaimer in §11) | anyone |
| Health | `/healthz` (database ping, no details) | anyone |
| Accounts | `/accounts/…` (allauth: signup, login, logout POST, email confirm, password reset, Google), `/accounts/claim/<token>/` | anyone |
| Student | `/me/` (dashboard), `/me/profile/` (+ `personal/`, `family/`, `family/<id>/` + `…/delete/`, `education/`, `education/<id>/` + `…/delete/`, `photo/`) | student (own records only) |
| Student | `/me/match/`, `/me/applications/`, `/me/applications/new/<slug>/` (GET: confirm page; POST: creates the draft), `/me/applications/<id>/`, `/me/applications/<id>/documents/<requirement>/` (POST), `…/submit/` (POST), `…/withdraw/` | student (own records only) |
| Student | `/me/scholarships/` (awards, terms, renewals, payouts and the next distribution), `/me/scholarships/<award>/renew/` (POST), `/me/notifications/` (+ `<id>/`, which marks it read and redirects; `read/` POST), `/me/support/` (M11) | student |
| Staff | `/staff/<slug>/` (dashboard) | program staff/head |
| Staff | `students/` (unclaimed profiles created for this program), `students/new/`, `students/<id>/invite/` | program staff/head |
| Staff | `applications/` (queue), `applications/<id>/` (review), `applications/<id>/start/`, `applications/<id>/documents/<document>/approve/`, `applications/<id>/documents/<document>/decline/`, `applications/<id>/decide/` (approve, return or reject), `applications/bulk/` (start review, approve; POST) | program staff/head |
| Staff | `applications/new/` (in progress + profile picker; POST starts), `applications/behalf/<id>/` (filing page), `…/academics/`, `…/documents/<requirement>/`, `…/submit/`, `…/withdraw/` (POST) | program staff/head |
| Staff | `scholars/`, `scholars/<award>/`, `…/edit/`, `…/status/`, `…/terms/new/`, `…/terms/<term>/`, `…/terms/<term>/merit/` (POST); `scholars/new/`, `scholars/import/`, `scholars/import/template/`, `scholars/export/` (M9b) | program staff/head |
| Staff | `schedules/`, `schedules/new/`, `schedules/<id>/`, `schedules/<id>/publish/` (POST); `disbursements/`, `disbursements/<schedule>/`, `…/generate/` (POST), `…/bulk/` (POST), `…/<id>/reject/`, `…/<id>/revert/` (POST); `budget/`, `budget/edit/` | program staff/head (see §6) |
| Staff | `tasks/` (+ `<id>/`, `<id>/done/` POST, `<id>/delete/` POST; owner only, M11), `reports/` (M11c), `settings/` (rules and window; `tiers/`, `tiers/new/`, `tiers/<code>/`; `documents/`, `documents/<id>/`, `documents/<id>/active/` POST; M11b) | staff; `settings/` is head (and office) only |
| Office | `/office/` (dashboard); M11b: `programs/` (+ `new/`, `<id>/`, `<id>/active/` POST), `staff/` (+ `new/`, `<id>/`, `<id>/active/`, `<id>/welcome/`, `<id>/memberships/` POST), `memberships/<id>/` POST, `schools/` (+ `new/`, `<id>/`); `terms/` (M9: list, `add/` POST, `<term>/current/`), `support/` (+ `<id>/answer/` POST; M11); M11c: `scholars/`, `reports/`, `analytics/`, `audit/` | super admin |
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
- **The scholar list** (`scholars/`, M9): tabs Active (default), Suspended, Inactive, Graduated, At risk, Not renewed
  (due this term), All; a name search (every word matches first or last name) and a tier filter by code; 25 rows a
  page, unknown values fall back to the defaults; columns scholar, school, tier, GWA (latest term), terms, status;
  `?scholar=<id>` opens a drawer with the facts, renewal status, at-risk reasons and "Open record". The staff nav has
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
- **Proposed head vs staff split** (open question §18):

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
  must have no known signature and no NUL byte in its first 4 KB. Import files are never downloadable.

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
  name search. `StoredFile.Purpose.EXPORT` and `exports/` keys stay reserved for M11c's office-wide exports.
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
      so the page says "Suggested by v1's model; advisory, and the model's income units are unknown.";
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

  Staff and the office get no notifications in M11. Support messages are never emailed (free text).
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
  - logout is POST only.
- **CSRF and redirects:**
  - Django CSRF on every form; HTMX sends `X-CSRFToken` through `hx-headers` on `<body>`;
  - redirects are validated with `url_has_allowed_host_and_scheme`.
- **Headers:**
  - HSTS: 1 year, includeSubDomains; preload after launch;
  - `nosniff`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin`, a strict `Permissions-Policy`.
- **CSP:**
  - `default-src 'self'`; `script-src 'self'`; `style-src 'self'`;
  - `img-src 'self' data: <storage-origin>`; `connect-src 'self' <storage-origin> <sentry-ingest>`;
  - `frame-ancestors 'none'`; `form-action 'self'`;
  - htmx config (a `<meta name="htmx-config">`): `allowEval: false`, `allowScriptTags: false`,
    `includeIndicatorStyles: false`, `selfRequestsOnly: true`, and `historyCacheSize: 0` so page snapshots holding
    personal data never land in `localStorage`; no `hx-on`, no inline scripts or styles.
- **Errors:** `DEBUG=False` in every deployment; custom 400/403/404/500 pages; nothing internal reaches the client.
- **Logging:**
  - JSON to stdout, with user IDs but no names, emails or document contents;
  - Sentry's `before_send` scrubs request bodies and cookies.
- **Dependencies:** `pip-audit` (on `uv export`) and `npm audit` in CI; Dependabot.
- **RA 10173 (Data Privacy Act):**
  - a privacy notice and a consent record;
  - collect only what eligibility needs;
  - program-scoped access, with an audit of every document view;
  - a private bucket;
  - a retention period (open question);
  - "download my data" and account-deletion requests, handled by the office in v2.0.

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
- **Demo:** everything demo-only (test accounts, sample data, login-page notice) lives in `apps/demo/`. Deleting that
  folder removes it with no other edit; the app reaches it only through an optional hook, never by import. It is
  inactive in production mode even if present, and `check --deploy` fails while the folder exists. Programs
  (`seed_programs`) are not demo material.
- **Providers:** any PostgreSQL 17 (`DATABASE_URL`), any S3-compatible storage, any SMTP server, Google sign-in when
  keys are set, Sentry when a DSN is set.
- **Proxy settings:** `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`; hosts and CSRF origins come from
  `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`; allauth reads the client IP from the forwarded header with
  a trusted-proxy count.
- **Migrations:** expand/contract only; the entrypoint runs `migrate` against the unpooled URL when set.
- **Guides:** `README.md` (quick start, test accounts), `docs/SETUP.md` (local run, developer workflow) and
  `docs/HOSTING.md` (self-hosting checklist, M12). `compose.production.yaml` (web and worker only) is the hosting
  example.
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
    edges); pills (999 px) only for counts; shadows only on floating layers (drawer, dialog, toast, menus).
  - Light theme in v2.0; tokens are role-named so a dark theme can be added later.
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
  - dialogs load content into `<dialog>`, and `dialog.ts` opens them;
  - toasts come from `HX-Trigger: {"toast": …}`, read by `toast.ts` into an `aria-live` region;
  - bulk actions are a form with checkboxes;
  - every form also works as a normal POST without JS.
- **Dashboards (M11):**
  - **student** (`/me/`, the approved mockup): returned banners (not on-behalf), one award card per active or
    suspended award ("To renew:" from the program's renewal rules), profile, the 5 newest applications, the 3 newest
    payouts with M10's student labels, the 3 newest notifications; the bell shows the unread count on every student
    page;
  - **staff** (`/staff/<slug>/`, kit figures and attention rows): "Active scholars", "Applications waiting",
    "Released this year", "At risk"; "Needs attention" (waiting over 7 days from `submitted_at`, own overdue tasks,
    at risk, prepared payouts, approved payouts, the window); "Applications by month" (6 months by
    `first_submitted_at` in Manila, zero-filled, CSS bars in 5 % steps + "View as table"); "Your tasks";
  - **office** (`/office/`, the approved mockup) without "Download report" (M11c), "New program" and "Manage
    programs" (M11b) and "Reports to review" (M11c, replaced by "Support requests"); needs attention per program
    (waiting over 7 days, budget used ≥ 75 %) and open support requests; recent activity from audit events with a
    sentence, where a student actor reads "A student".
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
- **TypeScript modules:**
  - `main.ts`: imports and configures htmx;
  - `dialog.ts`, `toast.ts`, `upload.ts` (presigned PUT + confirm), `bulk.ts` (select-all, count);
  - `charts.ts`: a dynamic import of Chart.js that reads `{{ data|json_script }}`.
- **Budget:** JS + CSS ≤ 100 KB gzipped, excluding the lazy chart chunk and fonts. CI checks it.
- **Accessibility:**
  - target WCAG 2.2 AA;
  - landmarks, one `h1`, a skip link, visible focus;
  - every input labelled; controls at least 32 px (2.5.8 asks for 24);
  - status shown as text, not colour alone;
  - `prefers-reduced-motion` respected;
  - tables with `th scope`.

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

## 14. Settings and environment variables (names only)
- **Mode:** `SCHOLARSYNC_EXPLORE` (set by compose only), `DJANGO_DEBUG`.
- **Core:** `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `SITE_URL`.
- **Proxy:** `TRUSTED_PROXY_COUNT` (default 0; set to the number of proxies in front of the app, usually 1).
- **Database:** `DATABASE_URL`, `DATABASE_URL_UNPOOLED` (optional).
- **Files (S3-compatible):** `S3_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT_URL` (optional), `S3_REGION`, `S3_BUCKET`,
  `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ADDRESSING_STYLE`. `.env.example` carries the local compose storage
  values; production refuses the explore storage secret `scholarsync-explore-secret`.
- **Email:** `EMAIL_URL` (SMTP, URL-style), `DEFAULT_FROM_EMAIL`. Production requires a real SMTP `EMAIL_URL`: blank,
  `console://`, `memory://`, `dummy://` and `file://` refuse to start.
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
- [ ] The contributor guide, `docs/legacy-audit.md`, this spec and `README.md` committed.
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
- [ ] README, `docs/SETUP.md`, `docs/HOSTING.md`; the contributor guide updated.
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
- [ ] The barangay list (38, EMBO included) is not yet verified against PSA PSGC; check it in a browser.
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
- Profiles created for the program only; the email lookup waits for the maintainer (§18 Q16).

**M9: Scholars, terms and renewals**
- [ ] Scholar list and detail, edit, status changes, `ScholarTerm` history, staff term records, merit by rule +
  confirmation, at-risk selector.
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

**M12: Hardening + hosting guide**
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
1. ~~Leaked v1 secrets~~ Resolved 2026-10-12: the maintainer confirmed every v1 key had already been rotated.
2. Confirm the benefit amounts per program and tier.
3. What qualifies a student for each LANI tier (honors, premier, priority, basic plus, basic, SUC/LCU, review, lead)?
4. Renewal criteria: is CEAA's "GWA ≥ 80%, ≥ 15 units" right? What scale is LANI's "SWA not lower than 2.5" on?
5. Definition of at-risk. Proposed in M9 (§4.6): the latest term misses the renewal GWA or units, or the award is
   not renewed after the window closed.
6. Can one student hold CEAA and LANI at the same time? Decided 2026-11-13 (M8): yes, one active award per program
   (v1 never checked across programs). The maintainer to confirm.
7. Head vs staff powers (§6 proposal).
8. Maximum terms per program; graduation rules. M9: the summer term never renews; awards graduate at `max_terms`
   on rollover, and by hand for the final year.
9. Budget figures; confirm the City fiscal year (January–December) as the budget period. M10: a disbursement counts
   in the year of its schedule's distribution date; over budget is shown, not blocked.
10. RA 10173 retention period for documents and closed records.
11. Can staff create student accounts, or only profiles that students claim?
12. ~~Vercel plan~~ Obsolete (revision 5): nobody hosts an official copy.
13. ~~Domain and sender domain~~ Obsolete (revision 5): each self-hoster chooses their own.
14. Is v1 still used by the City, and is there a cut-over date?
16. Can staff file for a self-registered student found by the exact email of their account? (M8b; not
    built.) It reaches students who never touched the program and tells staff whether an address has an account.
    M9b matches imports only within the program's own students for the same reason.

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
| A short contributor guide is tracked; personal notes stay local | The maintainer's request (2026-10-12) |
| Redesign rev 4: red primary, blue secondary, yellow accent; Cark-style white sidebar shell (2026-10-30) | The maintainer's choice after reviewing and editing the design canvas |
| Open source, one-command run, provider-neutral self-hosting; Vercel dropped (2026-10-30, revision 5) | The maintainer's portfolio project: nobody hosts an official copy, visitors run it on localhost with test accounts, self-hosters bring their own providers. Design: `docs/design/2026-10-30-open-source-self-hosting-design.md` |
| Public information pages and a not-affiliated footer disclaimer (2026-10-30) | The repo is public and anyone can host it; the pages say it isn't an official City service, what happens to data, and who is responsible |
