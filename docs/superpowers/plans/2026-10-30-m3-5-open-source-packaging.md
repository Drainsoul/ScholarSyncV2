# M3.5 Open-Source Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anyone can clone ScholarSync and run it with `docker compose up`, self-hosters get a provider-neutral
`.env.example` and guides, Vercel is gone, the demo lives in one deletable folder, and the repository is ready to
publish.

**Architecture:** Three modes in `config/settings.py`: developer (`DJANGO_DEBUG=true`), explore
(`SCHOLARSYNC_EXPLORE=true`, set by `compose.yaml`, localhost-only and HTTP) and production (neither, the
fail-closed default). One multi-stage `Dockerfile` (Vite build, then a uv-managed Python image running gunicorn)
serves both the explore compose stack (web, worker, PostgreSQL, S3-compatible storage, Mailpit) and the self-hosting
`compose.production.yaml`. Demo material lives in `apps/demo/`, installed only when the folder exists, active only
outside production, and the deploy check fails while it is present.

**Tech Stack:** Django 5.2, environs (`dj_db_url`, `dj_email_url`), gunicorn, Docker Compose v2, PostgreSQL 17,
Mailpit, an S3-compatible server, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-30-open-source-self-hosting-design.md` (approved 2026-10-30), amending
`docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md`. Read both.

## Global Constraints

- Commands run from the repo root in PowerShell 5.1 (no `&&`) or Git Bash; Python through `python -m uv run …`.
- Every task: TDD where code is involved, one Conventional Commit per task, staging only that task's files.
- **No AI attribution anywhere**: no `Co-Authored-By`, no "Generated with", no 🤖, in commits or PR text. Repeat this in
  every subagent prompt that commits.
- Never push, never force-push, never rewrite history, except Task 11 step 4 after Kenneth's explicit go-ahead.
- Never claim ScholarSync is an official City of Taguig service, in any page, doc or commit.
- After each task, update the local, git-ignored `STATE.md` (timestamp, next action, inventory, changelog line).
  Never stage it.
- Explore mode serves only `localhost` and `127.0.0.1`; every compose port is published on `127.0.0.1`.
- Production is the default mode: no variable selects it, and a missing required variable fails at startup.
- `apps/demo/` is reached only through `INSTALLED_APPS` (added when the folder exists) and the
  `include_if_present` template tag. No other module imports `apps.demo`.
- Default host ports: app **8000**, Mailpit UI **8025**, PostgreSQL **5433**, storage **9000**, overridable with
  `APP_PORT`, `MAIL_PORT`, `DB_PORT`, `STORAGE_PORT`.
- The explore secret key starts with `explore-only-`; production refuses any key with that prefix.
- Pin every image and dependency to an exact current version, checked on the day; record the versions in `STATE.md`.
- Python file edits from scripts use `encoding="utf-8"`.

## Review Focus

1. **A developer's own `.env` is present when they run `docker compose up`.** It must not leak into the container (it
   points at `localhost:5433` with `DEBUG=true`). Task 6 pins `.dockerignore` excluding `.env` and `.env.*`.
2. **Port 8000 is already taken.** `APP_PORT=8123 docker compose up` must work and print the right URL. Task 6's smoke
   run and Task 7's CI job use 8123.
3. **Second and later runs.** `prepare` runs on every start, so it must be idempotent. Task 4 calls it twice; Task 6
   restarts `web` and checks health again.
4. **A Windows checkout.** Git may hand the entrypoint script CRLF or drop its executable bit. Task 6 asserts there is no
   `\r` in `docker/entrypoint.sh` and that the `Dockerfile` runs it through `sh`.
5. **A self-hoster reuses the explore secret key or leaves the kit on in production.** Startup must refuse. Task 2
   tests both.

---

### Task 1: Spec revision 4

**Files:**
- Modify: `docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md`

- [ ] **Step 1: Apply the revision.** Make every change in the design's §12, using the design's wording:
  - Add a `Revision: 4 (2026-10-30)` line pointing at the design doc.
  - Rewrite §1 goal 7 and the non-goals.
  - Make the §2 table rows provider-neutral, and change "Deliberately absent" to "an outbox plus a worker loop".
  - Reword the §7 constraints.
  - Replace §9's cron with the `cleanup` / `send_outbox` commands run by the worker.
  - Delete the §10 preview-database line.
  - Replace §11 with "Running and hosting" (a summary of the design §4–§8, linking to it).
  - Rewrite the §14 variables using the names in Task 2 and Task 5.
  - Replace §15's deploy step with the hosting-path and compose-smoke jobs.
  - In §16: mark M1 historical; add an "M3.5 Open-source packaging" checklist (this plan's tasks); add the demo
    accounts and login notice to M4; add "extend the demo loader" to M5–M11; rewrite M12's production items as the
    hosting checklist.
  - Add design §15's pages: `/about/`, `/cookies/` and `/contact/` in §5, the footer disclaimer, and the two operator
    settings in §14. Move the privacy, terms and help pages from M12 into M3.5.
  - Replace the Vercel rows in §17.
  - Close §18 Q12 and Q13 as obsolete.
  - Add the decision to §19.
- [ ] **Step 2: Verify.** Run `rg -n -i "vercel|neon|resend|R2_|cron" docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md`.
  Expected: hits only in M1's historical entry, the revision line, §19's history and worked-example mentions.
- [ ] **Step 3: Commit.** `git commit -m "docs: spec rev 4 for open-source self-hosting"`

### Task 2: Modes in settings

**Files:**
- Modify: `config/settings.py`, `config/e2e_settings.py`, `config/tests/test_settings.py`, `apps/core/sentry.py` (only
  if it reads Vercel variables)
- Delete: `config/hosts.py`, `config/tests/test_hosts.py`

**Interfaces:**
- Produces settings:
  - `EXPLORE: bool` (env `SCHOLARSYNC_EXPLORE`, default false);
  - `PRODUCTION: bool` (`not DEBUG and not EXPLORE`);
  - `EXPLORE_HOSTS = ["localhost", "127.0.0.1"]`;
  - `KIT_ENABLED` (default `DEBUG or EXPLORE`);
  - `CSRF_TRUSTED_ORIGINS` (env `DJANGO_CSRF_TRUSTED_ORIGINS`, list, default empty).
- HTTPS-only settings follow `PRODUCTION`: `SECURE_SSL_REDIRECT` default, the HSTS seconds and subdomains, and the
  secure session and CSRF cookies.
- Sentry: `environment=env.str("SENTRY_ENVIRONMENT", "production" if PRODUCTION else "local")`,
  `release=env.str("SENTRY_RELEASE", "") or None`.

- [ ] **Step 1: Write the failing tests.** Extend `config/tests/test_settings.py` by generalising the existing
  `_kit_env`/`_kit_enabled` pattern into a helper `settings_values(tmp_path, names, **env) -> dict` that imports
  `config.settings` in a subprocess and prints the named settings as JSON. The new tests and their assertions:
  - `test_explore_mode_is_http_and_localhost_only`: with `SCHOLARSYNC_EXPLORE=true` →
    - `ALLOWED_HOSTS == ["localhost", "127.0.0.1"]`;
    - `SECURE_SSL_REDIRECT is False`, `SECURE_HSTS_SECONDS == 0`;
    - `SESSION_COOKIE_SECURE is False`, `CSRF_COOKIE_SECURE is False`;
    - `KIT_ENABLED is True`, `PRODUCTION is False`.
  - `test_explore_mode_refuses_other_hosts`: `SCHOLARSYNC_EXPLORE=true`, `DJANGO_ALLOWED_HOSTS=scholarsync.example` →
    nonzero exit, `"SCHOLARSYNC_EXPLORE"` in stderr.
  - `test_production_is_the_default_and_https_only`: no mode variables →
    - `PRODUCTION is True`, `SECURE_SSL_REDIRECT is True`;
    - `SECURE_HSTS_SECONDS == 31536000`, `SESSION_COOKIE_SECURE is True`.
  - `test_kit_refuses_to_load_in_production` (rewritten): `DJANGO_KIT=true`, no mode → nonzero, `"DJANGO_KIT"` in
    stderr.
  - `test_kit_allowed_in_explore_and_developer_modes`: `DJANGO_KIT=true` with `SCHOLARSYNC_EXPLORE=true`, then with
    `DJANGO_DEBUG=true` → `KIT_ENABLED is True` both times.
  - `test_production_refuses_the_explore_secret_key`: `DJANGO_SECRET_KEY="explore-only-" + "x" * 40`, no mode →
    nonzero, `"explore"` in stderr; the same key with `SCHOLARSYNC_EXPLORE=true` loads.
  - `test_csrf_trusted_origins_from_env`:
    `DJANGO_CSRF_TRUSTED_ORIGINS=https://a.example,https://b.example` →
    `CSRF_TRUSTED_ORIGINS == ["https://a.example", "https://b.example"]`.
  - Delete the Vercel-preview test and `test_hosts.py`.
