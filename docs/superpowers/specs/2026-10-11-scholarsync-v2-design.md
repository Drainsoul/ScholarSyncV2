# ScholarSync V2: design spec

- **Revision:** 1 (2026-10-12)
- **Status:** draft, awaiting Kenneth's approval. No product code is written until this is approved and the M1 plan
  exists.
- **Inputs:**
  - `docs/legacy-audit.md` (v1 features, rules and problems);
  - Kenneth's decisions of 2026-10-11 (§19);
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
7. **Runs on Vercel within its limits** (§11), with a documented fallback host.

**Non-goals (v2.0)**
- Migrating v1 data: this is a fresh start with seed data.
- A public JSON API or SPA, a native mobile app, SMS, or payments integration (disbursement is recorded, not paid
  out).
- Real-time features (WebSockets), dark theme, multi-language UI (English only; Filipino later).
- Retraining the legacy model.

## 2. Stack
Versions are pinned to the latest stable release when M2 scaffolds the project, then recorded in `STATE.md`.

| Layer | Choice | Notes |
|---|---|---|
| Language/runtime | Python 3.13, managed by **uv** (`uv.lock`) | Vercel supports 3.12–3.14 |
| Framework | **Django 5.2 LTS** | Supported until April 2028 |
| Settings | One `config/settings.py` reading the environment with **environs[django]** | `.env` locally, Vercel env vars in deployments |
| Database | **PostgreSQL 17** on **Neon** (Vercel Marketplace, Singapore), **psycopg 3** | Pooled URL at runtime, unpooled for migrations |
| Auth | **django-allauth** (account + Google provider), **argon2-cffi** | Email login, mandatory verification, rate limits, reauthentication |
| Templates | Django templates + **django-htmx** + **django-template-partials** | `{% partialdef %}` for HTMX fragments |
| Front-end build | **Vite** + strict **TypeScript** + **Biome**, **django-vite** | Same tooling as PersonalWebsite |
| Charts / icons / fonts | **Chart.js** (lazy chunk), **Lucide** SVG sprite, **Fontsource** Poppins + Inter (self-hosted) | No runtime CDNs |
| Files | **Cloudflare R2** via **django-storages** (S3 backend, boto3), **Pillow**, **filetype** | Private bucket, presigned URLs |
| Import/export | stdlib `csv`, **openpyxl** | Row-by-row Django Forms with a preview |
| Email | **django-anymail** (Resend) + an `EmailOutbox` table | HTTP API, batch sends |
| Security headers | **django-csp** | Report-only from M2, enforced at launch |
| Observability | **sentry-sdk** (`send_default_pii=False`), JSON logs to stdout | Hobby keeps runtime logs for 1 hour |
| Lint/type | **ruff** (lint + format), **mypy** + **django-stubs** | |
| Tests | **pytest**, pytest-django, pytest-xdist, factory_boy, Faker (`en_PH`), time-machine, coverage, **pytest-playwright** | Real Postgres in tests |
| Local services | `compose.yaml`: Postgres 17, MinIO (S3-compatible) | |
| Host | **Vercel**: Python runtime, Fluid compute, region `sin1`, Cron | Fallback: Docker on Fly.io or Render (Singapore) |
| CI | GitHub Actions | §15 |

**Deliberately absent:**
- background workers, Celery and Redis (we use an outbox plus cron);
- a state-machine library (we use an explicit transition map plus database constraints);
- numpy, pandas and scikit-learn at runtime;
- jQuery, Tailwind and any UI framework.

