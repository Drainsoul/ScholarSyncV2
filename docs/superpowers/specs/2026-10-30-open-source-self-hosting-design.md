# ScholarSync V2: open source, one-command run, self-hosting

- **Date:** 2026-10-30
- **Status:** draft for Kenneth's review. Once approved, it amends the main spec
  (`2026-10-11-scholarsync-v2-design.md`, which becomes revision 4; §12 below lists the sections).
- **Replaces:** Vercel as the deployment target (main spec §11 and the parts of §2, §7, §9, §14–§17 built on it).

## 1. Intent

ScholarSync is Kenneth's portfolio project. Nobody hosts an official copy: the repository is published as open source
(MIT, already in `LICENSE`), and people run it themselves.

Kenneth pictures two kinds of visitor:

1. **Explorers** (most visitors): hiring managers and curious people. They fork or clone the repo, run **one command**,
   and the app is running on their own computer at a localhost port. They log in with a ready-made test account for the
   role they want to see and click around realistic sample data. They should never need an account anywhere, an API key
   or a credential.
2. **Self-hosters** (the occasional developer): someone who wants to really use it. They accept more steps: create their
   own `.env` from `.env.example` with their own credentials, remove the demo, and host it wherever they like, with
   whatever providers they like.

Success: a hiring manager with Git and Docker Desktop goes from `git clone` to logged in as a scholarship officer
in one command and a few minutes, without reading more than the README's quick start.

## 2. Goals, non-goals, anti-goals

**Goals**
1. One command runs the whole app locally, on Windows, macOS and Linux, and it is reachable at a port.
2. Test accounts for every role, offered on the login page with one-click form filling.
3. Provider-neutral self-hosting: any PostgreSQL, any S3-compatible object storage, any email service, any host that
   runs a container.
4. Removing all demo material for a real deployment means deleting **one folder**, with no other edits.
5. Three guides: a short README quick start, a setup guide (local), a hosting guide (self-host).