- [ ] **Step 2: Run them.** `python -m uv run pytest config/tests -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement the modes in `config/settings.py`.** Remove the `config.hosts` import and every `VERCEL_*`
  read. The error messages are copy the user will see:
  - explore with another host: `"SCHOLARSYNC_EXPLORE only serves localhost and 127.0.0.1. To host ScholarSync, follow docs/HOSTING.md."`
  - kit in production: `"DJANGO_KIT must be off in production. It is for local use only."`
  - explore key in production: `"DJANGO_SECRET_KEY is the public explore key. Set your own secret key for production (docs/HOSTING.md)."`
- [ ] **Step 4: Switch `config/e2e_settings.py` to explore mode.** Set `SCHOLARSYNC_EXPLORE=true` and drop the
  overrides it now makes redundant: `DJANGO_SECURE_SSL_REDIRECT`, `ALLOWED_HOSTS` and the two cookie flags. Keep
  `CSP_REPORT_ONLY=false`, `DJANGO_ALLOW_ASYNC_UNSAFE` and the staticfiles override.
- [ ] **Step 5: Run everything.**
  - `python -m uv run pytest -n auto`: expected PASS.
  - `python -m uv run pytest -m e2e --ds=config.e2e_settings --browser chromium`: expected PASS.
  - `python -m uv run mypy .`: expected clean.
- [ ] **Step 6: Commit.** `git commit -m "feat: add explore and production modes"`

### Task 3: Remove Vercel

**Files:**
- Delete: `vercel.json`, `.vercelignore`, `build.py`, `tests/test_build.py`, `tests/test_deploy_config.py`
- Create: `tests/test_frontend_lock.py` (receives `test_npm_lockfile_includes_linux_native_binaries` unchanged; the
  Docker build runs on linux-x64 too, so update its docstring to say so)
- Create: `tests/test_no_vercel.py`
- Modify: `pyproject.toml` (drop `[tool.vercel]` and `[tool.vercel.scripts]`), `.gitignore` (drop `.vercel/`; keep
  `.env.spike` until Task 11 removes the spike file), `apps/core/logging.py`, `apps/kit/views.py`,
  `apps/kit/tests/test_kit.py`, `conftest.py`, `.github/workflows/ci.yml` (Vercel comments only; the jobs change in
  Task 7)

- [ ] **Step 1: Write the failing test.** `test_no_vercel_references_in_code`: for every path from
  `git ls-files` ending in `.py`, `.toml`, `.yml`, `.yaml`, `.json`, `.ts`, `.html` or `.cfg`, outside `docs/` and
  `frontend/package-lock.json`, assert that `"vercel"` is not in the lowercased text. Fail with the offending paths.
- [ ] **Step 2: Run it.** `python -m uv run pytest tests/test_no_vercel.py -q`. Expected: FAIL, listing `vercel.json`,
  `pyproject.toml`, `build.py` and others.
- [ ] **Step 3: Delete and reword.** Remove the files listed above. Reword the docstrings and comments to be
  host-neutral; for example, the logging formatter becomes "for any log collector reading stdout" and the
  HTTPS client becomes "as every real request does behind a TLS proxy".
- [ ] **Step 4: Verify.** `python -m uv run pytest -n auto`, `ruff check .` and `mypy .`: all PASS.
- [ ] **Step 5: Commit.** `git commit -m "chore: remove Vercel deployment files"`

### Task 4: The demo app and its hook

**Files:**
- Create:
  - `apps/demo/__init__.py`, `apps/demo/apps.py`, `apps/demo/checks.py`, `apps/demo/loader.py`;
  - `apps/demo/management/__init__.py`, `apps/demo/management/commands/__init__.py`,
    `apps/demo/management/commands/load_demo.py`;
  - `apps/demo/tests/__init__.py`, `apps/demo/tests/test_demo.py`.
- Create: `apps/core/templatetags/slots.py`, `apps/core/tests/test_slots.py`
- Modify: `config/settings.py`

**Interfaces:**
- Settings:
  - `DEMO_INSTALLED: bool` is `importlib.util.find_spec("apps.demo") is not None`; when true, `"apps.demo"` is
    appended to `INSTALLED_APPS`;
  - `DEMO_ACTIVE: bool` is `DEMO_INSTALLED and not PRODUCTION`.
- `apps.demo.loader.load() -> int`: creates demo data and returns how many objects it created. It is idempotent. In
  M3.5 it returns `0`; M4 fills it.
- `manage.py load_demo`: raises
  `CommandError("The demo is off in production mode. It only runs locally (docs/SETUP.md).")` unless
  `settings.DEMO_ACTIVE`. Otherwise it prints `Demo data: {n} new objects.`
- A deploy check registered in `DemoConfig.ready()` with `@register(Tags.security, deploy=True)` returns
  `Error("The demo app is still installed.", hint="Delete the apps/demo folder before deploying (docs/HOSTING.md).", id="demo.E001")`.
- `{% load slots %}{% include_if_present "demo/login_notice.html" %}`: renders that template with the current
  context, or `""` when it doesn't exist. Signature:
  `include_if_present(context: Context, template_name: str) -> SafeString` (a `simple_tag(takes_context=True)`).

- [ ] **Step 1: Write the failing tests.**
  - In `apps/core/tests/test_slots.py`:
    - `test_include_if_present_renders_an_existing_template`: point it at an existing small template, for example
      `components/empty_state.html` with a context supplying its variables; assert the output contains that
      template's text.
    - `test_include_if_present_is_empty_for_a_missing_template`: assert the output of
      `Template('{% load slots %}[{% include_if_present "nope/missing.html" %}]').render(Context())` equals `"[]"`.
  - In `apps/demo/tests/test_demo.py`:
    - `test_demo_is_installed_but_inactive_under_test_settings`: `"apps.demo" in settings.INSTALLED_APPS`;
      `settings.DEMO_ACTIVE is False`, because tests run in production mode.
    - `test_load_demo_refuses_in_production`: `pytest.raises(CommandError, match="production")` around
      `call_command("load_demo")`.
    - `test_load_demo_runs_when_active(settings, capsys)`: with `settings.DEMO_ACTIVE = True`,
      `call_command("load_demo")` prints `"Demo data: 0 new objects."`.
    - `test_deploy_check_fails_while_the_demo_is_installed`: `run_checks(include_deployment_checks=True)` contains an
      error with `id == "demo.E001"`.
    - `test_nothing_outside_the_demo_imports_it`: scan every tracked `.py` file outside `apps/demo/` and
      `config/settings.py`; assert that none contains `apps.demo` or `from apps import demo`.
- [ ] **Step 2: Run them.** `python -m uv run pytest apps/demo apps/core/tests/test_slots.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the files and interfaces above.
- [ ] **Step 4: Prove the deletion path.** In a throwaway copy (`git worktree add ../ss-nodemo HEAD`, then delete
  `apps/demo` there), with production env vars set, run `python -m uv run python manage.py check --deploy --fail-level WARNING`
  and `python -m uv run pytest -n auto`. Expected: both PASS. Then remove the worktree.
