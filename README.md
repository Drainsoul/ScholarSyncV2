# ScholarSync V2

A ground-up rewrite of [ScholarSync](https://github.com/Drainsoul/ScholarSync), the City of Taguig scholarship
platform. Students build a profile, check which programs they qualify for, apply with their documents and track their
allowances. Program staff review applications, manage scholars and terms and run disbursements. The scholarship office
oversees every program, staff account and report.

**Status:** M2 scaffold done (Django project, health check, front-end toolchain, CI). Features start in M3; see
the roadmap in the spec.

## Stack
Django 5.2 LTS (Python 3.13, uv) · PostgreSQL (Neon) · Django templates + HTMX + a little TypeScript (Vite) ·
Cloudflare R2 for files · Resend for email · deployed on Vercel.

## Local development
Prerequisites: Python via [uv](https://docs.astral.sh/uv/) (`python -m pip install --user uv`), Node ≥ 22.12 and
Docker Desktop. Commands are for PowerShell from the repository root; `python -m uv` works even when `uv` isn't on
`PATH`.

```powershell
docker compose up -d --wait          # Postgres 17 on localhost:5433
Copy-Item .env.example .env          # local settings; never put real secrets in it
python -m uv sync                    # Python 3.13 + dependencies
Set-Location frontend; npm install; Set-Location ..   # first install must run inside frontend/
python -m uv run python manage.py migrate
npm --prefix frontend run build      # or `npm --prefix frontend run dev` with VITE_DEV_MODE=true in .env
python -m uv run python manage.py runserver
```

### Checks (the same commands CI runs)
```powershell
python -m uv run ruff check .
python -m uv run ruff format --check .
python -m uv run mypy .
python -m uv run python manage.py makemigrations --check --dry-run
python -m uv run pytest -n auto
npm --prefix frontend run typecheck
npm --prefix frontend run check
npm --prefix frontend run build; npm --prefix frontend run budget
```

## Docs
- [Design spec and roadmap](docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md): architecture, domain model,
  security, deployment, milestones.
- [Legacy audit](docs/legacy-audit.md): what v1 does, its business rules and its problems; the feature-parity
  checklist.
- [CLAUDE.md](CLAUDE.md): project structure, commands and conventions.

## License
[MIT](LICENSE)