## 3. Architecture
```
config/            settings.py, urls.py, wsgi.py
apps/
  accounts/        User (email login, role), allauth adapters, invite/claim
  programs/        Program, ProgramMembership, BenefitTier, RequiredDocument, School, AcademicTerm
  students/        StudentProfile, FamilyMember, EducationRecord, ConsentRecord
  files/           StoredFile, upload intents, presign/confirm/download
  applications/    Application, Document, DocumentFile, review services
  awards/          Award, ScholarTerm, renewals, term rollover, at-risk selector
  money/           DistributionSchedule, Disbursement, Budget
  matching/        eligibility engine, legacy model hint (+ data/legacy_tier_model.json)
  reports/         Report, ReportFile
  workspace/       Task, Notification, EmailOutbox
  office/          super-admin views (no models of its own)
  core/            AuditEvent, permissions, mixins, layouts, health, cron auth, errors
templates/         base.html, layouts/{public,auth,student,staff,office}.html, partials/, components/, emails/
frontend/          src/{main,dialog,toast,upload,charts,bulk}.ts, src/styles/{tokens,base,components,layouts}.css
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
    `is_staff` (Django admin only), `last_login`;
  - signup always creates `role=student`;
  - only a super admin (via a service) or `create_office_admin` can create staff or super admins.
- **`ProfileInvite`:**
  - fields: `profile` FK, `email`, `token_hash`, `expires_at`, `claimed_at`;
  - lets the owner of a staff-created `StudentProfile` claim it by verifying that email.

### 4.2 programs
- **`School`:** `name` (unique), `type` ∈ {public, private, SUC, LCU}, `grading_scale` ∈ {percent, one_to_five,
  four_point}, `is_in_taguig`.
- **`AcademicTerm`:**
  - fields: `school_year_start` (e.g. 2026), `term` ∈ {1, 2, 3 (summer)}, `starts_on`, `ends_on`, `is_current`;
  - constraints: unique (`school_year_start`, `term`); at most one current term (partial unique).
- **`Program`:**
  - identity: `slug` (e.g. `tcu-ceaa`, `lani`), `name`, `description`, `is_active`;
  - window and limits: `applications_open_on`, `applications_close_on`, `max_terms`, `claim_location_default`;
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
  - lookup: the amount for a term is the row with the latest `effective_from` ≤ that term.
- **`RequiredDocument`:**
  - fields: `program`, `code`, `label`, `help_text`, `applies_to` ∈ {new, renewal, both}, `is_required`,
    `accepted_types` (pdf/jpg/png), `max_bytes`, `sort_order`;
  - constraint: unique (`program`, `code`).

**Seed data** (`seed_programs`):
- TCU CEAA, with one tier `standard` (5,000 base / 10,000 merit).
- LANI, with tiers honors / premier / priority (20,000 / 25,000), basic plus (10,000 / 15,000), basic and SUC/LCU
  (7,500 / 12,500), review (15,000 / 20,000) and lead (30,000 / 50,000).
- The required documents from the v1 templates.
- These are the v1 admin values (`docs/legacy-audit.md` §3), pending Kenneth's confirmation.

### 4.3 students
- **`StudentProfile`:**
  - `user` (nullable, unique): null for staff-created or imported records until they are claimed;
  - name fields; `birth_date`; `sex`; `phone`;
  - address: `address_line`, `barangay` (choices: Taguig barangays), `district`;
  - `residing_since` (year); `is_registered_voter`; `monthly_household_income`;
  - `photo` FK `StoredFile`;
  - `created_by`;
  - `completion` is computed from required fields.
- **`FamilyMember`:** `profile`, `relation` ∈ {father, mother, guardian, sibling}, name, `occupation`,
  `monthly_income`, `contact`.
- **`EducationRecord`:** `profile`, `level` ∈ {elementary, jhs, shs, als, college}, `school` FK, `course`,
  `year_level`, `gwa` (Decimal), `gwa_scale` (copied from the school, overridable), `units`, `year_from`, `year_to`,
  `is_current`.
- **`ConsentRecord`:** `profile`, `notice_version`, `consented_at`, `ip_hash`. Recorded at signup and whenever the
  privacy notice changes.

### 4.4 files
- **`StoredFile`:**
  - fields: `key` (R2 object key), `status` ∈ {pending, ready, rejected}, `original_name`, `declared_type`,
    `sniffed_type`, `size`, `sha256`, `uploaded_by`, `purpose` ∈ {document, photo, report, export};
  - flow: §7.

### 4.5 applications
- **`Application`:**
  - fields:
    - `profile`, `program`, `term`, `kind` ∈ {new, renewal}, `award` (renewal only);
    - `requested_tier` FK `BenefitTier`;
    - academic: `school`, `course`, `year_level`, `gwa`, `gwa_scale`, `units`;
    - `match_snapshot` (JSON: eligibility result and model hint at submit time), `status`;
    - `submitted_at`, `decided_at`, `decided_by`, `decision_reason`, `created_by` (the student or staff).
  - transitions:
    - `draft` → `submitted` (all required documents uploaded) or `withdrawn`;
    - `submitted` → `under_review` or `withdrawn`;
    - `under_review` → `returned` (needs fixes; reason required), `approved` or `rejected` (reason required);
    - `returned` → `submitted` or `withdrawn`.
  - constraint: at most one *open* application (draft, submitted, under_review or returned) per (`profile`, `program`,
    `term`), as a partial unique index.
  - Approved applications are kept: they're the history.
- **`Document`:**
  - fields: `requirement` FK `RequiredDocument`; exactly one of `application` FK / `scholar_term` FK (a
    `CheckConstraint` enforces the XOR); `status` ∈ {pending, approved, declined}; `decline_reason`; `reviewed_by`;
    `reviewed_at`;
  - constraints: unique (`requirement`, `application`) and unique (`requirement`, `scholar_term`);
  - transitions: `pending` → `approved` or `declined`; `declined` → `pending` (re-upload).
- **`DocumentFile`:** `document`, `file` FK `StoredFile`, `version`, `is_current`. A document holds one or more files,
  and re-uploads add a version.

### 4.6 awards
- **`Award`** (a scholar in a program):
  - fields: `profile`, `program`, `tier`, `student_number`, `status` ∈ {active, suspended, inactive, graduated},
    `source` ∈ {applied, imported, manual}, `source_application` (nullable), `started_term`, `ended_term`, `notes`;
  - constraint: at most one active award per (`profile`, `program`);
  - whether a student can hold CEAA and LANI at once is an open question (§18).
- **`ScholarTerm`:**
  - fields: `award`, `term`, `year_level`, `course`, `school`, `gwa`, `gwa_scale`, `units`, `merit` (bool),
    `merit_confirmed_by`, `compliance` ∈ {incomplete, complete};
  - constraint: unique (`award`, `term`);
  - `merit` is proposed by the program's merit rule and confirmed by staff;
  - `compliance` is recomputed when documents change: complete only when every required renewal document is
    approved.
- **Lifecycle:**
  - An approved new application creates an `Award` (`source=applied`) and the first `ScholarTerm`.
  - An approved renewal application creates the next `ScholarTerm`.
  - Import or manual creation makes an `Award` + `ScholarTerm` with `source=imported` or `source=manual`.
- **At-risk** is derived, never stored: `awards.selectors.at_risk()` flags awards whose latest `ScholarTerm` GWA misses
  the renewal threshold, or whose renewal documents are past the application window. The exact definition is an open
  question.
- **Term rollover** (`awards.services.rollover(term)`):
  - creates no records by itself;
  - opens renewals for active awards;
  - advances `year_level` on the next `ScholarTerm`;
  - marks awards `graduated` after `program.max_terms` terms or the final year;
  - replaces v1's bulk `update_years`.

### 4.7 money
- **`DistributionSchedule`:** `program`, `term`, `distribution_date`, `claim_location`, `notes`, `frequency_label`,
  `is_published` (students only see published schedules).
- **`Disbursement`:**
  - fields: `scholar_term`, `schedule`, `amount` (snapshot from `BenefitTier` + merit at generation), `status`,
    `approved_by`, `approved_at`, `released_at`, `decision_reason`;
  - constraint: unique (`scholar_term`, `schedule`);
  - transitions:
    - `pending` → `approved` or `rejected`;
    - `approved` → `released`, or back to `pending` (revert; needs reauthentication, and only before release);
    - `rejected` → `pending` (revert, needs reauthentication);
    - `released` is final.
- **`Budget`:** `program`, `fiscal_year` (City fiscal year, January–December), `amount`.
  - spent = released disbursements in that year;
  - committed = approved but not released;
  - remaining = amount − spent − committed;
  - utilization = (spent + committed) / amount.
- **Student view:** times claimed, total received, remaining for the current award year, next published schedule.

### 4.8 reports, workspace, core
- **`Report`:**
  - fields: `program`, `title`, `period_start`, `period_end`, `description`, `status`, `submitted_by`, `reviewed_by`,
    `review_note`;
  - transitions: `submitted` → `accepted` or `returned`; `returned` → `submitted`.
- **`ReportFile`:** `report`, `file` FK `StoredFile`.
- **`Task`:** `owner`, `program` (nullable), `title`, `notes`, `due_on`, `done_at`.
- **`Notification`:** `recipient`, `kind`, `title`, `body`, `url`, `read_at`.
- **`EmailOutbox`:** `to`, `template`, `context` (JSON), `status` ∈ {queued, sent, failed}, `attempts`,
  `last_error`, `provider_message_id`, `sent_at`.
- **`AuditEvent`:** `actor`, `action` (dotted, e.g. `application.approved`), `program` (nullable), `target_type`,
  `target_id`, `data` (JSON diff, no secrets), `ip_hash`, `at`. Append-only: no update or delete views.

## 5. URL map
| Area | URL | Who |
|---|---|---|
| Public | `/`, `/programs/`, `/programs/<slug>/`, `/help/`, `/privacy/`, `/terms/` | anyone |
| Health | `/healthz` (database ping, no details) | anyone |
| Accounts | `/accounts/…` (allauth: signup, login, logout POST, email confirm, password reset, Google), `/accounts/claim/<token>/` | anyone |
| Student | `/me/` (dashboard), `/me/profile/` (+ `personal/`, `family/`, `education/`, `photo/`) | student |
| Student | `/me/match/`, `/me/applications/`, `/me/applications/new/<slug>/`, `/me/applications/<id>/` (documents, submit, withdraw) | student (own records only) |
| Student | `/me/scholarships/` (awards, terms, disbursements, schedules), `/me/notifications/` | student |
| Staff | `/staff/<slug>/` (dashboard) | program staff/head |
| Staff | `applications/`, `applications/new/` (on behalf), `applications/<id>/` (review, documents, decide) | program staff/head |
| Staff | `scholars/`, `scholars/<award>/`, `scholars/import/`, `scholars/export/`, `terms/` (rollover) | program staff/head |
| Staff | `schedules/`, `disbursements/`, `disbursements/<schedule>/`, `budget/` | program staff/head (see §6) |
| Staff | `reports/`, `tasks/`, `settings/` (tiers, documents, rules, window) | staff; `settings/` is head only |
| Office | `/office/` (dashboard), `programs/`, `staff/`, `scholars/`, `reports/`, `analytics/`, `audit/`, `schools/`, `terms/` | super admin |
| Files | `POST /files/uploads/` (intent), `POST /files/uploads/<id>/confirm/`, `GET /files/<id>/` (authorize → 302) | owner or authorized staff |
| Cron | `/_cron/send-outbox/`, `/_cron/cleanup/` | `Authorization: Bearer $CRON_SECRET` |
| Django admin | `/_admin/` | technical superuser only |

## 6. Authorization
- **Roles:** `User.role` decides which area a user can enter. Staff powers come from `ProgramMembership`, and a super
  admin can do everything in `/office/` and act in any program.
- **Mixins and decorators:**
  - `StudentRequiredMixin`, `ProgramStaffRequiredMixin(level=staff|head)`, `SuperAdminRequiredMixin`;
  - object access always goes through a scoped selector (e.g. `applications_for_program(program)`), never through a
    bare `Model.objects.get(pk=…)`.
- **Proposed head vs staff split** (open question §18):

| Capability | Student | Staff | Head | Super admin |
|---|---|---|---|---|
| Own profile, applications, scholarships | ✓ | — | — | view |
| Review applications and documents, return/approve/reject | — | ✓ | ✓ | ✓ |
| Create applications or scholars on a student's behalf, import | — | ✓ | ✓ | ✓ |
| Edit scholars, terms, merit confirmation | — | ✓ | ✓ | ✓ |
| Generate and approve disbursements | — | prepare | approve | ✓ |
| Release and revert disbursements (reauth) | — | — | ✓ | ✓ |
| Schedules (create/publish) | — | ✓ | ✓ | ✓ |
| Program settings: tiers, documents, rules, window, budget | — | — | ✓ | ✓ |
| Programs, staff accounts, memberships, schools, terms | — | — | — | ✓ |
| Audit log | — | — | own program | all |

- **Permission-matrix test:** `tests/test_permission_matrix.py` enumerates `get_resolver()` and checks each URL name
  against an expected-access table for anonymous, student, other-student, staff, other-program staff, head and super
  admin. A new URL fails the test until it's added to the table.

## 7. Files
- **Constraints:**
  - Vercel caps request and response bodies at 4.5 MB, and functions have no persistent disk.
  - Files therefore never pass through Django; they go straight to a private R2 bucket.
- **Upload flow:**
  1. **Intent:** the browser calls `POST /files/uploads/` with purpose, name, declared type and size. The service checks
     the purpose's allowlist (PDF, JPEG, PNG; never SVG or HTML) and its size limit. It then creates a
     `StoredFile(status=pending)` and returns a presigned PUT for `pending/<uuid>` that signs `ContentType` and
     `ContentLength`.
  2. **Upload:** `upload.ts` PUTs the file straight to R2, with a progress bar.
  3. **Confirm:** the browser calls `POST /files/uploads/<id>/confirm/`. The server issues a HEAD (checking the size) and
     a ranged GET of the first 4 KB to sniff the type with `filetype`. On a mismatch the file is `rejected`.
     - Photos are re-encoded with Pillow to strip EXIF.
     - The object is copied to `files/<purpose>/<uuid>`, and the pending object is deleted.
     - The file becomes `ready`, with its sha256 recorded.
  4. **Housekeeping:** a 1-day lifecycle rule on `pending/` deletes abandoned uploads.
- **Download:** `GET /files/<id>/` checks access (owner, or staff of the owning program), writes an `AuditEvent`
  (`file.viewed`), and 302s to a presigned GET valid for 5 minutes with
  `ResponseContentDisposition=attachment; filename=…` and the sniffed `ResponseContentType`. Files are never served
  inline from the app origin.
- **Exports:** a CSV/XLSX export over 4.5 MB is written to R2 under `exports/`, and the browser is redirected to it.
- **Bucket:** private; CORS allows PUT and GET from the app's origins only; encryption at rest is R2's default.

## 8. Matching
- **Eligibility, deterministic** (`matching.eligibility.evaluate(profile, program, academic)`):
  - returns `EligibilityResult(eligible, reasons: list[str], tier_candidates, merit_likely)`;
  - checks the application window, residency years, voter registration, school/type allowlist, minimum units, and GWA
    against the scale-aware threshold;
  - every failed check adds a human-readable reason;
  - this is the only thing that gates applying.
- **Model hint, advisory** (`matching.legacy_model.suggest(...)`):
  - It is a pure-Python port of v1's pickle. `scripts/export_legacy_model.py`, run once in a throwaway sklearn 1.6.1
    environment, exports the scaler means/scales, one-hot categories, coefficients, intercepts and classes to
    `apps/matching/data/legacy_tier_model.json`. Inference is the same transform followed by a softmax.
  - **Inputs:**
    - `grade = clamp(1 + (gwa_percent − 70) × 0.1, 1, 4)`; only shown when a percent GWA exists;
    - `income`, now actually collected; its units are undocumented, and the hint is labelled as such;
    - the exact school name;
    - school type public/private, with SUC and LCU mapped to public.
  - **Output:** a suggested program plus merit (`CEAA_Merit`, …, `NotEligible`) and a probability. It never suggests a
    LANI tier.
  - **Parity test:** about 30 fixture vectors, including unknown schools and edge grades, generated by the export
    script with sklearn's own `predict_proba`. The port must match within 1e-9.
- **Match page:** `/me/match/` lists every active program with ✓/✗, the reasons, the tier candidates, and the hint
  ("Suggested by the legacy model; advisory"). The student applies only to eligible programs and requests a tier; staff
  confirm the tier on approval. The result is saved in `Application.match_snapshot` at submit time.

## 9. Email, notifications, cron
- **Sending email:**
  - `workspace.services.notify(user, kind, …)` creates a `Notification` and, when emailed, an `EmailOutbox` row.
  - `transaction.on_commit` tries the send through anymail (Resend) with a 5-second timeout. On failure the row is
    `failed`, with `last_error` set.
  - Batch actions (bulk approvals, disbursements) send one anymail batch call with `merge_data`.
- **Templates:** `templates/emails/<kind>.{html,txt}`, autoescaped.
  - v1 messages to port: application received, application decided, allowance approved/released, password reset (from
    allauth).
  - New: invite/claim, document declined, application returned.
- **Cron** (`vercel.json` crons; Hobby allows once per day, ±1 hour, production only):
  - `/_cron/send-outbox/` retries `failed` rows, up to 5 attempts;
  - `/_cron/cleanup/` runs `clearsessions`, deletes expired invites, and purges `sent` outbox rows older than 90 days.
- **Scope:** both cron endpoints are idempotent and require `CRON_SECRET`. Anything more frequent needs Vercel Pro or the
  fallback host.

## 10. Security and privacy
- **Authentication:**
  - allauth with email as the login and `ACCOUNT_EMAIL_VERIFICATION="mandatory"`;
  - Google OIDC links to the account only when the Google email is verified;
  - allauth rate limits (Django database cache, via `createcachetable`);
  - reauthentication before revert/release, membership and role changes, and program money settings;
  - Argon2 first in `PASSWORD_HASHERS`; validators: minimum length 10, common, numeric, similarity.
- **Sessions:**
  - database-backed; `Secure`, `HttpOnly`, `SameSite=Lax`; 12-hour age;
  - logout is POST only.
- **CSRF and redirects:**
  - Django CSRF on every form; HTMX sends `X-CSRFToken` through `hx-headers` on `<body>`;
  - redirects are validated with `url_has_allowed_host_and_scheme`.
- **Headers:**
  - HSTS: 1 year, includeSubDomains; preload after launch;
  - `nosniff`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin`, a strict `Permissions-Policy`.