- [ ] **Step 5: Verify the full suite** in the real tree: `python -m uv run pytest -n auto`. Expected: PASS.
  From here until Task 7, the existing CI python job's `check --deploy` step would fail on `demo.E001`. That is
  expected: nothing is pushed in between, and Task 7 moves the step into the hosting-path job.
- [ ] **Step 6: Commit.** `git commit -m "feat: add the deletable demo app and template slot"`

### Task 5: Runtime commands

**Files:**
- Create:
  - `apps/core/management/__init__.py`, `apps/core/management/commands/__init__.py`;
  - `apps/core/management/commands/prepare.py`, `cleanup.py`, `run_worker.py`;
  - `apps/core/tests/test_commands.py`.
- Modify: `pyproject.toml` and `uv.lock` (add `gunicorn`, latest stable, via `python -m uv add gunicorn`)

**Interfaces:**
- `manage.py prepare` runs, in order:
  1. `migrate --noinput`;
  2. `createcachetable`;
  3. `load_demo`, only when `apps.is_installed("apps.demo") and settings.DEMO_ACTIVE`.

  It then prints `ScholarSync is ready.` It is safe to run on every start.
- `manage.py cleanup` runs `clearsessions` now. M4 adds expired invites and old outbox rows.
- `manage.py run_worker [--interval SECONDS=300] [--once]` calls `cleanup` every interval. `--once` runs one cycle and
  exits. M4 adds `send_outbox` to the cycle.

