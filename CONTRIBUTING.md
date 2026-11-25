# Contributing to ScholarSync V2

Thanks for your interest. This guide covers what you need to change the code: the stack, where things live, the
commands, and the conventions every change follows. To just run the app, see the [README](README.md); for running it
locally in depth, see [docs/SETUP.md](docs/SETUP.md). To report a security problem, follow [SECURITY.md](SECURITY.md)
instead of opening an issue.

## The project
ScholarSync V2 is a ground-up Django rewrite of ScholarSync, an independent project modelled on the City of Taguig
scholarship platform (no official affiliation). It has three roles:
- **Students** build a profile, get matched to programs, apply with documents, and track their allowances.
- **Program staff** review applications, manage scholars and terms, and run disbursements.
- **The scholarship office** (super admin) manages programs, staff, reports and analytics.

Programs (TCU CEAA, LANI, and future ones) are **data**, not code.

- **Design spec (source of truth):** [docs/design/2026-10-11-scholarsync-v2-design.md](docs/design/2026-10-11-scholarsync-v2-design.md).
  Changes to the design or architecture go into the spec first, then the code.
- **Open-source and self-hosting design:**
  [docs/design/2026-10-30-open-source-self-hosting-design.md](docs/design/2026-10-30-open-source-self-hosting-design.md).
- **Legacy audit** (v1 features, business rules, problems): [docs/legacy-audit.md](docs/legacy-audit.md).
- **Legacy repository:** ScholarSync v1, private and not needed to work on v2. The legacy audit above records
  everything v2 takes from it (audited at commit `fa9974c`).

## Stack
- **Backend:** Python 3.13 (uv), Django 5.2 LTS, PostgreSQL 17, django-allauth, S3-compatible storage
  (django-storages), SMTP email.
- **Front end:** Django templates + HTMX (django-htmx, django-template-partials); a little strict TypeScript and plain
  CSS tokens built with Vite (django-vite); Biome.
- **Quality:** ruff, mypy + django-stubs, pytest + pytest-django + factory_boy, Playwright.
- **Run and host:** open source; nobody hosts an official copy. `docker compose up` runs explore mode (web, worker,
  db, storage, mail) on localhost; `compose.production.yaml` runs web and worker for self-hosters with their own
  PostgreSQL, S3-compatible storage and SMTP, behind HTTPS ([docs/HOSTING.md](docs/HOSTING.md)). Files go straight to
  storage with presigned URLs; email goes through an outbox. The worker loop runs `send_outbox` (retries failed and
  stale email) and `cleanup` (expired sessions, old outbox rows).
- **Modes:** developer (`DJANGO_DEBUG=true`), explore (`SCHOLARSYNC_EXPLORE=true`, set by `compose.yaml`) and
  production (neither; the fail-closed default). The demo (`apps/demo/`) is active only outside production.

## File structure
```
config/            settings.py (environs), test_settings.py (pytest: forces production security),
                   e2e_settings.py (Playwright: HTTP live server, enforced CSP, kit on), urls.py, wsgi.py
apps/
  accounts/        custom User, roles, allauth adapters
  programs/        Program, BenefitTier, RequiredDocument, School, AcademicTerm, memberships
  students/        StudentProfile, FamilyMember, EducationRecord, ProfileInvite: profile, family, education and photo
                   screens, staff-created profiles with invites, and the claim page
  files/           StoredFile, presigned upload/confirm/download
  applications/    Application, Document, the student apply flow and staff review
  awards/          Award, ScholarTerm, renewals, term rollover
  money/           DistributionSchedule, Disbursement, Budget
  matching/        eligibility rules + advisory legacy-model hint (JSON params)
  reports/         program reports and files
  workspace/       tasks, notifications, email outbox
  office/          scholarship-office (super admin) screens
  demo/            test accounts, sample data, login notice; deleting this folder removes all demo material
  kit/             design kit + key-screen mockups at /_kit/ (no models; DJANGO_KIT)
  core/            AuditEvent, permissions, layouts, health check
  <app>/           models.py services.py selectors.py views.py urls.py forms.py templates/ tests/
templates/         base.html, layouts/ (public, auth, student, app → staff/office), components/, 4xx/500 pages
frontend/          Vite root: src/*.ts, src/styles/*.css + src/styles/components/*.css (builds to static/dist/, git-ignored)
scripts/           one-off tools: export_legacy_model.py (PEP 723, run with `uv run --script`), smoke_signup.sh and
                   smoke_upload.sh (the compose smoke test's signup/email check and upload round trip)
tests/             cross-app tests (permission matrix), tests/e2e/ (Playwright)
docs/              SETUP.md, HOSTING.md, legacy-audit.md, design/ (specs and design boards), security/, accessibility/
docker/            entrypoint.sh (prepare, then exec), healthcheck.py
Dockerfile         two stages: Vite bundle, then the Python app (no Node on the host)
compose.yaml       explore mode: web, worker, db, storage, storage-init, mail
compose.production.yaml  web + worker only; reads .env; forces production mode
manage.py  pyproject.toml  uv.lock  .env.example
```

