# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project
ScholarSync V2 is a ground-up Django rewrite of ScholarSync, the City of Taguig scholarship platform. It has three
roles:
- **Students** build a profile, get matched to programs, apply with documents, and track their allowances.
- **Program staff** review applications, manage scholars and terms, and run disbursements.
- **The scholarship office** (super admin) manages programs, staff, reports and analytics.

Programs (TCU CEAA, LANI, and future ones) are **data**, not code.
- **Spec (source of truth):** `docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md`
- **Legacy audit (v1 features, business rules, problems):** `docs/legacy-audit.md`
- **Legacy repo (read-only reference):** https://github.com/Drainsoul/ScholarSync at commit `fa9974c`

## Stack
- **Backend:** Python 3.13 (uv), Django 5.2 LTS, PostgreSQL 17 (Neon), django-allauth, django-storages (Cloudflare R2),
  django-anymail (Resend).
- **Frontend:** Django templates + HTMX (django-htmx, django-template-partials); a little strict TypeScript and plain
  CSS tokens built with Vite (django-vite); Biome.
- **Quality:** ruff, mypy + django-stubs, pytest + pytest-django + factory_boy, Playwright.
- **Host:** Vercel (Python runtime, region `sin1`). Request/response bodies are capped at 4.5 MB, and there is no local
  disk or background worker. Files go straight to R2 with presigned URLs; email goes through an outbox, with cron
  retries.

## File structure (apps beyond `core` arrive milestone by milestone)
```
config/            settings.py (environs), test_settings.py (pytest: forces production security), e2e_settings.py (Playwright: HTTP live server,
                   enforced CSP, kit on), urls.py, wsgi.py
apps/
  accounts/        custom User, roles, allauth adapters
  programs/        Program, BenefitTier, RequiredDocument, School, AcademicTerm, memberships
  students/        StudentProfile, FamilyMember, EducationRecord
  files/           StoredFile, presigned upload/confirm/download
  applications/    Application, Document, review services
  awards/          Award, ScholarTerm, renewals, term rollover
  money/           DistributionSchedule, Disbursement, Budget
  matching/        eligibility rules + advisory legacy-model hint (JSON params)
  reports/         program reports and files
  workspace/       tasks, notifications, email outbox
  office/          super admin screens
  kit/             design kit + key-screen mockups at /_kit/ (no models; DJANGO_KIT)
  core/            AuditEvent, permissions, layouts, health check
  <app>/           models.py services.py selectors.py views.py urls.py forms.py templates/ tests/
templates/         base.html, layouts/, partials/, components/
frontend/          Vite root: src/*.ts, src/styles/*.css (builds to static/dist/, git-ignored)
scripts/           one-off tools (export_legacy_model.py)
tests/             cross-app tests (permission matrix), tests/e2e/ (Playwright)
docs/              legacy-audit.md, superpowers/specs/, superpowers/plans/
manage.py  pyproject.toml  uv.lock  compose.yaml  vercel.json  .env.example
```

## Commands (PowerShell, repo root; `python -m uv` because uv isn't on PATH)
- Setup: `docker compose up -d --wait` (Postgres 17 on **5433**) · `Copy-Item .env.example .env` · `python -m uv sync` ·
  first front-end install **inside** `frontend/` (`npm install`; `npm --prefix frontend install` breaks on npm 10)
- Run: `python -m uv run python manage.py runserver` with `npm --prefix frontend run dev` (`VITE_DEV_MODE=true`), or
  build once with `npm --prefix frontend run build`
- Checks (= CI): `python -m uv run ruff check .` · `python -m uv run ruff format --check .` · `python -m uv run mypy .` ·
  `python -m uv run python manage.py makemigrations --check --dry-run` · `python -m uv run pytest -n auto` ·
  `python -m uv run pytest -m e2e --ds=config.e2e_settings --browser chromium` (once:
  `python -m uv run playwright install chromium`) · `npm --prefix frontend run typecheck|check|build|budget`
- Deploy check (as CI runs it): `manage.py check --deploy --fail-level WARNING` with `DJANGO_DEBUG=false`,
  `DJANGO_ALLOWED_HOSTS=scholarsync.example` and `DJANGO_ENV_FILE=/nonexistent` so the local `.env` can't mask a
  missing variable (it did once: CI failed on an empty `ALLOWED_HOSTS` that passed locally)

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
  - no inline JS/CSS, because of the CSP; no `hx-on`.
- **Front end:** strict TypeScript, colours and spacing from CSS tokens, WCAG AA.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`), imperative mood,
  subject ≤ 72 characters.
- **Never commit** secrets, `.env`, real personal data or build output. Fixtures use Faker only, and PII is never
  logged.

## Environment
- Windows 11. PowerShell 5.1 is the primary shell (no `&&`); Git Bash is also available.
- Git has `core.autocrlf=true`, so `.gitattributes` (`eol=lf`) is added at scaffold time.
- `.env.example` (tracked) documents every setting; `.env` (git-ignored) holds local values.
- Local Postgres runs on host port 5433; a native PostgreSQL owns 5432 on this machine.
- Python file edits from scripts must use `encoding="utf-8"` (Windows defaults to cp1252 and mangles `§`).