- [ ] **Step 1: Write the failing tests.**
  - `test_prepare_is_idempotent(db)`: calling `call_command("prepare")` twice raises nothing, and the output contains
    `"ScholarSync is ready."` both times.
  - `test_prepare_loads_the_demo_only_when_active(settings, monkeypatch)`: record the names `call_command` is called
    with inside `prepare`.
    - With `DEMO_ACTIVE = True`: `"load_demo"` is in the list.
    - With `DEMO_ACTIVE = False`: it is not.
  - `test_cleanup_clears_expired_sessions(db)`: create one expired and one live `Session` row; after `cleanup` only
    the live one remains.
  - `test_run_worker_once_runs_cleanup(monkeypatch)`: record the call; assert `cleanup` was called exactly once and the
    command returned.
- [ ] **Step 2: Run them.** `python -m uv run pytest apps/core/tests/test_commands.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the three commands. The worker loop sleeps with `time.sleep(interval)` between cycles and
  exits cleanly on `KeyboardInterrupt`.
- [ ] **Step 4: Verify.** `python -m uv run pytest -n auto` and `mypy .`: both PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat: add prepare, cleanup and worker commands"`

### Task 6: Provider-neutral settings, `.env.example`, Docker and compose

**Files:**
- Modify: `config/settings.py`, `.env.example`, `compose.yaml`
- Create:
  - `Dockerfile`, `.dockerignore`, `docker/entrypoint.sh`, `compose.production.yaml`;
  - `config/tests/test_env_example.py`, `tests/test_docker_files.py`.

**Interfaces:**
- Settings:
  - **Email:** `EMAIL_URL` through `env.dj_email_url("EMAIL_URL", "console://")`, which sets `EMAIL_BACKEND`,
    `EMAIL_HOST` and the rest; `DEFAULT_FROM_EMAIL` (env, default `ScholarSync <no-reply@localhost>`).
  - **Storage:** `S3_STORAGE: dict[str, str]` with keys `endpoint_url`, `public_endpoint_url`, `region`, `bucket`,
    `access_key_id`, `secret_access_key` and `addressing_style`. They come from the env vars `S3_ENDPOINT_URL`,
    `S3_PUBLIC_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` and
    `S3_ADDRESSING_STYLE`, all defaulting to `""` except `addressing_style`, which defaults to `"path"`. M5 consumes
    this dict.
  - **CSP:** the CSP `img-src` and `connect-src` gain the origin (`scheme://host[:port]`) of
    `public_endpoint_url or endpoint_url` when one is set.