- **CSP:**
  - `default-src 'self'`; `script-src 'self'`; `style-src 'self'`;
  - `img-src 'self' data: <r2-origin>`; `connect-src 'self' <r2-origin> <sentry-ingest>`;
  - `frame-ancestors 'none'`; `form-action 'self'`;
  - htmx config: `allowEval: false`, `includeIndicatorStyles: false`; no `hx-on`, no inline scripts or styles.
- **Errors:** `DEBUG=False` in every deployment; custom 400/403/404/500 pages; nothing internal reaches the client.
- **Logging:**
  - JSON to stdout, with user IDs but no names, emails or document contents;
  - Sentry's `before_send` scrubs request bodies and cookies.
- **Django admin:** `/_admin/` is limited to `is_superuser` technical accounts, separate from the in-app super admin.
- **Dependencies:** `pip-audit` (on `uv export`) and `npm audit` in CI; Dependabot.
- **RA 10173 (Data Privacy Act):**
  - a privacy notice and a consent record;
  - collect only what eligibility needs;
  - program-scoped access, with an audit of every document view;
  - a private bucket;
  - previews never hold production data (§11);
  - a retention period (open question);
  - "download my data" and account-deletion requests, handled by the office in v2.0.

## 11. Vercel deployment
- **Detection:** Vercel's zero-config Django support detects `manage.py` and runs `WSGI_APPLICATION`. One function
  serves every route.
