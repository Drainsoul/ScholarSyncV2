# ScholarSync V2

A ground-up rewrite of [ScholarSync](https://github.com/Drainsoul/ScholarSync), a scholarship platform modelled on the
City of Taguig's programs. Students build a profile, check which programs they qualify for, apply with their documents
and track their allowances. Program staff review applications, manage scholars and terms and run disbursements. The
scholarship office oversees every program, staff account and report.

> Independent portfolio project. Not affiliated with or endorsed by the City of Taguig. All sample people and data
> are fictional.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/Drainsoul/ScholarSyncV2)

**Status:** M3.5 (open-source packaging) is in progress. You can run the app and browse the home page and the design
kit. Sign-in, the test accounts and the first real features arrive in M4; the roadmap is in the
[design spec](docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md).

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

Public pages: [about](/about/), [privacy](/privacy/), [terms](/terms/), [cookies](/cookies/), [FAQ](/help/) and
[contact](/contact/) (on a running copy). To report a security problem, see [SECURITY.md](SECURITY.md).

## Test accounts
| Role | Account | What it shows |
|---|---|---|
| Student | arrives with sign-in (M4) | the student area |
| Program staff | arrives with sign-in (M4) | reviewing applications, scholars, disbursements |
| Program head | arrives with sign-in (M4) | staff features plus releasing money and program settings |
| Scholarship office | arrives with sign-in (M4) | all programs, staff, reports, analytics |

When they exist, they are listed here and offered on the login page as one-click buttons. They exist only on copies
run with `docker compose up`, never on a hosted one.

## Stack
Django 5.2 LTS (Python 3.13) · PostgreSQL 17 · Django templates + HTMX + a little TypeScript (Vite) · any
S3-compatible storage for files · any SMTP server for email · runs in Docker.

## Guides
- [Setup](docs/SETUP.md): running locally in depth (ports, reset, troubleshooting) and the developer workflow (tests,
  linting, front end).
- [Hosting](docs/HOSTING.md): running your own copy for real, with your own database, storage and email, behind HTTPS.
- [Design spec and roadmap](docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md) and the
  [open-source and self-hosting design](docs/superpowers/specs/2026-10-30-open-source-self-hosting-design.md).
- [Legacy audit](docs/legacy-audit.md): what v1 does, its business rules and its problems.
- [CLAUDE.md](CLAUDE.md): project structure, commands and conventions for maintainers.

## License
[MIT](LICENSE)