- Compose services, as the design §4 table lists: `db`, `storage`, `storage-init` (a one-shot service that creates the
  bucket `scholarsync`, its CORS rule for `http://localhost:${APP_PORT:-8000}` and `http://127.0.0.1:${APP_PORT:-8000}`,
  and a 1-day expiry on the `pending/` prefix; it is idempotent), `mail`, `web` and `worker`.
- **The `web` environment** is set in compose, not from `.env`:
  - `SCHOLARSYNC_EXPLORE=true`, `CSP_REPORT_ONLY=false`;
  - `DJANGO_SECRET_KEY=explore-only-<64 fixed chars>`;
  - `DATABASE_URL=postgres://scholarsync:scholarsync@db:5432/scholarsync`;
  - `EMAIL_URL=smtp://mail:1025`;
  - the `S3_*` values pointing at `storage`, with `S3_PUBLIC_ENDPOINT_URL=http://localhost:${STORAGE_PORT:-9000}`;
  - `APP_PORT=${APP_PORT:-8000}` and `MAIL_PORT=${MAIL_PORT:-8025}`, used only for the ready message.
- `.env.example` also documents `DATABASE_URL_UNPOOLED`, which the entrypoint reads (not settings), and the compose
  ports, so a self-hoster sees them.
- **The `web` service itself:** a healthcheck on `/healthz` through Python's `urllib`, and
  `depends_on: db healthy, storage-init completed successfully, mail started`.
- **The `worker` service:** the same image, command `python manage.py run_worker`, depending on `web` being healthy.
- **Every port** is published as `"127.0.0.1:${X_PORT:-default}:<container port>"`.
- **`docker/entrypoint.sh`** (POSIX `sh`, LF):
  - runs `DATABASE_URL="${DATABASE_URL_UNPOOLED:-$DATABASE_URL}" python manage.py prepare`;
  - when `SCHOLARSYNC_EXPLORE` is true, prints
    `ScholarSync is running: http://localhost:${APP_PORT}  (test accounts: see README.md; email inbox: http://localhost:8025)`,
    using the real mail port;
  - then `exec "$@"`.
- **`Dockerfile`:**
  - stage `frontend`: Node 22 slim, `npm ci`, `npm run build`, producing `static/dist`;
  - stage `app`: Python 3.13 slim with uv copied from its official image, `uv sync --locked --no-dev`, the source, the
    built `static/dist`, and `collectstatic` run with build-only dummy `DJANGO_SECRET_KEY` and `DATABASE_URL` values;
  - a non-root user, `EXPOSE 8000`;
  - `ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]`;
  - `CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]`.