## Commands
Run from the repository root. The examples use `python -m uv`, which works even when `uv` is not on `PATH`; plain
`uv` works too. [docs/SETUP.md](docs/SETUP.md#developer-workflow) explains each step.

- **Setup:**
  - `docker compose up -d --wait db storage storage-init mail` (the supporting services only; PostgreSQL 17 on host
    port **5433**);
  - copy `.env.example` to `.env` (`Copy-Item .env.example .env` in PowerShell, `cp` elsewhere);
  - `python -m uv sync`;
  - the first front-end install runs **inside** `frontend/` (`npm install` there; `npm --prefix frontend install`
    breaks on npm 10);
  - `python -m uv run python manage.py migrate`;
  - `python -m uv run python manage.py load_demo` (the test accounts and sample data; safe to re-run).
- **Run:** `python -m uv run python manage.py runserver` with `npm --prefix frontend run dev`
  (`VITE_DEV_MODE=true`), or build once with `npm --prefix frontend run build`.
- **Explore run:** `docker compose up` (app on 8000, Mailpit on 8025; ports via `APP_PORT`, `MAIL_PORT`, `DB_PORT`,
  `STORAGE_PORT`). `docker compose down -v` resets it and also deletes the development database volume.
- **Checks (the same as CI):**
  ```
  python -m uv run ruff check .
  python -m uv run ruff format --check .
  python -m uv run mypy .
  python -m uv run python manage.py makemigrations --check --dry-run
  python -m uv run pytest -n auto
  python -m uv run playwright install chromium   # once
  python -m uv run pytest -m e2e --ds=config.e2e_settings --browser chromium
  npm --prefix frontend run typecheck
  npm --prefix frontend run check
  npm --prefix frontend run build
  npm --prefix frontend run budget
  ```
- **Deploy check (as CI runs it):** `manage.py check --deploy --fail-level WARNING` with `DJANGO_DEBUG=false`,
  `DJANGO_ALLOWED_HOSTS=scholarsync.example` and `DJANGO_ENV_FILE=/nonexistent`, so your local `.env` can't mask a
  missing variable. It fails while `apps/demo/` exists, on purpose; CI's hosting-path job deletes the folder first.
  The exact PowerShell lines are in [docs/SETUP.md](docs/SETUP.md#checks-the-same-commands-ci-runs).

## Conventions
- **Views are thin.** Writes go through `services.py`, reads through `selectors.py`, and every state change writes an
  `AuditEvent`.
- **Staff code is scoped to programs.** Querysets are always filtered by the program in the URL, and every URL is in
  the permission-matrix test.
- **Migrations are expand/contract only.** Never edit an applied migration.
- **Money and time:** money is `Decimal` (`DecimalField(12, 2)`, PHP); time is timezone-aware, `Asia/Manila`.
- **Uploads are never served inline.** Downloads redirect to short-lived presigned URLs sent as attachments.
- **Templates:**
  - extend a layout;
  - autoescape everything, and never put `|safe` on user data;
  - no inline JS or CSS, because of the Content Security Policy; no `hx-on`.
- **Front end:** strict TypeScript, colours and spacing from CSS tokens, WCAG 2.2 AA.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`,
  `refactor:`, `test:`), imperative mood, subject of 72 characters or fewer.
- **Never commit** secrets, `.env`, real personal data or build output. Fixtures use Faker only, and personal data is
  never logged.

## Environment notes
- `.env.example` (tracked) documents every setting; `.env` (git-ignored) holds your local values. Use `127.0.0.1`, not
  `localhost`, in `DATABASE_URL`: compose publishes ports on IPv4 loopback only.
- The development PostgreSQL listens on host port 5433, so it doesn't clash with a native PostgreSQL on 5432.
- The repository uses LF line endings (`.gitattributes` sets `eol=lf`).
- **On Windows:**
  - the commands work in PowerShell 5.1, which has no `&&` (use `;`, or `A; if ($?) { B }`); Git Bash works too;
  - with `core.autocrlf=true`, `.gitattributes` still keeps files LF;
  - scripts that edit Python or Markdown files must open them with `encoding="utf-8"` (the default code page,
    cp1252, mangles characters such as `§` and `₱`).
