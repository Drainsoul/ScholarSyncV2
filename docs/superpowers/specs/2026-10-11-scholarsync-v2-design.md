# ScholarSync V2: design spec

- **Revision:** 2 (2026-10-28): M3 design-system details (§3, §12, §13, §14, §15, §16), proposed with the M3 plan.
- **Revision:** 3 (2026-10-28): §12 visual redesign (UI UX Pro Max: Accessible & Ethical + Swiss; Lexend + Source Sans 3;
  navy actions, red brand mark only) after Kenneth's M3 mockup review.
- **Revision:** 4 (2026-10-30): §12 redesign on Kenneth's canvas (red primary, blue secondary, yellow accent; white
  sidebar shell; cards; status as coloured text). Boards in `docs/design/2026-10-30-redesign/`.
- **Revision:** 5 (2026-10-30): open source and self-hosting. Vercel is no longer the deployment target; the app runs
  from one `docker compose up` and on any container host with any provider (§1, §2, §5, §7, §9, §11, §14-§19, new
  M3.5). Design: `docs/superpowers/specs/2026-10-30-open-source-self-hosting-design.md`.
- **Status:** rev 1 approved by Kenneth on 2026-10-12. M1 plan: `docs/superpowers/plans/2026-10-12-m1-vercel-spike.md`.
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
7. **Runs anywhere a container runs, with a one-command local run** (§11): any PostgreSQL, any S3-compatible storage,
   any email service. Open source (MIT); nobody hosts an official copy.

**Non-goals (v2.0)**
- Migrating v1 data: this is a fresh start with seed data.
- A public JSON API or SPA, a native mobile app, SMS, or payments integration (disbursement is recorded, not paid
  out).
- Real-time features (WebSockets), dark theme, multi-language UI (English only; Filipino later).
- Retraining the legacy model.
- Kenneth hosting a public demo or production instance; a packaged desktop app; one-click deploy buttons for specific
  hosts; documenting a hosting path without Docker; branding through settings (rebranding is fork-and-edit); a
  published container image or release pipeline.

## 2. Stack
Versions are pinned to the latest stable release when M2 scaffolds the project, then recorded in `STATE.md`.

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
| Import/export | stdlib `csv`, **openpyxl** | Row-by-row Django Forms with a preview |
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
  - fields: `key` (object-store key), `status` ∈ {pending, ready, rejected}, `original_name`, `declared_type`,
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
| Public | `/`, `/programs/`, `/programs/<slug>/`, `/about/`, `/help/`, `/privacy/`, `/terms/`, `/cookies/`, `/contact/` (the six information pages; footer disclaimer in §11) | anyone |
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
  - The app is stateless: no persistent local disk, and large bodies stay out of it.
  - Files therefore never pass through Django; they go straight to a private bucket on any S3-compatible service. The
    design works on every host.