- **`compose.production.yaml`:** `web` and `worker` only, built from `.`, `env_file: .env`, `web` published on
  `${APP_PORT:-8000}` (behind the host's TLS proxy), with the same healthcheck and command.

- [ ] **Step 1: Write the failing tests.**
  - `config/tests/test_env_example.py::test_every_setting_variable_is_documented`: collect every name read in
    `config/settings.py` with the regex `env\.\w+\(\s*"([A-Z0-9_]+)"`, plus `SCHOLARSYNC_EXPLORE`. Assert that each
    one appears as `NAME=` at the start of a line in `.env.example`.
  - `config/tests/test_env_example.py::test_env_example_holds_no_real_secrets`: every `DJANGO_SECRET_KEY`,
    `S3_SECRET_ACCESS_KEY` and `EMAIL_URL` value in `.env.example` is empty or a placeholder containing `change-me`.
  - `config/tests/test_settings.py::test_csp_allows_the_storage_origin`: with
    `S3_PUBLIC_ENDPOINT_URL=http://localhost:9000/`, the CSP directives' `img-src` and `connect-src` contain
    `"http://localhost:9000"`.
  - `config/tests/test_settings.py::test_email_url_configures_smtp`: with `EMAIL_URL=smtp://mail:1025`,
    `EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend"`, `EMAIL_HOST == "mail"` and `EMAIL_PORT == 1025`.
  - `tests/test_docker_files.py`:
    - `test_dockerignore_keeps_secrets_and_local_state_out`: `.dockerignore` lines include `.env`, `.env.*`, `.venv`,
      `frontend/node_modules`, `static/dist`, `staticfiles`, `STATE.md`, `CLAUDE.local.md` and `.git`.
    - `test_entrypoint_is_lf_and_run_through_sh`: `b"\r" not in docker/entrypoint.sh bytes`; the `Dockerfile`
      contains `ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]`.
    - `test_every_compose_port_is_loopback_only`: every `ports` entry in `compose.yaml` starts with `"127.0.0.1:"`.
      Parse the YAML with a small line-based read; there is no new dependency.
- [ ] **Step 2: Run them.** `python -m uv run pytest config/tests tests/test_docker_files.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement the settings and rewrite `.env.example`.** Group it by concern: core, modes, database,
  email, file storage, error tracking and compose ports. Each variable gets a comment saying what it is, whether it is
  required in production, the format, and where to get it. The developer workflow's local values (debug, the
  local database on 5433) sit in a clearly marked "Local development" block at the top. Production values are
  placeholders.
- [ ] **Step 4: Write the Docker files.** Pick and pin a currently maintained S3-compatible image for `storage` and a
  CLI image for `storage-init` (the design leaves the product to the builder). Note the choice in `STATE.md`.
- [ ] **Step 5: Run the unit tests.** `python -m uv run pytest -n auto`: expected PASS.
- [ ] **Step 6: Smoke-run the stack on a non-default port.** Run `$env:APP_PORT="8123"; docker compose up -d --build`,
  then poll `http://127.0.0.1:8123/healthz` until it answers or 180 s pass. Expected:
  - `/healthz` answers `{"ok": true}`;
  - `/` answers 200;
  - `/_kit/` answers 200;
  - `http://127.0.0.1:8025/` (Mailpit) answers 200;
  - `docker compose ps -a storage-init` shows exit code 0;
  - `docker compose port web 8000` prints `127.0.0.1:8123`;
  - `docker compose logs web` contains `ScholarSync is running: http://localhost:8123`.
- [ ] **Step 7: Restart and reset.** `docker compose restart web`, then `/healthz` answers again (review focus 3).
  `docker compose down -v` finishes cleanly.
- [ ] **Step 8: Validate the production file.** Copy `.env.example` to a temp `.env`, then run
  `docker compose -f compose.production.yaml config`. Expected: exit 0. Delete the temp file.
- [ ] **Step 9: Commit.** `git commit -m "feat: run ScholarSync with one docker compose command"`

### Task 7: CI jobs

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Change the jobs.**
  - **python job:** remove the "Deploy checks" step; it moves to the new hosting-path job.
  - **hosting-path job:** a Postgres 17 service, uv and Node setup as in the python job, then the front-end build and
    `rm -rf apps/demo`. Then, with `DJANGO_DEBUG=false`, a CI-only secret key and
    `DJANGO_ALLOWED_HOSTS=scholarsync.example`, run `uv run python manage.py check --deploy --fail-level WARNING`
    followed by `uv run pytest -n auto`.
  - **compose-smoke job:**
    1. `APP_PORT=8123 docker compose up -d --build`;
    2. poll `curl -fsS http://127.0.0.1:8123/healthz` (180 s cap);
    3. `curl -fsS` against `/`, `/_kit/` and `http://127.0.0.1:8025/`;
    4. assert that `docker compose port web 8000` equals `127.0.0.1:8123`;
    5. `cp .env.example .env && docker compose -f compose.production.yaml config -q`;
    6. always `docker compose logs` on failure and `docker compose down -v`.
  - Give every new job `timeout-minutes` and the same top-level read-only permissions.
- [ ] **Step 2: Verify locally.** Task 4 step 4 already proved the hosting-path commands, and Task 6 steps 6–8 proved
  the smoke commands. Re-run the hosting-path pair once in a worktree to confirm the YAML's exact commands. Lint the
  YAML with `docker run --rm -v ${PWD}:/repo rhysd/actionlint:<pinned> -color` (or `uvx` an equivalent). Expected:
  no errors.
- [ ] **Step 3: Commit.** `git commit -m "ci: add hosting-path and compose smoke jobs"`. CI runs only when Kenneth
  pushes; record "CI unconfirmed until push" in `STATE.md`.

### Task 8: Guides

**Files:**
- Modify: `README.md`, `CLAUDE.md`
- Create: `docs/SETUP.md`, `docs/HOSTING.md`

- [ ] **Step 1: Write `README.md`** as the design §10 describes. Until M4 there are no accounts yet, so the test-account
  table says "arrives with sign-in (M4)", and the quick start ends at the home page and the design kit at
  `http://localhost:8000/_kit/`. Keep the status line current. Move the developer workflow out to `docs/SETUP.md`.
- [ ] **Step 2: Write `docs/SETUP.md`** as the design §10 describes. It covers the one-command run, ports
  (`APP_PORT` etc.), stopping, resetting (`docker compose down -v`), the Mailpit inbox, and troubleshooting (Docker not
  running, port in use, slow first build, CRLF). The developer workflow has a changed first command: it starts the
  services only, `docker compose up -d --wait db storage storage-init mail`.
- [ ] **Step 3: Write `docs/HOSTING.md`** as the design §10 describes, in order:
  1. delete `apps/demo/`;
  2. copy `.env.example` to `.env` and fill it in;
  3. optional rebranding (`templates/layouts/` and the favicon);
  4. provision PostgreSQL, S3-compatible storage (private, CORS, the `pending/` lifecycle rule) and SMTP;
  5. `docker compose -f compose.production.yaml up -d --build` behind HTTPS;
  6. the worker, or scheduling `cleanup` on cron;
  7. `manage.py check --deploy`;
  8. after M4: the first scholarship-office account and the optional `seed_programs`;
  9. backups.

  Provider examples are clearly marked as examples.
- [ ] **Step 4: Update `CLAUDE.md`.** Change the stack's Host line, add the file-structure entries (`Dockerfile`,
  `compose.production.yaml`, `docker/`, `apps/demo/`), change the setup command to the services-only compose
  command, and drop the Vercel notes and the Vercel wording in the deploy-check line.