- **Region:** `"regions": ["sin1"]`, next to Neon `aws-ap-southeast-1`.
- **Limits that shape the design:**
  - request/response bodies ≤ 4.5 MB (handled in §7);
  - function bundle ≤ 500 MB (we stay small: no numpy, pandas or sklearn; boto3 is imported lazily);
  - duration ≤ 300 s on Hobby;
  - no persistent disk;
  - Hobby is for non-commercial use only (open question).
- **Static files:**
  - The build runs `npm --prefix frontend ci && npm --prefix frontend run build` (Vite → `static/dist/` +
    `manifest.json`).
  - Vercel then runs `collectstatic` (`STATIC_ROOT` set; WhiteNoise `CompressedManifestStaticFilesStorage`) and serves
    `/static/` from the CDN.
  - The Vite manifest is also added to the function bundle (`includeFiles`), so django-vite can resolve it at runtime.
  - **M1 proves this order.**
- **Database settings:**
  - `DATABASE_URL` is Neon's pooled (PgBouncer, transaction mode) URL.
  - `CONN_MAX_AGE=0`, `CONN_HEALTH_CHECKS=True`, `DISABLE_SERVER_SIDE_CURSORS=True`.
  - No session-level features: no advisory locks, no `LISTEN`, no Django connection pool.
