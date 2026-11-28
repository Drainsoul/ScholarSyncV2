# ScholarSync

A scholarship platform modelled on the City of Taguig's programs.

- **Students** build a profile, see which programs they qualify for, apply with their documents and track their
  allowances.
- **Program staff** review applications, manage scholars and terms, and release allowances.
- **The scholarship office** oversees every program, staff account and report.

> Independent portfolio project, not affiliated with or endorsed by the City of Taguig. All sample people and data are
> fictional.

**Try it now: [live demo](https://scholarsyncv2.vercel.app).** Sign in with any of the [test accounts](#test-accounts)
(one-click buttons on the sign-in page). It sends no email, and its data resets every night around 03:00 Manila time,
so don't enter real personal information.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/Drainsoul/ScholarSyncV2)

## Quick start
You need [Git](https://git-scm.com/downloads) and Docker running: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
on Windows or macOS; on Linux, Docker Desktop or [Docker Engine](https://docs.docker.com/engine/install/) with the
Compose plugin ([Linux notes](docs/SETUP.md#on-linux)). Nothing else.

```
git clone https://github.com/Drainsoul/ScholarSyncV2.git
cd ScholarSyncV2
docker compose up
```

The first build takes a few minutes. When the console prints `ScholarSync is running`, open:

- the app: <http://localhost:8000>
- the email inbox (no email leaves your computer): <http://localhost:8025>
- the design kit: <http://localhost:8000/_kit/>

Stop with `Ctrl+C` (your data stays). `docker compose down -v` deletes everything. Port 8000 taken? See
[changing ports](docs/SETUP.md#changing-ports). No Docker? The badge above runs it in a GitHub Codespace.

## Test accounts
Every account uses the password `explore-demo-2026`. The sign-in page offers them as one-click buttons.

| Group | Account | What it shows |
|---|---|---|
| Students | `new@scholarsync.test` | an empty profile: setup, matching, a first application |
| | `student@scholarsync.test` | a nearly complete profile, a LANI draft and support replies |
| | `applicant4@scholarsync.test` | a TCU CEAA application returned with a declined document |
| | `scholar@scholarsync.test` | a TCU CEAA scholar with a released allowance and a renewal due |
| | `scholar3@scholarsync.test` | a TCU CEAA award on hold |
| Program staff | `staff@scholarsync.test` | TCU CEAA review queue, scholars, walk-ins, tasks, support |
| | `head@scholarsync.test` | staff features plus releasing money, settings and reports |
| | `lani.staff@scholarsync.test` | the LANI queue and scholars |
| | `lani.head@scholarsync.test` | LANI reports to approve or fix |
| Scholarship office | `office@scholarsync.test` | all programs, staff, reports, analytics, reply templates, audit log |

Test accounts exist only in local copies (`docker compose up`, or `manage.py load_demo` in development) and in the
[live demo](https://scholarsyncv2.vercel.app), which runs from the `demo` branch. A self-hosted copy never has them.

## Self-hosting
Follow [docs/HOSTING.md](docs/HOSTING.md), then create the scholarship-office account:

```
docker compose -f compose.production.yaml exec web python manage.py create_office_admin --email you@example.org --full-name "Your Name"
```

## Stack
Django 5.2 (Python 3.13) · PostgreSQL 17 · Django templates + HTMX + a little TypeScript (Vite) · any S3-compatible
storage · any SMTP server · Docker.

## More
- [Setup](docs/SETUP.md): local development, tests and troubleshooting.
- [Hosting](docs/HOSTING.md): running your own copy behind HTTPS, with a runbook.
- [Contributing](CONTRIBUTING.md): structure, commands and conventions.
- [Design spec](docs/design/2026-10-11-scholarsync-design.md): how everything is meant to work.
- [Screenshots](docs/screenshots/README.md): a walkthrough of every role, from the demo data.
- Reviews: [OWASP ASVS 5.0 L2](docs/security/asvs-l2.md), [WCAG 2.2 AA](docs/accessibility/wcag-22-aa.md).
- [Security policy](SECURITY.md): how to report a vulnerability.

## License
© 2026 John Kenneth Planas, [MIT License](LICENSE). Bundled icons, fonts and libraries keep their own licenses
([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