- [ ] **Step 5: Verify from a fresh clone.** `git clone . $env:TEMP\ss-fresh`, then in that clone follow the README
  quick start literally, using `APP_PORT=8124` to avoid a clash. Expected: the home page and the kit load. Then follow
  `docs/HOSTING.md` in the same clone against the explore stack's db, storage and mail containers. Use a `.env` built
  from `.env.example` and send `curl -H "X-Forwarded-Proto: https"` to `/healthz`. Expected: `{"ok": true}`, and
  `check --deploy` is clean. Fix every guide step that didn't work as written. Remove the clone.
- [ ] **Step 6: Commit.** `git commit -m "docs: add quick start, setup and hosting guides"`

### Task 9: Public information pages and the disclaimer

Design §15. These pages lower legal risk but are not legal advice; Task 11 step 3 asks Kenneth to get them reviewed.

**Files:**
- Create:
  - `apps/core/pages.py` (views for the six pages);
  - `templates/core/pages/{about,privacy,terms,cookies,help,contact}.html`;
  - `templates/components/site_footer.html`;
  - `SECURITY.md`;
  - `apps/core/tests/test_pages.py`.
- Modify:
  - `apps/core/urls.py`, `config/settings.py`, `config/test_settings.py`;
  - `templates/layouts/{public,auth,student,app}.html`;
  - `.env.example`, `README.md`, `docs/HOSTING.md`, `compose.production.yaml` (only if it lists variables).

**Interfaces:**
- **URL names:** `core:about`, `core:privacy`, `core:terms`, `core:cookies`, `core:help` and `core:contact`, at
  `/about/`, `/privacy/`, `/terms/`, `/cookies/`, `/help/` and `/contact/`. Each view is `@require_safe` and renders
  its template in the public layout.
- **Settings:**
  - `SITE_OPERATOR_NAME: str` and `PRIVACY_CONTACT_EMAIL: str`, required (`env.str` with no default) in
    production. In explore and developer modes they default to `"This local copy"` and `""`.
  - `PRIVACY_NOTICE_VERSION = "2026-10-30"`, a constant that M4's `ConsentRecord.notice_version` uses and that
    the privacy page shows as "Last updated".
  - `config/test_settings.py` sets both new variables with `os.environ.setdefault` before importing, because tests
    run in production mode.
- **The footer component** is used by all four layouts: links to the six pages, then the disclaimer copy, exactly
  `Independent portfolio project. Not affiliated with or endorsed by the City of Taguig. All sample people and data are fictional.`
- **The explore notice** (privacy page, explore mode only), exactly:
  `This copy runs on your computer. Anything you enter stays in its database, and emails go to the local inbox, not to real people.`

- [ ] **Step 1: Write the failing tests** in `apps/core/tests/test_pages.py` and `config/tests/test_settings.py`:
  - `test_every_information_page_renders` (parametrised over the six URL names): status 200, exactly one `<h1>`, and
    the footer disclaimer present.
  - `test_every_layout_has_the_footer_and_no_affiliation_claim`: render one page per layout, using the kit layout demo
    at `/_kit/layouts/<name>/` with `KIT_ENABLED`. Assert that each has the disclaimer and all six links, and that none
    contains `"ScholarSync is the scholarship platform of the City of Taguig"`.
  - `test_privacy_page_names_the_operator_and_contact(settings)`: with `SITE_OPERATOR_NAME="Example Org"` and
    `PRIVACY_CONTACT_EMAIL="dpo@example.org"`, both strings appear on `/privacy/` and `/contact/`, and
    `"National Privacy Commission"` appears on `/privacy/`.
  - `test_explore_notice_only_in_explore_mode(settings)`: the notice is absent by default, and present with
    `settings.EXPLORE = True`.
  - `test_cookie_notice_lists_every_cookie_the_app_sets(client)`: GET a page that sets the CSRF cookie (any form page,
    for example a kit form, with the kit on). Collect the response's cookie names plus `settings.SESSION_COOKIE_NAME`.
    Assert each name appears on `/cookies/`.
  - `test_production_requires_the_operator_settings` (subprocess, as in Task 2): in production with
    `SITE_OPERATOR_NAME` unset → nonzero exit, and the name appears in stderr. Repeat for `PRIVACY_CONTACT_EMAIL`.
  - `test_no_personal_email_in_repo`: tracked files outside `docs/` contain no email address except `@example.`
    addresses, `@scholarsync.test` and the `noreply@` and `no-reply@` placeholders.