- **Migrations:**
  - run in the build: `migrate --noinput` and `createcachetable`, against `DATABASE_URL_UNPOOLED`;
  - Instant Rollback does **not** undo migrations, so every migration is expand/contract: add nullable → backfill →
    enforce → remove in a later deploy.
- **Previews:**
  - The Neon integration gives each preview deployment its own branch, forked from a **`preview-base` branch seeded with
    Faker data, never from production**.
  - Deployment Protection is on.
  - Google sign-in works only on the production domain and a fixed staging alias, which are the registered redirect
    URIs.
- **Proxy settings:**
  - `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`;
  - `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` built from `VERCEL_URL`, `VERCEL_BRANCH_URL`,
    `VERCEL_PROJECT_PRODUCTION_URL` and the custom domain;
  - allauth reads the client IP from the forwarded header, with a trusted-proxy count, so rate limits key on the real
    client.
- **Production gating:** production deploys only after CI passes. Either Vercel deployment checks are gated on the CI
  workflow, or a CI job runs `vercel build` then `vercel deploy --prebuilt --prod`. M1 picks one. Kenneth pushes; nothing
  deploys on its own.
- **Fallback:** if M1 fails a must-pass check, the same app ships as a Docker image (gunicorn) on Fly.io or Render in
  Singapore. The code doesn't change, because §7 and §9 already assume no disk and no workers.