**Non-goals**
- Kenneth hosting a public demo or production instance anywhere.
- A packaged desktop app (installer, Electron, etc.). "Run it on their desktop" means the one-command run.
- One-click deploy buttons for specific hosts.
- Supporting a deployment without Docker in the guides (developers may, but it isn't documented as a hosting path).
- Branding through settings (site name, organisation, logo). Rebranding is a fork-and-edit job.
- A published container image or release pipeline.

**Anti-goals (would be a failure even if it works)**
- Test accounts with published passwords existing on a real hosted site.
- The explore run needing any sign-up, key, credential or edit of a config file.
- The demo removal needing edits in several places, or leaving a dangling reference that breaks the app.
- Self-hosting tied to Kenneth's own providers (Neon, Cloudflare R2, Resend, Vercel).

## 3. Decided by Kenneth (2026-10-30)
- No hosting by Kenneth; open source; visitors run it themselves on localhost.
- One command, then the app is reachable at a port on their PC.
- A login-page notice offers prepared test accounts; clicking a role fills the form; the visitor clicks **Log in**.
- Self-hosters get a `.env.example` to copy and fill with their own credentials.
- A setup guide (local run) and a hosting guide (self-host) exist.
- The hosting guide tells them to delete one file (or as few as possible) to remove demo material.
- Test accounts, sample data and the login notice are the demo material; nothing else needs removing.
- Self-hosters use whatever providers they want.
- Making the repository public is part of this work. If the history scan finds a secret, rewriting this repository's
  history to remove it is allowed (Kenneth's explicit permission, overriding the usual no-rewrite rule for this case).
- The "City of Taguig" identity stays hard-coded. Self-hosters who want their own name or logo fork and edit the
  templates; the hosting guide says where.

## 4. The one-command run (explore mode)

**The command:** `docker compose up` from the repository root. Prerequisites: Git and Docker Desktop (or Docker Engine
with the Compose plugin). Nothing else is installed on the visitor's machine. *(Claude's call: Docker over a
`start.bat`/`start.sh` that installs Python, Node and PostgreSQL, because those scripts are where "easy" setups break,
and the same container doubles as the self-hosting artifact.)*

**What runs** (`compose.yaml`, services; names are the builder's choice):

| Service | Purpose | Host port (default) |
|---|---|---|
| web | the app (gunicorn), built from the repo's `Dockerfile` | **8000** → `http://localhost:8000` |
| db | PostgreSQL 17 | 5433 (kept for the developer workflow) |
| storage | an S3-compatible object store, so uploads use the same code path as production | builder's choice; the browser must reach it (presigned PUT/GET) |
| mail | Mailpit: catches every email and shows it in a web inbox | 8025 → `http://localhost:8025` |
| worker | sends queued email and runs periodic cleanup (§7) | none |

**First run:** builds the image (Vite bundle inside the build, so no Node on the host), waits for the database, runs
migrations and `createcachetable`, creates the storage bucket, then loads the demo (accounts + sample data) **only if the
database has no users yet**. Later runs start in seconds and keep the visitor's data. `docker compose down -v` resets
everything.

**Requirements on the run:**
- No `.env` file is needed: compose supplies explore-mode defaults. If a `.env` exists, it does not break explore mode.
- Host ports are overridable through environment variables (for example `APP_PORT=8080 docker compose up`), documented
  in the setup guide, because 8000 is often taken.
- Works on Windows: shell scripts used inside the image keep LF line endings (`.gitattributes` already forces `eol=lf`).
- The console prints the URL and points at the test accounts when the app is ready.
- Signing up a new account works: the verification email lands in Mailpit.

**Optional extra (Claude's suggestion, not decided by Kenneth):** a GitHub Codespaces configuration and an "Open in
Codespaces" button in the README, running the same compose setup with nothing installed. Build last, drop if it fights
the design.

## 5. The demo

**Location:** everything demo-only lives in one Django app folder, `apps/demo/`:
- the test-account definitions and the shared password;
- the sample-data loader (Faker `en_PH`, seeded, never real people; reuses the names already used in
  `apps/kit/samples.py` where they fit);
- the login-page notice template;
- its own tests.

**Removal:** the hosting guide's instruction is "delete the `apps/demo/` folder". After that, with no other edit:
- the app starts, every page works, and the full test suite passes;
- no notice, no accounts, no seeding command;
- `INSTALLED_APPS` includes `apps.demo` only when the folder exists, and every other part of the app reaches the demo
  through an optional hook (for example a login-page extension point that renders nothing when no app fills it), never
  by importing it.

**Test accounts:** one per role, all sharing one password that passes the app's own password validators. The emails
use a reserved test domain (for example `@scholarsync.test`); the builder picks the exact addresses and password.

| Button | Account | What it shows |
|---|---|---|
| Student | a student with an active TCU CEAA award, a returned LANI application and allowance history | the student area |
| Program staff | `staff` membership in TCU CEAA | reviewing applications, scholars, preparing disbursements |
| Program head | `head` membership in TCU CEAA | everything staff do, plus releasing money and program settings |
| Scholarship office | `super_admin` | all programs, staff, schools, reports, analytics, audit log |

The accounts are pre-verified, so logging in never needs email.

**Programs are not demo material** *(Claude's call)*. The TCU CEAA and LANI program definitions (tiers, rules,
required documents), the school list and the terms come from the non-demo `seed_programs` command that main spec §16
already puts in M4, in `apps/programs/`. It is never run automatically in production. After deleting `apps/demo/`, a
self-hoster starts with an empty system and either runs `seed_programs` for the Taguig starter programs or creates
their own in the office screens; the hosting guide says so right after "create the first scholarship-office account".
The demo loader calls `seed_programs` first, then adds people and activity on top.

**Sample data:** enough for every screen to look real: the programs from `seed_programs`, then scholars across statuses, applications in every state, documents (small generated placeholder files), schedules
and disbursements, notifications and audit events. It grows milestone by milestone: each feature milestone extends the
loader for its own screens.

**Login notice:**
- A clearly marked box above the login form: "Exploring ScholarSync? Use a test account", with one line saying these
  accounts and their data exist only on this copy.
- One button per role. Clicking fills email and password; the visitor presses **Log in**. Filling is done by the bundled
  TypeScript (CSP forbids inline scripts and `hx-on`), using data attributes on the buttons.
- Without JavaScript, the box lists each role's email and the password as text.
- The README lists the same accounts.

**When the demo is active:** only when `apps/demo/` exists **and** the app runs in explore or developer mode (§6). In
production mode it is inactive even if the folder is still there: no notice, and the loader refuses to run. On top of
that, `manage.py check --deploy` fails with a clear message ("delete apps/demo before deploying") while the folder
exists, so the hosting guide's own check catches a forgotten deletion. *(Claude's call, from Kenneth's anti-goal.)*

## 6. Modes

| Mode | How it's selected | Debug | HTTPS-only (SSL redirect, HSTS, secure cookies) | Demo | Design kit `/_kit/` |
|---|---|---|---|---|---|
| Developer | `DJANGO_DEBUG=true` (developer's `.env`) | on | off | active | on by default |
| Explore | set by `compose.yaml` (for example `SCHOLARSYNC_EXPLORE=true`) | off | off (plain `http://localhost`) | active | on |
| Production | neither | off | on | inactive | refused |

- **Explore mode is for the visitor's own machine only** *(Claude's call, from the anti-goal)*. Compose publishes every
  port on `127.0.0.1`, and in explore mode `ALLOWED_HOSTS`, the CSRF origins and the public storage endpoint are fixed
  to `localhost`/`127.0.0.1`; settings refuse explore mode with any other host. Reaching it from another device or a
  remote VM is unsupported; anyone who wants that follows the hosting guide. The optional Codespaces setup, if built,
  may add only Codespaces' own forwarded-port host.
- Explore mode behaves like production in everything except HTTPS: gunicorn, WhiteNoise, custom error pages, enforced
  or report-only CSP as configured. It is never selected by default; production is the fail-closed default.
- The kit's existing production guard (today keyed on `VERCEL_ENV=production`) keys on production mode instead.
- The existing rule stands: startup fails fast on a missing required variable in production mode, with no insecure
  fallbacks.

## 7. Provider-neutral infrastructure

| Concern | Explore (compose) | Self-host (`.env`) |
|---|---|---|
| Database | the `db` container | any PostgreSQL 17 through `DATABASE_URL`; an optional second URL for migrations when the main one goes through a transaction pooler |
| Files | the `storage` container | any S3-compatible service: endpoint, region, bucket, keys, an optional public endpoint for presigned URLs, addressing style |
| Email | Mailpit over SMTP | any SMTP server through one URL-style setting, plus the from-address. Provider APIs (through Anymail) only if the builder finds it costs nothing extra |
| Background jobs | the `worker` container | the same worker container, or the documented commands on any scheduler |
| Google sign-in | off (no keys; button hidden) | on when client ID and secret are set |
| Error tracking | off | Sentry when a DSN is set |

**Files:** the upload design in main spec §7 stays (intent → presigned PUT → confirm with sniffing → presigned GET as an
attachment, never inline), because it works on every host and keeps large bodies out of the app. Its justification
changes from "Vercel's 4.5 MB cap" to "works on any host, keeps the app stateless". The 4.5 MB export rule becomes the
builder's call. Presigned URLs must point at an address the browser can reach (inside compose, the app talks to the
storage container by its service name, but the browser needs `localhost`), and CSP `connect-src`/`img-src` include the
storage origin from settings.

**Background jobs:** Vercel cron goes away. Two management commands replace the cron endpoints: one retries failed
outbox emails, one runs cleanup (`clearsessions`, expired invites, old sent outbox rows). The `worker` service runs them
on a loop. The hosting guide also shows running them from cron or a host's scheduler. The `/_cron/` endpoints and
`CRON_SECRET` are dropped.

**Email sending:** the outbox design in main spec §9 stays; only the transport becomes provider-neutral.

## 8. Removing Vercel

Removed or rewritten:
- `vercel.json`, `build.py` (and `[tool.vercel.scripts]` in `pyproject.toml`);
- `config/hosts.py` Vercel host detection (hosts come from `DJANGO_ALLOWED_HOSTS` and a CSRF-trusted-origins setting);
- `VERCEL_ENV` checks (kit guard, Sentry environment/release), log wording in `apps/core/logging.py`;
- the CI comment and any Vercel-only steps.

The spike branch `spike/vercel` stays local and historical; `STATE.md` keeps its results as history.

## 9. `.env.example`

One file, tracked, and the self-hoster's starting point. Grouped by concern (core, database, files, email, Google,
error tracking, modes), each variable with a comment saying what it is, whether it's required in production, an
example value or format, and where to get it. Values are safe placeholders, never secrets. Copying it to `.env` also
works for Kenneth's developer workflow (the builder decides how the developer-only values are marked). Main spec §14
is rewritten to match.

## 10. Guides

- **`README.md`:** what ScholarSync is, a screenshot, **Quick start** (prerequisites, `git clone`, `docker compose up`,
  open `http://localhost:8000`), the test-account table, where emails go (Mailpit), how to stop and reset, links to the
  two guides. A hiring manager should need nothing else.
- **`docs/SETUP.md`:** running locally in depth: the one-command run, changing ports, resetting, troubleshooting
  (Docker not running, port in use, first build slow, Windows line endings), and the developer workflow (uv, npm,
  checks) that the README has today.
- **`docs/HOSTING.md`:** self-hosting step by step: delete `apps/demo/`; copy `.env.example` to `.env` and fill it in;
  (optional) change the City of Taguig name, stripe and brand mark in `templates/layouts/` and the favicon;
  provision PostgreSQL, S3-compatible storage (bucket private, CORS for the site's origin, a lifecycle rule for
  `pending/`) and email; build and run the image behind HTTPS (the host's TLS or a reverse proxy); run the worker or
  schedule the commands; create the first scholarship-office account; run `manage.py check --deploy`; back up the
  database. Examples stay generic, with at most one or two worked provider examples clearly marked as examples.
  *(Claude's call)* Self-hosters build the image from source (`docker build`); no image is published to a registry and
  there is no release pipeline. The repo ships one production compose example (for example `compose.production.yaml`:
  web and worker only, with database, storage and email external, reading `.env`), which the guide uses and CI at
  least validates (`docker compose config`).

`CLAUDE.md` (stack, host, file structure, commands) is updated to match.

## 11. CI

- The existing jobs stay.
- A new **hosting-path** job proves the guide: delete `apps/demo/`, then run the test suite and
  `manage.py check --deploy` in production mode.
- A **compose smoke** job proves the one-command run: `docker compose up` (detached), wait for health, check that the
  login page answers on the app port and shows the notice. The builder may trim it if CI time becomes a problem.

## 12. Main spec changes (revision 4)

Applied when this document is approved:
- §1 goal 7 → "runs anywhere a container runs; one-command local run"; non-goals updated.
- §2 stack table: Database, Files, Email, Host and Local-services rows become provider-neutral; "Deliberately absent"
  changes from "outbox plus cron" to "outbox plus a worker loop".
- §7 constraints reworded (§7 of this document); §9 cron → worker commands.
- §10: the preview-database line goes; everything else stands.
- §11 "Vercel deployment" is replaced by "Running and hosting" (this document §4–§8).
- §14 env vars rewritten; §15 deploy step replaced by §11 of this document.
- §16: M1 marked historical; a new milestone for this work (§13 below); M4 gains the demo app and the login notice;
  later milestones each extend the sample data; M12's production checklist becomes the hosting guide's checklist.
- §17 Vercel risks replaced (§14 below); §18 questions 12 and 13 (Vercel plan, domain) closed as obsolete; §19 gains
  this decision.

## 13. Sequencing

1. **Now, before M4 (a new milestone, "M3.5 open-source packaging"):** spec revision 4; Vercel removal; modes; Dockerfile
   and compose (web, db, storage, mail; the worker can start empty); provider-neutral settings for database, files and
   email; `.env.example`; README, SETUP, HOSTING; the hosting-path and compose-smoke CI jobs; the empty `apps/demo/`
   skeleton with its hook and deploy check. The explore run works and shows the existing pages (the kit and mockups)
   even before accounts exist.
   *(Claude's call on scope)* M3.5 stands up the storage and mail containers, creates the bucket with its CORS rule and
   `pending/` lifecycle rule, and adds the settings and `.env.example` entries. It does **not** add the S3 or email
   libraries or prove a presigned round trip: there is nothing to upload or send yet. Those become acceptance items
   of M4 (email through Mailpit in the compose smoke test) and M5 (a presigned upload/download round trip in the
   compose smoke test). Unit tests keep using moto, as M1 decided.
   **Publication, the last part of M3.5:**
   1. Scan the full git history (every branch that will be pushed) for secrets, for example with gitleaks.
   2. Review every tracked document for things not meant for the public: `docs/legacy-audit.md` (v1 data and
      domains), the M1 plan (spike URLs, account names), `CLAUDE.md`, the specs. Kenneth decides on anything found.
   3. If a secret is found: show Kenneth the finding, rotate it, then rewrite history to remove it (allowed, §3) and
      force-push `main`. Branches never pushed (`spike/vercel`) stay local.
   4. Tear down the M1 spike's Vercel project, Neon database and R2 bucket, after Kenneth confirms.
   5. Kenneth flips the repository to public himself, or Claude does it on his explicit go-ahead at that moment.
2. **M4 (accounts, email, minimal program):** test accounts, the login notice and the first sample data, now that the
   `User` model and login page exist.
3. **M5 onward:** each milestone extends the sample-data loader for its own screens.

The red/blue/yellow redesign proposal is independent of this work and doesn't block it.

## 14. Risks and notes

| Risk | Mitigation |
|---|---|
| A secret in git history becomes public when the repo opens | Scan the full history before publishing; rotate anything found, then rewrite history (§13) |
| A document says something not meant for the public | Review every tracked document before publishing (§13) |
| The S3-compatible container's image or licence changes (MinIO's community distribution has changed before) | The builder picks a currently maintained image; the code only speaks the S3 API, so swapping it is a compose change |
| Presigned URLs signed for the internal hostname fail in the browser | A separate public endpoint setting (§7), covered by the compose smoke test from M5 |
| Port 8000 (or 5433, 8025) already in use on the visitor's machine | Ports overridable; the setup guide's troubleshooting section |
| Visitor's first build is slow or fails behind a proxy | README sets expectations; SETUP covers it |
| Demo folder forgotten in production | Demo inactive in production mode, plus the failing deploy check |

## 15. Left to the builder
- Service names, image choices and the storage container product.
- Exact test-account emails and the shared password (must pass the validators).
- The hook mechanism that lets the login page show the notice without importing the demo app.
- The mode variable's exact name.
- SMTP-only versus SMTP plus Anymail.
- Whether explore mode enforces CSP or leaves it report-only.
- The worker loop's interval and implementation.
- How developer-only values are marked in `.env.example`.
- The guides' exact wording and structure within §10.