- [ ] **Step 2: Run them.** `python -m uv run pytest apps/core/tests/test_pages.py config/tests -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Write the settings, views, URLs and footer component, and include the footer in the four layouts.
  - Write the six pages' copy to the design §15 table, in plain English, using the components the pages already use.
  - The privacy page cites RA 10173 and lists the rights. Its retention section says how long records are kept "as
    set by the operator of this copy" and asks self-hosters to state their period.
- [ ] **Step 4: Write the repo files.**
  - `SECURITY.md`: report privately through GitHub's private vulnerability reporting, not public issues.
  - The README: the disclaimer under the title, plus links to the pages.
  - `.env.example`: entries for both settings.
  - `docs/HOSTING.md`: the required step from design §15.
- [ ] **Step 5: Verify.**
  - `python -m uv run pytest -n auto` and the e2e suite: both PASS.
  - The pages pass the existing e2e accessibility and CSP checks; add the six URLs to whatever page list those checks
    walk.
  - `docker compose up -d --build`: `/privacy/` shows the explore notice.
- [ ] **Step 6: Commit.** `git commit -m "feat: add privacy, terms, cookies, FAQ, about and contact pages"`

### Task 10 (optional): GitHub Codespaces

Build this only if Tasks 1–9 are done. Stop and report to Kenneth if it needs more than the two changes below.

**Files:**
- Create: `.devcontainer/devcontainer.json`
- Modify: `config/settings.py`, `config/tests/test_settings.py`

- [ ] **Step 1: Write the failing test.** `test_explore_allows_the_codespaces_forwarded_host`: with
  `SCHOLARSYNC_EXPLORE=true`, `CODESPACE_NAME=demo` and
  `GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN=app.github.dev`:
  - `ALLOWED_HOSTS` ends with `"demo-8000.app.github.dev"`;
  - `CSRF_TRUSTED_ORIGINS` contains `"https://demo-8000.app.github.dev"`.
- [ ] **Step 2: Run it**, expecting FAIL; then implement the change in explore mode only, and run it again, expecting
  PASS.
- [ ] **Step 3: Write `devcontainer.json`.** It runs `docker compose up -d --build` on start, forwards 8000 and 8025,
  and labels port 8000 "ScholarSync". Add an "Open in GitHub Codespaces" badge to the README.
- [ ] **Step 4: Verify.** Kenneth opens a codespace from his pushed branch, so this waits for a push. Record it as
  pending in `STATE.md`.
- [ ] **Step 5: Commit.** `git commit -m "feat: open ScholarSync in GitHub Codespaces"`

### Task 11: Publication

This task works through checkpoints with Kenneth. Every outward-facing or history-changing step waits for his explicit
go-ahead at that moment.

- [ ] **Step 1: Scan for secrets.** Run a pinned gitleaks image over the full history:
  `docker run --rm -v ${PWD}:/repo zricethezav/gitleaks:<pinned> git /repo --redact -v`. Scan both `main` and
  `spike/vercel`.
- [ ] **Step 2: Review the content.** Read every tracked document for things not meant for the public:
  - `docs/legacy-audit.md`;
  - the M1 plan (`docs/superpowers/plans/2026-10-12-m1-vercel-spike.md`): spike URLs, account names;
  - every other plan and spec, `CLAUDE.md` and `README.md`.

  List each finding with the file, line and a suggested change.
- [ ] **Step 3: Report to Kenneth** with the scan result and the content findings. Remind him to have a qualified
  person review `/privacy/`, `/terms/` and the disclaimer before the flip. Claude's drafts are not legal advice. Apply the content changes he
  approves as one commit: `docs: prepare documents for publication`.
- [ ] **Step 4: Only if the scan found a secret, and Kenneth says go:**
  1. Kenneth rotates the secret first.
  2. Rewrite history to remove it with `git filter-repo`, run against a fresh mirror clone with a backup of the old one
     kept.
  3. Re-scan the rewritten history.
  4. Force-push `main` (allowed by the design §3 for this case only).
  5. Keep `spike/vercel` local, never pushed.
- [ ] **Step 5: Tear down the spike, after Kenneth confirms.** Remove the M1 Vercel project, the Neon project and the R2
  bucket and its API token, using the CLIs or dashboards. Delete the local `.env.spike` and its `.gitignore` line (commit
  `chore: drop spike leftovers`).
- [ ] **Step 6: Make the repository public.** Kenneth flips it himself, or says "go" and Claude runs
  `gh repo edit Drainsoul/ScholarSyncV2 --visibility public --accept-visibility-change-consequences`. Then check that
  the README renders on GitHub, and record the date in `STATE.md`.
