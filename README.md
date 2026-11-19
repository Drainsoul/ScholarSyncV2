# ScholarSync V2

A ground-up rewrite of ScholarSync, a scholarship platform modelled on the City of Taguig's programs. Students build
a profile, check which programs they qualify for, apply with their documents and track their allowances. Program staff
review applications, manage scholars and terms and run disbursements. The scholarship office oversees every program,
staff account and report.

> Independent portfolio project. Not affiliated with or endorsed by the City of Taguig. All sample people and data
> are fictional.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/Drainsoul/ScholarSyncV2)

**Status:** v2.0 is feature-complete (milestones M1 to M12 in the
[design spec](docs/design/2026-10-11-scholarsync-v2-design.md)): student profiles, matching and applications;
review, scholars, terms and renewals; disbursements and budgets; dashboards, notifications, program reports,
analytics and the audit log. Since then it has had a security pass (two-factor sign-in with encrypted secrets, session
limits, the ASVS and WCAG reviews below). Run it locally and sign in with the test accounts below.

## Quick start
You need [Git](https://git-scm.com/downloads) and [Docker Desktop](https://www.docker.com/products/docker-desktop/)
(or Docker Engine with the Compose plugin), running. Nothing else: no Python, Node, database or account.

```
git clone https://github.com/Drainsoul/ScholarSyncV2.git
cd ScholarSyncV2
docker compose up
```

The first build takes a few minutes. When the console prints `ScholarSync is running`, open:

- the app: <http://localhost:8000>
- the design kit and key-screen mockups: <http://localhost:8000/_kit/>
- the email inbox (every email the app sends lands here, none leave your computer): <http://localhost:8025>

The app, its database and its file storage all run in containers on your computer, and the ports are reachable only
from your computer. Later runs start in seconds and keep your data.

**Stop:** press `Ctrl+C`, or run `docker compose down` from another terminal. Your data stays.
**Reset everything:** `docker compose down -v` deletes the database and stored files.

**No install:** the badge above opens the same stack in a GitHub Codespace (see
[SETUP](docs/SETUP.md#github-codespaces)).

Port 8000 taken? See [changing ports](docs/SETUP.md#changing-ports).

Public pages: about, privacy, terms, cookies, FAQ and contact are in the running app (`/about/`, `/privacy/`,
`/terms/`, `/cookies/`, `/help/`, `/contact/`); their text lives in [templates/core/pages/](templates/core/pages/).
To report a security problem, see [SECURITY.md](SECURITY.md).

## Test accounts
Every account uses the password `explore-demo-2026`.

| Role | Account | What it shows |
|---|---|---|
| Student | `student@scholarsync.test` | the student area |
| Program staff | `staff@scholarsync.test` | reviewing applications, scholars, disbursements |
| Program head | `head@scholarsync.test` | staff features plus releasing money and program settings |
| Scholarship office | `office@scholarsync.test` | all programs, staff, reports, analytics, the audit log |

They are offered on the login page as one-click buttons. They appear automatically in explore copies
(`docker compose up`) and in developer copies (`DJANGO_DEBUG=true`) after
`python -m uv run python manage.py load_demo`. They never exist on a hosted copy.

## Self-hosting
See [docs/HOSTING.md](docs/HOSTING.md). After the first start, create the scholarship-office account:

```
docker compose -f compose.production.yaml exec web python manage.py create_office_admin --email you@example.org --full-name "Your Name"
```

## Stack
Django 5.2 LTS (Python 3.13) · PostgreSQL 17 · Django templates + HTMX + a little TypeScript (Vite) · any
S3-compatible storage for files · any SMTP server for email · runs in Docker.

## Guides
- [Setup](docs/SETUP.md): running locally in depth (ports, reset, troubleshooting) and the developer workflow (tests,
  linting, front end).
- [Hosting](docs/HOSTING.md): running your own copy for real, with your own database, storage and email, behind HTTPS.
  It ends with a [runbook](docs/HOSTING.md#10-runbook) (update, roll back, restore, rotate secrets); the
  [walkthrough](docs/hosting-walkthrough.md) records the guide followed once on a clean checkout.
- Security and accessibility reviews: [OWASP ASVS 5.0 level 2](docs/security/asvs-l2.md),
  [WCAG 2.2 AA](docs/accessibility/wcag-22-aa.md) and the [security policy](SECURITY.md).
- [Design spec and roadmap](docs/design/2026-10-11-scholarsync-v2-design.md) and the
  [open-source and self-hosting design](docs/design/2026-10-30-open-source-self-hosting-design.md).
- [Legacy audit](docs/legacy-audit.md): what v1 (a private repository) does, its business rules and its problems.
- [Contributing](CONTRIBUTING.md): project structure, commands and conventions for contributors.

## License
Copyright © 2026 John Kenneth Planas. Released under the [MIT License](LICENSE). Bundled icons and fonts keep their
own licenses: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