## 12. Frontend
- **Brand,** kept from v1 and tidied:
  - logo: the graduation-cap outline (`static/images/favicon.svg` in v1) plus the "ScholarSync" wordmark;
  - visual style: white cards, a red accent, stat tiles with soft icon chips, rounded status pills.
- **Tokens** (`frontend/src/styles/tokens.css`):
  - **Brand red:** `--brand-600: #d10e0f` is used for text, buttons and links (5.6:1 on white, AA). `--brand-500:
    #fd1415` is decorative only (4.0:1, fails AA for text). `--brand-400: #ff4546`.
  - **Gold accent:** `--accent: #ebbf56`, decorative.
  - **Info:** `--info: #27488b`.
  - **Neutrals:** `#111827` → `#f9fafb`.
  - **Status:** success `#047857`, warning `#b45309`, danger `--brand-600`. Text on tints is always AA.
  - **Type:** Poppins 600/700 for headings, Inter 400/500/600 for body.
  - **Scales:** 4 px spacing scale, radius scale, two shadows.
  - Light theme in v2.0; tokens are named so a dark theme can be added later.
- **Components** (`templates/components/` + CSS):
  - controls: button (primary, secondary, ghost, danger), field (label, help, error), select, file input with progress;
  - data: table (sortable header, pagination, row selection + bulk bar), filter bar, stat tile, card, status pill,
    tabs;
  - overlays and feedback: dialog, toast, empty state;
  - navigation: breadcrumbs, top nav, sidebar with program switcher.
- **Layouts:** public, auth (split panel, as in v1), student (top nav), staff (sidebar + program switcher), office
  (sidebar).
- **HTMX patterns:**
  - filters use `hx-get` + `hx-push-url` and swap a `{% partialdef table %}`;
  - forms use `hx-post`: re-render the form partial on error, `HX-Redirect` or `HX-Trigger` on success;
  - dialogs load content into `<dialog>`, and `dialog.ts` opens them;
  - toasts come from `HX-Trigger: {"toast": …}`, read by `toast.ts` into an `aria-live` region;
  - bulk actions are a form with checkboxes;
  - every form also works as a normal POST without JS.
