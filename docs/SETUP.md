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
is migrated and the sample data is loaded if the database has no users yet. Later runs start in seconds and keep your
data. No `.env` file is needed; if you have one, explore mode ignores it.

Explore mode is for your own computer only. Every port is published on `127.0.0.1`, and the app answers only
`localhost` and `127.0.0.1`. To let other people use it, follow [HOSTING.md](HOSTING.md).

Pages to try: the home page `/`, the design kit and mockups `/_kit/`, and the health check `/healthz`. Sign-in and the
test accounts arrive with M4.

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
npm --prefix frontend run build                            # or run `npm --prefix frontend run dev` with VITE_DEV_MODE=true in .env
python -m uv run python manage.py runserver
```

The app is at <http://localhost:8000> and the design kit at <http://localhost:8000/_kit/>. Without an `EMAIL_URL`, emails
print to the terminal.

Notes:
- `.env.example` has `DJANGO_DEBUG=true` and a database URL that uses `127.0.0.1`, not `localhost`. Compose publishes
  ports on IPv4 loopback only, and `localhost` can resolve to IPv6 and fail.
- Developer mode loads the demo and the kit, and serves plain HTTP.
- Do not run the one-command `web` container and `runserver` at the same time on port 8000. Set `APP_PORT` for one of
  them, or `docker compose stop web worker`.
- `docker compose down -v` deletes the development database. Use `docker compose down` to keep it.

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
