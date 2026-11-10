# Setup guide

Running ScholarSync on your own computer. Two ways:

- [Run it with one command](#run-it-with-one-command) to look around. Needs only Git and Docker.
- [Developer workflow](#developer-workflow) to change the code. Needs Python (uv), Node and Docker.

To host a copy for other people, use [HOSTING.md](HOSTING.md) instead.

## Run it with one command

```
docker compose up
```

From the repository root, with Docker running. This is "explore mode".

What starts:

| Service | What it is | Address |
|---|---|---|
| `web` | the app | <http://localhost:8000> |
| `worker` | deletes expired sessions every 5 minutes (email retry arrives with M4) | none |
| `db` | PostgreSQL 17 | `127.0.0.1:5433` |
| `storage` | S3-compatible file storage (RustFS) | `127.0.0.1:9000` |
| `storage-init` | creates the bucket, its CORS rule and the `pending/` expiry, then exits | none |
| `mail` | Mailpit, the inbox that catches every email | <http://localhost:8025> |

On the first run the app image is built (the front-end bundle is built inside it, so you need no Node), the database
is migrated and the demo accounts are loaded. Every start runs the loader again; it only adds what is missing (a
deleted demo account comes back) and never touches your other data. Later runs start in seconds. No `.env` file is
needed; if you have one, explore mode ignores it.

Explore mode is for your own computer only. Every port is published on `127.0.0.1`, and the app answers only
`localhost` and `127.0.0.1`. To let other people use it, follow [HOSTING.md](HOSTING.md).

Pages to try: the home page `/`, the design kit and mockups `/_kit/`, and the health check `/healthz`.

### Test accounts
The login page offers these as one-click buttons. All four use the password `explore-taguig-2026`; they exist only
on this copy. They exist in explore and developer copies (`docker compose up`, or `DJANGO_DEBUG=true`), never on
a hosted copy.

- Student: `student@scholarsync.test`
- Program staff: `staff@scholarsync.test`
- Program head: `head@scholarsync.test`
- Scholarship office: `office@scholarsync.test`

### Email
The app sends all email to Mailpit. Open <http://localhost:8025> to read it. Nothing is delivered to real addresses.

### Changing ports
Each host port has a variable. Set it in the same terminal before `docker compose up`.

| Variable | Default | What |
|---|---|---|
| `APP_PORT` | 8000 | the app |
| `MAIL_PORT` | 8025 | the Mailpit inbox |
| `DB_PORT` | 5433 | PostgreSQL |
| `STORAGE_PORT` | 9000 | file storage |

PowerShell:
```powershell
$env:APP_PORT = "8080"; docker compose up
```
bash, zsh:
```bash
APP_PORT=8080 docker compose up
```

Use the same value every time you run compose in that folder, because the storage rules depend on `APP_PORT`. A
`.env` file in the repository root with `APP_PORT=8080` works too for compose's own port settings.

### GitHub Codespaces
The "Open in GitHub Codespaces" badge in the README starts the same `docker compose up` stack in a codespace
(`.devcontainer/devcontainer.json`). Open the forwarded "ScholarSync" port 8000 once the build finishes. Explore mode
adds that one forwarded address to its allowed hosts, and nothing else.

Each codespace gets its own secret key: the devcontainer writes a random `EXPLORE_SECRET_KEY` to the git-ignored
`.devcontainer/explore.env` on first start and passes it to compose every time (`docker compose --env-file
.devcontainer/explore.env up -d --build`). Explore mode refuses the public `explore-only-` key inside a codespace. To
start the stack by hand in a codespace, use that same command.

**Never make the ports public.** Ports 8000 and 8025 are forwarded as private (only you, signed in to GitHub, can open
them), and the database and storage ports are not forwarded at all. Keep it that way: the explore copy has published
demo accounts (from M4) and a known database password, so anyone who could reach a public port could sign in as them.
The per-codespace key protects sessions only.

Known limitation: file storage is advertised at `localhost:9000`, which a codespace browser cannot reach. Uploads
arrive in a later milestone, so nothing uses it yet.

### Stopping and resetting
- Stop and keep your data: `Ctrl+C`, or `docker compose down`.
- Start again: `docker compose up`.
- Run in the background: `docker compose up -d --wait`. See logs with `docker compose logs -f web`.
- Reset everything (database, stored files, sample data): `docker compose down -v`.
- Rebuild after pulling new code: `docker compose up --build`.

If you use the [developer workflow](#developer-workflow) as well, `down -v` also deletes its database, because both
use the same volume. Plain `docker compose down` keeps it.

### Troubleshooting
**"Cannot connect to the Docker daemon", or `docker compose` hangs.** Docker Desktop is not running. Start it, wait
until it says it is running, and try again.

**"port is already allocated" or "address already in use".** Another program uses 8000, 8025, 5433 or 9000. Either stop
it, or [change the port](#changing-ports). Check what uses a port:
- PowerShell: `Get-NetTCPConnection -LocalPort 8000 -State Listen`
- bash: `lsof -i :8000`

**The first build is slow.** It downloads base images and installs packages, so allow a few minutes on a normal
connection. Later builds reuse the cache. Behind a company proxy, set the proxy in Docker Desktop's settings.

**The app container restarts or `web` is "unhealthy".** Read its log: `docker compose logs web`. It waits up to about
three minutes for the database and storage. If `db` is unhealthy, try `docker compose down -v` and start again.

**Windows line endings (`\r`: not found, `exec ... no such file`).** The repository forces LF line endings through
`.gitattributes`, so a normal clone is fine. If you copied the files in some other way, clone again with
`git clone`, or run `git add --renormalize .` and check out the files again.

**You see an old page after pulling new code.** Run `docker compose up --build`.

## Developer workflow

For changing the code. You run Django on your machine and only the supporting services in Docker.

Prerequisites: Docker Desktop, Python through [uv](https://docs.astral.sh/uv/) (`python -m pip install --user uv`),
and Node 22.12 or newer. Commands below are for PowerShell from the repository root; `python -m uv` works even when
`uv` is not on `PATH`. On macOS or Linux, use `uv` and `Copy-Item` becomes `cp`.

```powershell
docker compose up -d --wait db storage storage-init mail   # services only, not the app
Copy-Item .env.example .env                                # local settings; never put real secrets in it
python -m uv sync                                          # Python 3.13 and the dependencies
Set-Location frontend; npm install; Set-Location ..        # the first install must run inside frontend/
python -m uv run python manage.py migrate
python -m uv run python manage.py load_demo                # the test accounts; safe to re-run
npm --prefix frontend run build                            # or run `npm --prefix frontend run dev` with VITE_DEV_MODE=true in .env
python -m uv run python manage.py runserver
```

`load_demo` loads the four test accounts (see above). It only adds what is missing, so it is safe to re-run. It also gives the student a sample profile and creates an
unclaimed one for Paolo Villanueva (his invite email goes to Mailpit in explore mode).

`load_demo` runs `seed_programs`, which seeds the programs, their benefit tiers and required
documents, the starter schools and the academic terms. It never overwrites your edits.

The app is at <http://localhost:8000> and the design kit at <http://localhost:8000/_kit/>. Without an `EMAIL_URL`, emails
print to the terminal.

Notes:
- `.env.example` has `DJANGO_DEBUG=true` and a database URL that uses `127.0.0.1`, not `localhost`. Compose publishes
  ports on IPv4 loopback only, and `localhost` can resolve to IPv6 and fail.
- Developer mode loads the demo and the kit, and serves plain HTTP.
- Uploads work in developer mode once `storage` and `storage-init` are up (the `S3_*` values in `.env.example` point
  at them), through `runserver` on port 8000: the bucket's CORS rule names `localhost:8000` and `127.0.0.1:8000`.
- Do not run the one-command `web` container and `runserver` at the same time on port 8000. Set `APP_PORT` for one of
  them, or `docker compose stop web worker`.
- `docker compose down -v` deletes the development database. Use `docker compose down` to keep it.
- A database created before M4 has Django's default user table and must be reset before `migrate`: `docker compose down -v`, or drop and recreate the development database.

### Re-exporting the legacy model (never needed for normal use)
`apps/matching/data/legacy_tier_model.json` is committed. Only if you must rebuild it from the legacy `.pkl`, run
`python -m uv run --script scripts/export_legacy_model.py <pkl> <model-json> <parity-json>`. The script's docstring has
the `gh api` command that fetches the pickle. It is one-off, PEP 723 (it brings its own dependencies) and is never
imported by the app.

### Checks (the same commands CI runs)
```powershell
python -m uv run ruff check .
python -m uv run ruff format --check .
python -m uv run mypy .
python -m uv run python manage.py makemigrations --check --dry-run
python -m uv run pytest -n auto
python -m uv run playwright install chromium   # once
python -m uv run pytest -m e2e --ds=config.e2e_settings --browser chromium
npm --prefix frontend run typecheck
npm --prefix frontend run check
npm --prefix frontend run build; npm --prefix frontend run budget
```

The deploy check, as CI runs it (production mode, ignoring your `.env`):

```powershell
$env:DJANGO_DEBUG="false"; $env:DJANGO_ALLOWED_HOSTS="scholarsync.example"; $env:DJANGO_ENV_FILE="/nonexistent"
$env:DJANGO_SECRET_KEY="check-only-" + ("x" * 60); $env:DATABASE_URL="postgres://u:p@127.0.0.1:5433/scholarsync"
python -m uv run python manage.py check --deploy --fail-level WARNING
```

This fails while `apps/demo/` exists. That is intended: it is the reminder to delete it before deploying. CI's
hosting-path job deletes it first.