- **TypeScript modules:**
  - `main.ts`: imports and configures htmx;
  - `dialog.ts`, `toast.ts`, `upload.ts` (presigned PUT + confirm), `bulk.ts` (select-all, count);
  - `charts.ts`: a dynamic import of Chart.js that reads `{{ data|json_script }}`.
- **Budget:** JS + CSS ≤ 100 KB gzipped, excluding the lazy chart chunk and fonts. CI checks it.
- **Accessibility:**
  - target WCAG 2.2 AA;
  - landmarks, one `h1`, a skip link, visible focus;
  - every input labelled; 44 px touch targets;
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
- **End to end:** pytest-playwright from M4:
  - sign up → verify → profile → match → apply;
  - staff review → approve → award;
  - disbursement generate → approve → release;
  - office creates a program and a staff member.
- **Test data:** factory_boy + Faker `en_PH` only; time-machine for terms, windows and fiscal years.
- **Coverage:** at least 90% on `services`, `selectors` and `matching`; at least 80% overall.

## 14. Settings and environment variables (names only)
- **Core:** `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `SITE_URL`.
- **Database:** `DATABASE_URL`, `DATABASE_URL_UNPOOLED`.
- **Files:** `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_ENDPOINT_URL`.
- **Email:** `RESEND_API_KEY`, `DEFAULT_FROM_EMAIL`.
- **Google sign-in:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.
- **Ops:** `SENTRY_DSN`, `CRON_SECRET`, `CSP_REPORT_ONLY`.
- **Set by Vercel:** `VERCEL_ENV`, `VERCEL_URL`, `VERCEL_BRANCH_URL`, `VERCEL_PROJECT_PRODUCTION_URL`.
- **Rules:**
  - `.env.example` documents every variable, with no values.
  - Startup fails fast on a missing required variable outside `DEBUG`. No insecure fallbacks, ever: v1's
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
- **e2e** (from M4): build, run the server, `pytest --browser chromium tests/e2e`.
- **deploy:** see §11, "Production gating".

## 16. Milestones
Each milestone gets its own implementation plan in `docs/superpowers/plans/` (TDD, one commit per task) before work
starts, and ends with every acceptance item checked.

**M0: Planning docs**
- [ ] `CLAUDE.md`, `docs/legacy-audit.md`, this spec and `README.md` committed; `CLAUDE.local.md` and `STATE.md`
  local.
- [ ] Spec approved by Kenneth.

**M1: Vercel go/no-go spike** (throwaway branch `spike/vercel`; results go into `STATE.md` → Spike results)
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
- [ ] CI green; `vercel.json` (region, function config, crons).

**M3: Design system**
- [ ] Tokens, fonts, icons, components and layouts (§12); `/_kit` page shows every component in every state
  (development only).
- [ ] Key-screen mockups (student dashboard, apply, staff application review, disbursements, office dashboard)
  **approved by Kenneth** (gate).

**M4: Accounts, email, minimal Program**
- [ ] Custom `User`, allauth (verification, Google, reset, rate limits, reauth), roles; signup only ever makes students.
- [ ] Minimal `Program` + `ProgramMembership`; scoping mixins; permission-matrix test.
- [ ] `EmailOutbox` + anymail + send-outbox cron; privacy notice + `ConsentRecord`.
- [ ] `seed_programs`, `create_office_admin`, `seed_demo`; first Playwright flow.

**M5: Files**
- [ ] `StoredFile` intent → PUT → confirm → final; allowlists; sniffing; EXIF strip; attachment downloads with audit;
  `upload.ts`; MinIO locally, R2 in deployments.

**M6: Reference data + student profile**
- [ ] Full `Program` config, `BenefitTier` (effective-from), `RequiredDocument`, `School`, `AcademicTerm`.
- [ ] Profile sections, photo, completion tracker; staff-created profiles + invite/claim.

**M7: Matching + student applications**
- [ ] Eligibility engine; exported legacy model + parity test; `/me/match/`.
- [ ] Apply flow (documents, submit, withdraw, returned → resubmit); status page; emails.

**M8: Application review**
- [ ] Staff queue (filters, sorting, pagination), review screen, document approve/decline, return, approve → `Award` +
  first `ScholarTerm`, reject, bulk, on-behalf applications.

**M9: Scholars, terms and renewals**
- [ ] Scholar list and detail, edit, status changes, `ScholarTerm` history, merit by rule + confirmation, at-risk
  selector.
- [ ] Renewal applications, term rollover + graduation, CSV/XLSX import with preview, CSV/XLSX export.

**M10: Money**
- [ ] Schedules (publish); disbursement generation from tiers; approve/reject/release/revert (reauth); batch; budget,
  spent, committed, utilization; student distribution view; emails.

**M11: Dashboards + office**
- [ ] Staff dashboards (stats, trends, at-risk, tasks); office: programs CRUD, staff + memberships, schools, terms,
  cross-program scholars, reports review, analytics (trends, success rate, approval time, top feeder school), audit
  viewer; notifications center; support form.

**M12: Hardening + launch**
- [ ] Security review (OWASP ASVS L2 checklist), CSP enforced, headers, `check --deploy` clean.
- [ ] WCAG 2.2 AA audit; query budgets; Playwright suite green; help, FAQ, privacy and terms pages.
- [ ] Production: Vercel project, Neon production + `preview-base`, R2 bucket + lifecycle + CORS, Resend domain, Google
  OAuth client, Sentry, domain.
- [ ] Backups (Neon point-in-time restore) and a runbook (deploy, rollback, restore, rotate secrets).

## 17. Risks
| Risk | Mitigation |
|---|---|
| Vercel's build order (Vite → collectstatic → migrate) or Django support doesn't behave as documented | M1 spike before any feature work; fallback to Docker on Fly.io/Render |
| Real PII leaks into preview databases | Previews branch from a seeded `preview-base`, never production; Deployment Protection |
| A bad migration can't be rolled back with Instant Rollback | Expand/contract migrations only; Neon point-in-time restore |
| 4.5 MB body limit | Direct-to-R2 uploads and exports (§7) |
| Hobby limits: non-commercial use, daily cron, 1-hour logs | Pro plan for a City deployment (open question); Sentry for errors; outbox retries |
| Rate limits key on the proxy IP | Trusted forwarded-header configuration, verified in M1 |
| The legacy model is a toy trained on unknown data | Advisory only, clearly labelled; rules decide; retire or retrain when real data exists |
| Business rules are still unclear (amounts, LANI tier criteria, at-risk) | Rules are data, editable by heads; open questions tracked in `STATE.md` |

## 18. Open questions (also tracked in `STATE.md`)
1. **URGENT (Kenneth):** rotate or revoke the leaked v1 secrets, delete the Aiven database, and make the legacy repo
   private or purge it (`docs/legacy-audit.md` §8).
2. Confirm the benefit amounts per program and tier.
3. What qualifies a student for each LANI tier (honors, premier, priority, basic plus, basic, SUC/LCU, review, lead)?
4. Renewal criteria: is CEAA's "GWA ≥ 80%, ≥ 15 units" right? What scale is LANI's "SWA not lower than 2.5" on?
5. Definition of at-risk.
6. Can one student hold CEAA and LANI at the same time?
7. Head vs staff powers (§6 proposal).
8. Maximum terms per program; graduation rules.
9. Budget figures; confirm the City fiscal year (January–December) as the budget period.
10. RA 10173 retention period for documents and closed records.
11. Can staff create student accounts, or only profiles that students claim?
12. Vercel plan: Hobby is non-commercial only; a real City deployment needs Pro.
13. Domain: reuse `scholarsync.site`? Which sender domain for email?
14. Is v1 still used by the City, and is there a cut-over date?

## 19. Decisions (2026-10-11 → 2026-10-12)
| Decision | Why |
|---|---|
| Rewrite in a new private repo (`ScholarSyncV2`); legacy stays a read-only reference | v1's structure can't be fixed incrementally |
| Django 5.2 LTS | Kenneth's choice; auth, ORM, migrations, CSRF and forms built in; LTS until April 2028 |
| Fresh start with seed data | Kenneth's choice; no v1 data migration |
| Django templates + HTMX + a little TypeScript | Kenneth's choice; replaces 30 global-JS files with server-rendered partials |
| Host on Vercel | Kenneth's choice; designed around its limits, with an M1 spike and a fallback |
| Rules decide eligibility; the legacy model only advises | Kenneth's choice; auditable decisions for a public benefit |
| Programs are data | Removes the 67–99% CEAA/LANI duplication; new programs need no code |
| `ScholarTerm` per award per term; applications kept after approval | v1 overwrote term data and deleted applications, losing history |
| Cloudflare R2 for files (S3 API via django-storages) | Private, presigned, works with Vercel's django-storages support; swappable |
| Outbox + daily cron instead of background workers | Vercel has no long-running workers; retries without new infrastructure |
| Region `sin1` + Neon Singapore | Users are in Taguig; Vercel's default region is the US |
| `CLAUDE.md` tracked and basic; `CLAUDE.local.md` and `STATE.md` git-ignored | Kenneth's request (2026-10-12) |
| No AI attribution on any commit or PR | Kenneth's non-negotiable (`CLAUDE.local.md`) |