- **Upload flow:**
  1. **Intent:** the browser calls `POST /files/uploads/` with purpose, name, declared type and size. The service checks
     the purpose's allowlist (PDF, JPEG, PNG; never SVG or HTML) and its size limit. It then creates a
     `StoredFile(status=pending)` and returns a presigned PUT for `pending/<uuid>` that signs `ContentType` and
     `ContentLength`.
  2. **Upload:** `upload.ts` PUTs the file straight to the bucket, with a progress bar.
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
- **Exports:** large CSV/XLSX exports are written to the bucket under `exports/` and the browser is redirected to them
  (the size threshold is the builder's call).
- **Bucket:** private; CORS allows PUT and GET from the app's origins only; encryption at rest is the provider's.
- **Public endpoint:** presigned URLs must point at an address the browser can reach. An optional public endpoint
  setting covers the case where the app reaches storage by an internal name (inside compose); CSP `connect-src` and
  `img-src` include the storage origin from settings.

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

## 9. Email, notifications, background jobs
- **Sending email:**
  - `workspace.services.notify(user, kind, …)` creates a `Notification` and, when emailed, an `EmailOutbox` row.
  - `transaction.on_commit` tries the send through the configured SMTP transport with a 5-second timeout. On failure the row is
    `failed`, with `last_error` set.
  - Batch actions (bulk approvals, disbursements) send one batched call over the same transport.
- **Templates:** `templates/emails/<kind>.{html,txt}`, autoescaped.
  - v1 messages to port: application received, application decided, allowance approved/released, password reset (from
    allauth).
  - New: invite/claim, document declined, application returned.
- **Background jobs:** two management commands, run on a loop by the `worker` service (or from any cron or scheduler):
  - `send_outbox` retries `failed` rows, up to 5 attempts;
  - `cleanup` runs `clearsessions`, deletes expired invites, and purges `sent` outbox rows older than 90 days.
- **Scope:** both commands are idempotent. There are no HTTP cron endpoints and no `CRON_SECRET`.

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
  - `img-src 'self' data: <storage-origin>`; `connect-src 'self' <storage-origin> <sentry-ingest>`;
  - `frame-ancestors 'none'`; `form-action 'self'`;
  - htmx config (a `<meta name="htmx-config">`): `allowEval: false`, `allowScriptTags: false`,
    `includeIndicatorStyles: false`, `selfRequestsOnly: true`, and `historyCacheSize: 0` so page snapshots holding
    personal data never land in `localStorage`; no `hx-on`, no inline scripts or styles.
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
  - a retention period (open question);
  - "download my data" and account-deletion requests, handled by the office in v2.0.

## 11. Running and hosting
Summary of `docs/superpowers/specs/2026-10-30-open-source-self-hosting-design.md` §4-§8, which is the detail.
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
- **Design direction (rev 4, 2026-10-30):** Kenneth asked for a redesign on the layout of a Dribbble admin
  dashboard ("Cark: User management platform"), with red as the main colour, blue second and yellow third, using the
  UI UX Pro Max skill. He reviewed and edited the result on a design canvas; its boards are kept in
  `docs/design/2026-10-30-redesign/` and are the visual reference for this section. Rev 4 replaces rev 3's
  navy-led, unboxed look. Kenneth's rulings from the canvas review:
  - one plain box of figures (label + number), no icons, captions or progress bars in it;
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
  - **type:** Lexend 600/700 headings, Source Sans 3 400/600/700 body at 16 px, line height 1.5, tabular figures for
    money; captions and table headers 13 px;
  - **shape:** radius 8 px (controls, buttons, nav items), 10 px (small blocks), 12 px (cards, figures box, drawer
    edges); pills (999 px) only for counts; shadows only on floating layers (drawer, dialog, toast, menus).
  - Light theme in v2.0; tokens are role-named so a dark theme can be added later.
- **Components** (`templates/components/` + CSS):
  - **buttons:** 44 px tall, radius 8. Primary = solid red; secondary = white with a `#d0d5dd` border; soft = blue
    tint with a blue border; ghost = no border, hover tint; danger = white, outlined in `#9b1022`. Icons only where
    they carry meaning (download, add, mail, close, menu, sign out, pause);
  - **cards:** white, 1 px border, radius 12, a title row with an optional link on the right. Page sections are
    cards on the grey ground; a card never sits inside another card;
  - **figures:** one bordered box of label + Lexend number cells divided by 1 px rules; cells wrap on narrow
    screens;
  - **status:** bold text in its tone colour (`.status--success` etc.), no background; **counts:** small pills (nav
    counts in yellow with ink text, tab counts grey or red tint on the current tab);
  - **avatars:** initials in a circle, tinted red, blue or yellow by position;
  - **table:** 13 px bold muted headers on `#fafafb`, 1 px row rules, row hover, numbers right-aligned in tabular
    figures; toolbar of search + filter selects above; numbered pagination with the current page in red;
  - **tabs:** bold text with a 3 px red underline on the current tab and a count pill;
  - **drawer:** a slide-over detail panel (white, left border, shadow) opened by a link, so a list keeps its place;
    server-rendered, closed by a link;
  - **progress:** 8 px rounded bar on `#eef0f3`;
  - **row links:** whole-row links for task lists (no underline; hover background, underlined title, arrow);
  - **banners:** tinted box with radius 12 and an icon for warning and danger; **feedback:** dialog, toast, empty
    state as before.
- **Layouts:**
  - **app shell (staff, office, student):** a white 248 px sidebar (stripe, brand, a context block, grouped nav with
    an icon per item and counts, an optional callout, a user card with the account menu and sign out at the bottom)
    beside a column with a white top bar (search for staff and office, term chooser, notifications) and the page on
    the grey ground. The context block is the program switcher for staff and "Scholarship office" for the office.
    The current nav item has a red tint and red text;
  - **public:** a white top bar with the brand and text navigation, the stripe on top, content max 72rem;
  - **auth:** the split panel, now flat red with white text (Claude's call; not on the canvas), the stripe on top;
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
- **Database:** `DATABASE_URL`, `DATABASE_URL_UNPOOLED` (optional).
- **Files (S3-compatible):** `S3_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT_URL` (optional), `S3_REGION`, `S3_BUCKET`,
  `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ADDRESSING_STYLE`.
- **Email:** `EMAIL_URL` (SMTP, URL-style), `DEFAULT_FROM_EMAIL`.
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
Each milestone gets its own implementation plan in `docs/superpowers/plans/` (TDD, one commit per task) before work
starts, and ends with every acceptance item checked.

**M0: Planning docs**
- [ ] `CLAUDE.md`, `docs/legacy-audit.md`, this spec and `README.md` committed; `CLAUDE.local.md` and `STATE.md`
  local.
- [ ] Spec approved by Kenneth.

**M1: Vercel go/no-go spike** (historical, superseded by revision 5; throwaway branch `spike/vercel`, kept local; results are in `STATE.md` → Spike results)
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
  **approved by Kenneth** (gate).

**M3c: Redesign (rev 4)**
- [ ] Tokens, components, the white-sidebar app shell (staff, office, student), public and auth layouts, and every
  kit mockup restyled to `docs/design/2026-10-30-redesign/`; a new Scholars mockup with the drawer; full gate green.

**M3.5: Open-source packaging** (plan: `docs/superpowers/plans/2026-10-30-m3-5-open-source-packaging.md`; before M4)
- [ ] Task 1: this spec revision (rev 5).
- [ ] Task 2: modes in settings (developer, explore, production); the kit refused in production mode.
- [ ] Task 3: Vercel removed (`vercel.json`, `build.py`, host detection, `VERCEL_ENV` checks).
- [ ] Task 4: the `apps/demo/` skeleton, its optional hook and the failing deploy check.
- [ ] Task 5: runtime commands (`send_outbox`, `cleanup`, worker loop, entrypoint).
- [ ] Task 6: provider-neutral settings, `.env.example`, `Dockerfile`, `compose.yaml`, `compose.production.yaml`.
- [ ] Task 7: CI jobs (hosting-path, compose smoke).
- [ ] Task 8: README, `docs/SETUP.md`, `docs/HOSTING.md`; `CLAUDE.md` updated.
- [ ] Task 9: `/about/`, `/privacy/`, `/terms/`, `/cookies/`, `/help/`, `/contact/`, the footer disclaimer, the two
  operator settings, `SECURITY.md`.
- [ ] Task 10 (optional): GitHub Codespaces.
- [ ] Task 11: publication (history scan, document review, Vercel/Neon/R2 teardown, repository made public).
- [ ] `docker compose up` shows the existing pages; deleting `apps/demo/` leaves the full suite and `check --deploy`
  green.

**M4: Accounts, email, minimal Program**
- [ ] Custom `User`, allauth (verification, Google, reset, rate limits, reauth), roles; signup only ever makes students.
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

**M6: Reference data + student profile**
- [ ] Full `Program` config, `BenefitTier` (effective-from), `RequiredDocument`, `School`, `AcademicTerm`.
- [ ] Profile sections, photo, completion tracker; staff-created profiles + invite/claim.
- [ ] Extend the demo loader for this milestone's screens.

**M7: Matching + student applications**
- [ ] Eligibility engine; exported legacy model + parity test; `/me/match/`.
- [ ] Apply flow (documents, submit, withdraw, returned → resubmit); status page; emails.
- [ ] Extend the demo loader for this milestone's screens.

**M8: Application review**
- [ ] Staff queue (filters, sorting, pagination), review screen, document approve/decline, return, approve → `Award` +
  first `ScholarTerm`, reject, bulk, on-behalf applications.
- [ ] Extend the demo loader for this milestone's screens.

**M9: Scholars, terms and renewals**
- [ ] Scholar list and detail, edit, status changes, `ScholarTerm` history, merit by rule + confirmation, at-risk
  selector.
- [ ] Renewal applications, term rollover + graduation, CSV/XLSX import with preview, CSV/XLSX export.
- [ ] Extend the demo loader for this milestone's screens.

**M10: Money**
- [ ] Schedules (publish); disbursement generation from tiers; approve/reject/release/revert (reauth); batch; budget,
  spent, committed, utilization; student distribution view; emails.
- [ ] Extend the demo loader for this milestone's screens.

**M11: Dashboards + office**
- [ ] Staff dashboards (stats, trends, at-risk, tasks); office: programs CRUD, staff + memberships, schools, terms,
  cross-program scholars, reports review, analytics (trends, success rate, approval time, top feeder school), audit
  viewer; notifications center; support form.
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
| A secret in git history or a document not meant for the public becomes visible when the repo opens | Scan the full history and review every tracked document before publishing (M3.5 Task 11); rotate, then rewrite history if needed |
| A forgotten `apps/demo/` (published test passwords) in a real deployment | Demo inactive in production mode, and `check --deploy` fails while the folder exists |
| Explore mode exposed beyond the visitor's machine | Ports bound to `127.0.0.1`; settings refuse explore mode with any other host |
| A bad migration can't be rolled back | Expand/contract migrations only; database backups |
| Large bodies reach the app | Direct-to-bucket uploads and exports (§7) |
| Presigned URLs signed for an internal hostname fail in the browser | A public storage endpoint setting; round trip covered by the compose smoke from M5 |
| Rate limits key on the proxy IP | Trusted forwarded-header configuration with a proxy count (§11) |
| The S3-compatible container's image or licence changes | Code speaks only the S3 API; swapping the image is a compose change |
| The legacy model is a toy trained on unknown data | Advisory only, clearly labelled; rules decide; retire or retrain when real data exists |
| Business rules are still unclear (amounts, LANI tier criteria, at-risk) | Rules are data, editable by heads; open questions tracked in `STATE.md` |

## 18. Open questions (also tracked in `STATE.md`)
1. ~~Leaked v1 secrets~~ Resolved 2026-10-12: Kenneth confirmed every v1 key had already been rotated.
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
12. ~~Vercel plan~~ Obsolete (revision 5): nobody hosts an official copy.
13. ~~Domain and sender domain~~ Obsolete (revision 5): each self-hoster chooses their own.
14. Is v1 still used by the City, and is there a cut-over date?

## 19. Decisions (2026-10-11 → 2026-10-30)
| Decision | Why |
|---|---|
| Rewrite in a new private repo (`ScholarSyncV2`); legacy stays a read-only reference | v1's structure can't be fixed incrementally |
| Django 5.2 LTS | Kenneth's choice; auth, ORM, migrations, CSRF and forms built in; LTS until April 2028 |
| Fresh start with seed data | Kenneth's choice; no v1 data migration |
| Django templates + HTMX + a little TypeScript | Kenneth's choice; replaces 30 global-JS files with server-rendered partials |
| Host on Vercel (superseded 2026-10-30 by the open-source decision below) | Kenneth's choice; designed around its limits, with an M1 spike and a fallback |
| Rules decide eligibility; the legacy model only advises | Kenneth's choice; auditable decisions for a public benefit |
| Programs are data | Removes the 67–99% CEAA/LANI duplication; new programs need no code |
| `ScholarTerm` per award per term; applications kept after approval | v1 overwrote term data and deleted applications, losing history |
| S3-compatible storage for files (R2 was the first choice) | Private, presigned, swappable; any provider works since revision 5 |
| Outbox + a small worker loop instead of Celery (was daily cron on Vercel) | Retries without a broker or new infrastructure |
| Region `sin1` + Neon Singapore (historical, M1 spike only) | Users are in Taguig; no longer a target |
| `CLAUDE.md` tracked and basic; `CLAUDE.local.md` and `STATE.md` git-ignored | Kenneth's request (2026-10-12) |
| No AI attribution on any commit or PR | Kenneth's non-negotiable (`CLAUDE.local.md`) |
| Redesign rev 4: red primary, blue secondary, yellow accent; Cark-style white sidebar shell (2026-10-30) | Kenneth's choice after reviewing and editing the design canvas |
| Open source, one-command run, provider-neutral self-hosting; Vercel dropped (2026-10-30, revision 5) | Kenneth's portfolio project: nobody hosts an official copy, visitors run it on localhost with test accounts, self-hosters bring their own providers. Design: `docs/superpowers/specs/2026-10-30-open-source-self-hosting-design.md` |
| Public information pages and a not-affiliated footer disclaimer (2026-10-30) | The repo is public and anyone can host it; the pages say it isn't an official City service, what happens to data, and who is responsible |
