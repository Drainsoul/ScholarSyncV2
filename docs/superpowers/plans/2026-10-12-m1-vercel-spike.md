# M1 Vercel Go/No-Go Spike Implementation Plan

**Goal:** Prove or reject Vercel as ScholarSync V2's host. A throwaway Django + Vite probe app is deployed to Vercel and
exercises everything the spec relies on. The answer is recorded as a go or no-go.

**Architecture:** One small Django project (`config/` + a `probe` app) on the throwaway branch `spike/vercel`. It has:
- a page rendered with django-vite assets;
- a Vercel build script (Vite → migrate + `createcachetable` on the unpooled URL);
- token-protected probe endpoints: runtime and cold start, client IP, database, cron, email;
- an R2 presigned upload/confirm/download flow.

Tasks 1–5 are built and tested locally: Postgres in Docker, moto as the S3 stand-in, the console email backend. Task 6
is creating the external accounts. Task 7 deploys and measures.

**Tech Stack:**
- Python 3.13 (uv 0.13), Django 5.2.18, environs 15.2 (+ dj-database-url), psycopg 3.3;
- django-vite 3.2, whitenoise 6.12, django-allauth 65.19.7, django-anymail 15.2 (Resend);
- boto3 1.43, filetype 1.2;
- pytest 9.1 + pytest-django 4.14, moto 5.2 (server mode), ruff 0.17;
- Vite 8.3 + TypeScript 7.0; Vercel CLI 63.1.

**Spec:** `docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md` (§11 Vercel deployment, §7 Files, §9 Email/cron,
§16 M1 checklist).

## Global Constraints
- Python `>=3.13,<3.14`; Django `>=5.2.18,<5.3` (5.2 LTS).
- Vercel region `sin1`; a Neon database in Singapore.
- Database at runtime: `CONN_MAX_AGE=0`, `CONN_HEALTH_CHECKS=True`, `DISABLE_SERVER_SIDE_CURSORS=True`.
- Migrations and `createcachetable` run in the build against `DATABASE_URL_UNPOOLED` (falling back to `DATABASE_URL`
  when it's unset).
- Files never pass through Django:
  - presigned PUT signs `Content-Type` and `Content-Length` and targets `pending/`;
  - confirm sniffs the first 4 KB and copies the object to `files/`;
  - downloads are presigned GETs with `ResponseContentDisposition=attachment`, valid for 5 minutes.
- Allowed upload types are `application/pdf`, `image/jpeg` and `image/png`, at most 10 MB. Never SVG or HTML.
- Every probe endpoint except `/healthz` and `/` requires a bearer token compared with `hmac.compare_digest`. An empty
  configured secret means **deny**, never allow.
- **Secrets:**
  - never commit secrets; `.env.example` has placeholders only;
  - the maintainer enters real keys himself (Vercel dashboard or `vercel env add`) and never prints them.
- **Git:**
  - this plan is committed to `main`; all spike code is committed to `spike/vercel` only;
  - nothing is pushed to GitHub;
  - Conventional Commits.
- Windows: run uv as `python -m uv …` (uv isn't on PATH) and use PowerShell 5.1 syntax (no `&&`; use `;` or separate
  commands).

## Review Focus
1. **Mismatched upload content:** a file declared as one type but containing another (a `.txt` renamed `.pdf`) must be
   rejected at confirm, and its `pending/` object deleted. *Test:* Task 5 `test_confirm_rejects_mismatched_content`.
2. **Escaping the bucket prefixes:** a confirm key outside `pending/`, or a download key outside `files/` (including
   `..`), must be refused (400). *Test:* Task 5 `test_confirm_rejects_key_outside_pending` and
   `test_download_rejects_key_outside_files`.
3. **Empty secret:** with `CRON_SECRET` or `SPIKE_TOKEN` unset (empty), every protected endpoint must return 403, never
   200. *Test:* Task 4 `test_empty_secret_denies`.
4. **No unpooled URL:** a build without `DATABASE_URL_UNPOOLED` must migrate with `DATABASE_URL`, not crash or migrate
   nothing. *Test:* Task 3 `test_migration_env_falls_back_to_pooled_url`.
5. **Wrong upload size:** a browser PUT with a different size from the intent must fail at R2 (signature mismatch).
   moto doesn't verify signatures, so this is *checked live*: Task 7, step 7.

---

### Task 1: Spike skeleton, settings, health check

**Files:**
- Create: `pyproject.toml`, `uv.lock` (generated), `.python-version`, `.gitattributes`, `manage.py`
- Create: `config/__init__.py`, `config/settings.py`, `config/hosts.py`, `config/urls.py`, `config/wsgi.py`
- Create: `probe/__init__.py`, `probe/apps.py`, `probe/views.py`, `probe/urls.py`, `probe/tests/__init__.py`
- Create: `compose.yaml`, `.env.example`, `conftest.py`
- Modify: `.gitignore` (append build and local folders)
- Test: `probe/tests/test_health.py`, `config/tests/test_hosts.py` (+ `config/tests/__init__.py`)

**Interfaces:**
- Produces:
  - `config.hosts.vercel_hosts(environ: Mapping[str, str]) -> list[str]`;
  - `probe.views.healthz(request) -> JsonResponse` at `/healthz`, returning `{"ok": true}` and status 200 when the
    database answers.

- [ ] **Step 1: Create the branch and start Docker**

```powershell
git switch -c spike/vercel
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
```
Wait until `docker info --format '{{.ServerVersion}}'` prints a version (Docker Desktop takes about 30–60 s).

- [ ] **Step 2: Write `pyproject.toml`, `.python-version`, `.gitattributes`, then lock**

`pyproject.toml`:
```toml
[project]
name = "scholarsync"
version = "0.0.0"
description = "ScholarSync V2 (M1 Vercel spike)"
requires-python = ">=3.13,<3.14"
dependencies = [
    "django>=5.2.18,<5.3",
    "environs[django]>=15.2",
    "psycopg[binary]>=3.3.6",
    "django-vite>=3.2",
    "whitenoise>=6.12",
    "django-allauth>=65.19.7",
    "django-anymail[resend]>=15.2",
    "boto3>=1.43",
    "filetype>=1.2",
]

[dependency-groups]
dev = [
    "pytest>=9.1",
    "pytest-django>=4.14",
    "moto[s3,server]>=5.2",
    "requests>=2.34",
    "ruff>=0.17",
]

[tool.vercel]
entrypoint = "config.wsgi:application"

[tool.vercel.scripts]
build = "python build.py"

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
python_files = ["test_*.py"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "S", "DJ"]
ignore = ["S101"]
```

`.python-version`:
```
3.13
```

`.gitattributes`:
```
* text=auto eol=lf
*.png binary
*.jpg binary
*.pdf binary
```

Run: `python -m uv lock` then `python -m uv sync`
Expected: `uv.lock` is created and `.venv/` holds Django 5.2.18.

- [ ] **Step 3: Append to `.gitignore`**

```
# Build output and local tooling
static/dist/
staticfiles/
frontend/node_modules/
.vercel/
.env.local
```

- [ ] **Step 4: Write the failing tests**

`config/tests/test_hosts.py`:
```python
from config.hosts import vercel_hosts


def test_vercel_hosts_collects_set_values_in_order():
    environ = {
        "VERCEL_URL": "spike-abc.vercel.app",
        "VERCEL_BRANCH_URL": "",
        "VERCEL_PROJECT_PRODUCTION_URL": "<spike-project>.vercel.app",
    }
    assert vercel_hosts(environ) == ["spike-abc.vercel.app", "<spike-project>.vercel.app"]


def test_vercel_hosts_empty_outside_vercel():
    assert vercel_hosts({}) == []
```

`probe/tests/test_health.py`:
```python
import pytest


@pytest.mark.django_db
def test_healthz_reports_database_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
```

Also create empty `config/tests/__init__.py` and `probe/tests/__init__.py`.

- [ ] **Step 5: Run the tests and confirm they fail**

Run: `python -m uv run pytest`
Expected: FAIL (`ModuleNotFoundError: No module named 'config'`).

- [ ] **Step 6: Write the project files**

`manage.py`:
```python
#!/usr/bin/env python
import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

`config/__init__.py`: empty.

`config/hosts.py`:
```python
from collections.abc import Mapping

VERCEL_HOST_VARIABLES = ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL")


def vercel_hosts(environ: Mapping[str, str]) -> list[str]:
    """Hostnames Vercel assigns to this deployment, in a stable order."""
    return [host for name in VERCEL_HOST_VARIABLES if (host := environ.get(name, ""))]
```

`config/settings.py`:
```python
import os
from pathlib import Path

from environs import Env

from config.hosts import vercel_hosts

BASE_DIR = Path(__file__).resolve().parent.parent

env = Env()
env.read_env(str(BASE_DIR / ".env"), recurse=False)

DEBUG = env.bool("DJANGO_DEBUG", False)
SECRET_KEY = env.str("DJANGO_SECRET_KEY")

_vercel = vercel_hosts(os.environ)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", []) + _vercel
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in _vercel]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_vite",
    "allauth",
    "allauth.account",
    "anymail",
    "probe",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.dj_db_url("DATABASE_URL", conn_max_age=0, conn_health_checks=True),
}
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DJANGO_VITE = {
    "default": {
        "dev_mode": env.bool("VITE_DEV_MODE", False),
        "manifest_path": BASE_DIR / "static" / "dist" / ".vite" / "manifest.json",
        "static_url_prefix": "dist",
    }
}

ALLAUTH_TRUSTED_CLIENT_IP_HEADER = env.str("ALLAUTH_TRUSTED_CLIENT_IP_HEADER", "") or None

EMAIL_BACKEND = env.str("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
ANYMAIL = {"RESEND_API_KEY": env.str("RESEND_API_KEY", "")}
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", "ScholarSync <onboarding@resend.dev>")

R2_ENDPOINT_URL = env.str("R2_ENDPOINT_URL", "")
R2_ACCESS_KEY_ID = env.str("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = env.str("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = env.str("R2_BUCKET", "")
R2_REGION = env.str("R2_REGION", "auto")

SPIKE_TOKEN = env.str("SPIKE_TOKEN", "")
CRON_SECRET = env.str("CRON_SECRET", "")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
```

`config/wsgi.py`:
```python
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
```

`config/urls.py`:
```python
from django.urls import include, path

urlpatterns = [
    path("", include("probe.urls")),
]
```

`probe/__init__.py`: empty.

`probe/apps.py`:
```python
from django.apps import AppConfig


class ProbeConfig(AppConfig):
    name = "probe"
    default_auto_field = "django.db.models.BigAutoField"
```

`probe/views.py`:
```python
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"ok": True})
```

`probe/urls.py`:
```python
from django.urls import path

from probe import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
]
```

`compose.yaml`:
```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_USER: scholarsync
      POSTGRES_PASSWORD: scholarsync
      POSTGRES_DB: scholarsync
    ports:
      - "5432:5432"
    volumes:
      - db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U scholarsync -d scholarsync"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  db-data:
```

`.env.example`:
```
# Copy to .env for local development. Never put real secrets here.
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=local-dev-only-not-a-secret
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
# Local Postgres from compose.yaml (development credentials only)
DATABASE_URL=postgres://scholarsync:scholarsync@localhost:5432/scholarsync
DATABASE_URL_UNPOOLED=
VITE_DEV_MODE=false
ALLAUTH_TRUSTED_CLIENT_IP_HEADER=
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
RESEND_API_KEY=
DEFAULT_FROM_EMAIL=ScholarSync <onboarding@resend.dev>
R2_ENDPOINT_URL=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=
R2_REGION=auto
SPIKE_TOKEN=
CRON_SECRET=
```

`conftest.py` (repo root):
```python
import pytest


@pytest.fixture(autouse=True)
def _plain_static_storage(settings):
    """Tests don't run collectstatic, so the manifest storage would fail on {% static %}."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
```

- [ ] **Step 7: Start Postgres, create `.env`, run the tests**

```powershell
docker compose up -d --wait
Copy-Item .env.example .env
python -m uv run pytest
```
Expected: 3 passed.

- [ ] **Step 8: Lint and run Django's checks**

Run: `python -m uv run ruff check .` then `python -m uv run python manage.py check`
Expected: `All checks passed!` and `System check identified no issues (0 silenced).`

- [ ] **Step 9: Commit**

```powershell
git add pyproject.toml uv.lock .python-version .gitattributes .gitignore manage.py config probe compose.yaml .env.example conftest.py
git commit -m "chore(spike): add Django skeleton with health check"
```

---

### Task 2: Vite front end rendered through django-vite

**Files:**
- Create: `frontend/package.json`, `frontend/package-lock.json` (generated), `frontend/tsconfig.json`,
  `frontend/vite.config.ts`, `frontend/src/main.ts`, `frontend/src/style.css`
- Create: `templates/probe/index.html`
- Modify: `probe/views.py` (add `index`), `probe/urls.py`, `conftest.py` (build fixture)
- Test: `probe/tests/test_index.py`

**Interfaces:**
- Consumes: settings `DJANGO_VITE["default"]` from Task 1 (manifest at `static/dist/.vite/manifest.json`, prefix
  `dist`).
- Produces:
  - `probe.views.index` at `/`;
  - Vite entries `src/main.ts` (and, from Task 5, `src/upload.ts`);
  - npm scripts `build` and `dev`;
  - pytest fixture `vite_build` (session).

- [ ] **Step 1: Write the failing test**

`probe/tests/test_index.py`:
```python
import pytest


@pytest.mark.django_db
def test_index_links_hashed_vite_assets(client, vite_build):
    response = client.get("/")
    body = response.content.decode()
    assert response.status_code == 200
    assert '<script type="module"' in body
    assert "/static/dist/assets/main-" in body
    assert ".css" in body
```

Add to `conftest.py`:
```python
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "static" / "dist" / ".vite" / "manifest.json"


@pytest.fixture(scope="session")
def vite_build() -> Path:
    """Build the front end once per test session so django-vite has a real manifest."""
    if not MANIFEST.exists():
        npm = shutil.which("npm")
        assert npm, "npm is required to build the front end for tests"
        subprocess.run([npm, "--prefix", "frontend", "run", "build"], check=True, cwd=ROOT)  # noqa: S603
    return MANIFEST
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python -m uv run pytest probe/tests/test_index.py`
Expected: FAIL (the npm build fails because `frontend/package.json` doesn't exist).

- [ ] **Step 3: Write the front end**

`frontend/package.json`:
```json
{
  "name": "scholarsync-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "typecheck": "tsc --noEmit"
  },
  "devDependencies": {
    "typescript": "7.0.2",
    "vite": "8.3.4"
  }
}
```

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "types": ["vite/client"],
    "skipLibCheck": true,
    "noEmit": true
  },
  "include": ["src", "vite.config.ts"]
}
```

`frontend/vite.config.ts`:
```ts
import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/static/dist/",
  build: {
    outDir: resolve(__dirname, "../static/dist"),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, "src/main.ts"),
      },
    },
  },
  server: { origin: "http://localhost:5173" },
});
```

`frontend/src/style.css`:
```css
:root {
  --brand-600: #d10e0f;
  --ink: #111827;
  --paper: #f9fafb;
}

body {
  margin: 0;
  padding: 2rem;
  font-family: system-ui, sans-serif;
  color: var(--ink);
  background: var(--paper);
}

h1 {
  color: var(--brand-600);
}
```

`frontend/src/main.ts`:
```ts
import "./style.css";

const marker = document.querySelector<HTMLElement>("[data-js-status]");
if (marker) {
  marker.textContent = "JavaScript bundle loaded.";
}
```

`templates/probe/index.html`:
```html
{% load django_vite %}<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ScholarSync spike</title>
  {% vite_hmr_client %}
  {% vite_asset 'src/main.ts' %}
</head>
<body>
  <main>
    <h1>ScholarSync V2: Vercel spike</h1>
    <p data-js-status>JavaScript bundle not loaded.</p>
  </main>
</body>
</html>
```

Add to `probe/views.py`:
```python
from django.shortcuts import render


@require_GET
def index(request: HttpRequest):
    return render(request, "probe/index.html")
```

Add to `probe/urls.py` `urlpatterns`:
```python
    path("", views.index, name="index"),
```

- [ ] **Step 4: Install, build, test**

```powershell
npm --prefix frontend install
npm --prefix frontend run typecheck
python -m uv run pytest
```
Expected: the typecheck exits 0; 4 passed.

- [ ] **Step 5: Prove collectstatic works with the manifest storage**

Run: `python -m uv run python manage.py collectstatic --noinput`
Expected: `… static files copied to '…\staticfiles', … post-processed.` It creates `staticfiles/staticfiles.json` and
copies `staticfiles/dist/assets/main-*.js`.

- [ ] **Step 6: Commit**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/src templates probe conftest.py
git commit -m "feat(spike): render Vite assets through django-vite"
```

---

### Task 3: Vercel build script and project config

**Files:**
- Create: `build.py`, `vercel.json`
- Test: `tests/test_build.py` (+ `tests/__init__.py`)

**Interfaces:**
- Consumes: npm scripts from Task 2; `manage.py` from Task 1.
- Produces:
  - `build.steps(npm: str, python: str) -> list[list[str]]`;
  - `build.migration_env(environ: Mapping[str, str]) -> dict[str, str]`;
  - `build.main() -> int`.

- [ ] **Step 1: Write the failing tests**

`tests/test_build.py`:
```python
import build


def test_steps_build_frontend_then_migrate_then_cache_table():
    assert build.steps("npm", "py") == [
        ["npm", "--prefix", "frontend", "ci"],
        ["npm", "--prefix", "frontend", "run", "build"],
        ["py", "manage.py", "migrate", "--noinput"],
        ["py", "manage.py", "createcachetable"],
    ]


def test_migration_env_prefers_unpooled_url():
    env = build.migration_env(
        {"DATABASE_URL": "postgres://pooled", "DATABASE_URL_UNPOOLED": "postgres://direct"}
    )
    assert env["DATABASE_URL"] == "postgres://direct"


def test_migration_env_falls_back_to_pooled_url():
    env = build.migration_env({"DATABASE_URL": "postgres://pooled", "DATABASE_URL_UNPOOLED": ""})
    assert env["DATABASE_URL"] == "postgres://pooled"
```
Also create an empty `tests/__init__.py`.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m uv run pytest tests/test_build.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'build'`).

- [ ] **Step 3: Write `build.py` and `vercel.json`**

`build.py`:
```python
"""Vercel build step: build the front end, then migrate on the unpooled database URL.

Vercel runs this after installing Python dependencies (pyproject `[tool.vercel.scripts] build`).
It also prints whether `staticfiles/` already exists, which tells the spike whether Vercel's
automatic collectstatic runs before or after this script.
"""

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def steps(npm: str, python: str) -> list[list[str]]:
    return [
        [npm, "--prefix", "frontend", "ci"],
        [npm, "--prefix", "frontend", "run", "build"],
        [python, "manage.py", "migrate", "--noinput"],
        [python, "manage.py", "createcachetable"],
    ]


def migration_env(environ: Mapping[str, str]) -> dict[str, str]:
    env = dict(environ)
    unpooled = env.get("DATABASE_URL_UNPOOLED", "")
    if unpooled:
        env["DATABASE_URL"] = unpooled
    return env


def main() -> int:
    print(f"build: staticfiles present at start = {(ROOT / 'staticfiles').exists()}", flush=True)
    npm = shutil.which("npm") or "npm"
    env = migration_env(os.environ)
    for command in steps(npm, sys.executable):
        print("build: running", " ".join(command[1:]), flush=True)
        subprocess.run(command, check=True, cwd=ROOT, env=env)  # noqa: S603
    manifest = ROOT / "static" / "dist" / ".vite" / "manifest.json"
    print(f"build: vite manifest present = {manifest.exists()}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`vercel.json`:
```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "regions": ["sin1"],
  "functions": {
    "config/wsgi.py": {
      "maxDuration": 30,
      "includeFiles": "static/dist/.vite/manifest.json",
      "excludeFiles": "{frontend/node_modules/**,frontend/src/**,tests/**,**/tests/**,compose.yaml}"
    }
  },
  "crons": [{ "path": "/_cron/ping/", "schedule": "0 1 * * *" }]
}
```

- [ ] **Step 4: Run the tests**

Run: `python -m uv run pytest`
Expected: 7 passed.

- [ ] **Step 5: Run the build script for real against local Postgres**

Run: `python -m uv run python build.py`
Expected, in order:
1. `build: staticfiles present at start = True` (Task 2 collected locally; on Vercel this line is the measurement);
2. npm ci and the Vite build;
3. `Applying …` migrations or `No migrations to apply.`;
4. `createcachetable` silent;
5. `build: vite manifest present = True`.

- [ ] **Step 6: Commit**

```powershell
git add build.py vercel.json tests
git commit -m "feat(spike): add Vercel build script and project config"
```

---

### Task 4: Runtime, client-IP, cron and email probes

**Files:**
- Create: `probe/auth.py`
- Modify: `probe/views.py`, `probe/urls.py`
- Test: `probe/tests/test_auth.py`, `probe/tests/test_probes.py`

**Interfaces:**
- Consumes: settings `SPIKE_TOKEN`, `CRON_SECRET`, `ALLAUTH_TRUSTED_CLIENT_IP_HEADER` from Task 1.
- Produces:
  - `probe.auth.bearer_matches(request: HttpRequest, secret: str) -> bool`;
  - `probe.auth.require_token(setting_name: str)`: a view decorator returning 403 unless the bearer matches
    `getattr(settings, setting_name)`;
  - JSON endpoints:
    - `GET /probe/runtime/` (keys `started_at`, `uptime_s`, `request_no`, `vercel_env`, `vercel_region`, `db_host`,
      `db_ms`, `last_cron`);
    - `GET /probe/ip/` (keys `remote_addr`, `x_forwarded_for`, `x_real_ip`, `x_vercel_forwarded_for`,
      `allauth_client_ip`);
    - `POST /probe/email/` (form field `to`; returns `{"sent": int, "message_id": str | null}`);
    - `GET /_cron/ping/` (`{"ok": true}`).

- [ ] **Step 1: Write the failing tests**

`probe/tests/test_auth.py`:
```python
from django.test import RequestFactory

from probe.auth import bearer_matches


def test_bearer_matches_exact_token():
    request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer s3cret")
    assert bearer_matches(request, "s3cret")


def test_bearer_rejects_wrong_or_missing_token():
    factory = RequestFactory()
    assert not bearer_matches(factory.get("/", HTTP_AUTHORIZATION="Bearer nope"), "s3cret")
    assert not bearer_matches(factory.get("/"), "s3cret")


def test_bearer_rejects_everything_when_secret_empty():
    request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer ")
    assert not bearer_matches(request, "")
```

`probe/tests/test_probes.py`:
```python
import pytest
from django.core import mail

TOKEN = {"HTTP_AUTHORIZATION": "Bearer spike-token"}
CRON = {"HTTP_AUTHORIZATION": "Bearer cron-secret"}


@pytest.fixture(autouse=True)
def _secrets(settings):
    settings.SPIKE_TOKEN = "spike-token"
    settings.CRON_SECRET = "cron-secret"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.mark.django_db
def test_runtime_reports_process_and_database(client):
    first = client.get("/probe/runtime/", **TOKEN).json()
    second = client.get("/probe/runtime/", **TOKEN).json()
    assert second["request_no"] == first["request_no"] + 1
    assert second["started_at"] == first["started_at"]
    assert first["db_ms"] >= 0
    assert "db_host" in first


def test_ip_reports_headers_and_allauth_view(client, settings):
    settings.ALLAUTH_TRUSTED_CLIENT_IP_HEADER = "x-real-ip"
    body = client.get(
        "/probe/ip/", HTTP_X_REAL_IP="203.0.113.7", HTTP_X_FORWARDED_FOR="203.0.113.7", **TOKEN
    ).json()
    assert body["x_real_ip"] == "203.0.113.7"
    assert body["allauth_client_ip"] == "203.0.113.7"


@pytest.mark.django_db
def test_cron_ping_records_last_run(client):
    assert client.get("/_cron/ping/", **CRON).json() == {"ok": True}
    assert client.get("/probe/runtime/", **TOKEN).json()["last_cron"] is not None


@pytest.mark.django_db
def test_email_probe_sends_one_message(client):
    response = client.post("/probe/email/", {"to": "kenneth@example.com"}, **TOKEN)
    assert response.json()["sent"] == 1
    assert mail.outbox[0].to == ["kenneth@example.com"]


def test_email_probe_requires_recipient(client):
    assert client.post("/probe/email/", {}, **TOKEN).status_code == 400


@pytest.mark.parametrize(
    ("method", "path", "headers"),
    [
        ("get", "/probe/runtime/", {"HTTP_AUTHORIZATION": "Bearer wrong"}),
        ("get", "/probe/ip/", {}),
        ("post", "/probe/email/", {"HTTP_AUTHORIZATION": "Bearer cron-secret"}),
        ("get", "/_cron/ping/", TOKEN),
    ],
)
def test_wrong_token_denies(client, method, path, headers):
    assert getattr(client, method)(path, **headers).status_code == 403


@pytest.mark.parametrize("path", ["/probe/runtime/", "/_cron/ping/"])
def test_empty_secret_denies(client, settings, path):
    settings.SPIKE_TOKEN = ""
    settings.CRON_SECRET = ""
    assert client.get(path, HTTP_AUTHORIZATION="Bearer ").status_code == 403
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m uv run pytest probe/tests/test_auth.py probe/tests/test_probes.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'probe.auth'`).

- [ ] **Step 3: Implement**

`probe/auth.py`:
```python
import hmac
from collections.abc import Callable
from functools import wraps

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden


def bearer_matches(request: HttpRequest, secret: str) -> bool:
    """True only for `Authorization: Bearer <secret>` with a non-empty configured secret."""
    if not secret:
        return False
    header = request.headers.get("Authorization", "")
    return hmac.compare_digest(header.encode(), f"Bearer {secret}".encode())


def require_token(setting_name: str) -> Callable:
    def decorator(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(view)
        def wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if not bearer_matches(request, getattr(settings, setting_name)):
                return HttpResponseForbidden()
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
```

Replace `probe/views.py` with:
```python
import itertools
import os
import time
from datetime import UTC, datetime

from allauth.account.adapter import get_adapter
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from probe.auth import require_token

STARTED_AT = datetime.now(UTC).isoformat()
_STARTED_MONOTONIC = time.monotonic()
_REQUEST_COUNTER = itertools.count(1)
LAST_CRON_KEY = "probe:last_cron"


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"ok": True})


@require_GET
def index(request: HttpRequest):
    return render(request, "probe/index.html")


@require_GET
@require_token("SPIKE_TOKEN")
def runtime(request: HttpRequest) -> JsonResponse:
    started = time.perf_counter()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    db_ms = round((time.perf_counter() - started) * 1000, 2)
    return JsonResponse(
        {
            "started_at": STARTED_AT,
            "uptime_s": round(time.monotonic() - _STARTED_MONOTONIC, 2),
            "request_no": next(_REQUEST_COUNTER),
            "vercel_env": os.environ.get("VERCEL_ENV", "local"),
            "vercel_region": os.environ.get("VERCEL_REGION", "local"),
            "db_host": connection.settings_dict.get("HOST", ""),
            "db_ms": db_ms,
            "last_cron": cache.get(LAST_CRON_KEY),
        }
    )


@require_GET
@require_token("SPIKE_TOKEN")
def client_ip(request: HttpRequest) -> JsonResponse:
    try:
        allauth_ip: str | None = get_adapter(request).get_client_ip(request)
    except Exception as exc:  # the probe reports the failure instead of hiding it
        allauth_ip = f"error: {type(exc).__name__}"
    return JsonResponse(
        {
            "remote_addr": request.META.get("REMOTE_ADDR"),
            "x_forwarded_for": request.headers.get("X-Forwarded-For"),
            "x_real_ip": request.headers.get("X-Real-Ip"),
            "x_vercel_forwarded_for": request.headers.get("X-Vercel-Forwarded-For"),
            "allauth_client_ip": allauth_ip,
        }
    )


@csrf_exempt  # bearer-token API, no cookies involved
@require_POST
@require_token("SPIKE_TOKEN")
def send_test_email(request: HttpRequest) -> JsonResponse:
    to = request.POST.get("to", "").strip()
    if not to:
        return JsonResponse({"error": "missing 'to'"}, status=400)
    message = EmailMessage(
        subject="ScholarSync spike: email probe",
        body="If you can read this, Resend delivery from Vercel works.",
        to=[to],
    )
    sent = message.send()
    status = getattr(message, "anymail_status", None)
    return JsonResponse({"sent": sent, "message_id": getattr(status, "message_id", None)})


@require_GET
@require_token("CRON_SECRET")
def cron_ping(request: HttpRequest) -> JsonResponse:
    cache.set(LAST_CRON_KEY, datetime.now(UTC).isoformat(), None)
    return JsonResponse({"ok": True})
```

Replace `probe/urls.py` with:
```python
from django.urls import path

from probe import views

urlpatterns = [
    path("", views.index, name="index"),
    path("healthz", views.healthz, name="healthz"),
    path("probe/runtime/", views.runtime, name="probe-runtime"),
    path("probe/ip/", views.client_ip, name="probe-ip"),
    path("probe/email/", views.send_test_email, name="probe-email"),
    path("_cron/ping/", views.cron_ping, name="cron-ping"),
]
```

The cron test needs the cache table, so `conftest.py` gains an autouse database-cache fixture:
```python
@pytest.fixture(autouse=True)
def _cache_table(request):
    """Create the DatabaseCache table in the test database for tests that use the DB."""
    if "django_db" in request.keywords:
        from django.core.management import call_command

        request.getfixturevalue("db")
        call_command("createcachetable", verbosity=0)
```

- [ ] **Step 4: Run all tests and lint**

Run: `python -m uv run pytest` then `python -m uv run ruff check .`
Expected: 21 passed; `All checks passed!`

- [ ] **Step 5: Commit**

```powershell
git add probe conftest.py
git commit -m "feat(spike): add runtime, client-IP, cron and email probes"
```

---

### Task 5: R2 presigned upload, confirm and download probe

**Files:**
- Create: `probe/storage.py`, `probe/tests/conftest.py`, `templates/probe/upload.html`, `frontend/src/upload.ts`
- Modify: `probe/views.py`, `probe/urls.py`, `frontend/vite.config.ts` (second entry)
- Test: `probe/tests/test_storage.py`, `probe/tests/test_file_views.py`

**Interfaces:**
- Consumes: settings `R2_*`, `SPIKE_TOKEN`; `probe.auth.require_token` (Task 4).
- Produces (`probe/storage.py`):
  - `ALLOWED_TYPES: dict[str, str]` (MIME → extension), `MAX_BYTES = 10 * 1024 * 1024`;
  - `class UploadRejected(ValueError)`;
  - `@dataclass(frozen=True) class UploadIntent: key: str; url: str; headers: dict[str, str]`;
  - `create_intent(*, content_type: str, size: int) -> UploadIntent`;
  - `confirm_upload(*, key: str, content_type: str, size: int) -> str` (returns the final `files/…` key);
  - `download_url(*, key: str, filename: str) -> str`.
- Endpoints, all requiring the `SPIKE_TOKEN` bearer:
  - `POST /probe/files/intent/` (JSON `{content_type, size}` → `{key, url, headers}`);
  - `POST /probe/files/confirm/` (JSON `{key, content_type, size}` → `{key}`);
  - `GET /probe/files/download/?key=&name=` (302);
  - `GET /probe/upload/` page: the token is entered in the page itself, never placed in the URL.

- [ ] **Step 1: Write the moto fixture and the failing storage tests**

`probe/tests/conftest.py`:
```python
import boto3
import pytest
from moto.server import ThreadedMotoServer

BUCKET = "scholarsync-test"


@pytest.fixture(scope="session")
def s3_endpoint():
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    yield f"http://{host}:{port}"
    server.stop()


@pytest.fixture
def bucket(s3_endpoint, settings):
    settings.R2_ENDPOINT_URL = s3_endpoint
    settings.R2_ACCESS_KEY_ID = "test"
    settings.R2_SECRET_ACCESS_KEY = "test"  # noqa: S105 - moto fake credential
    settings.R2_BUCKET = BUCKET
    settings.R2_REGION = "us-east-1"
    s3 = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",  # noqa: S106
        region_name="us-east-1",
    )
    s3.create_bucket(Bucket=BUCKET)
    yield s3
    for item in s3.list_objects_v2(Bucket=BUCKET).get("Contents", []):
        s3.delete_object(Bucket=BUCKET, Key=item["Key"])
    s3.delete_bucket(Bucket=BUCKET)
```

`probe/tests/test_storage.py`:
```python
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from probe import storage
from probe.tests.conftest import BUCKET

PDF = b"%PDF-1.7\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


def put(intent: storage.UploadIntent, body: bytes) -> int:
    return requests.put(intent.url, data=body, headers=intent.headers, timeout=10).status_code


def test_intent_signs_type_and_length(bucket):
    intent = storage.create_intent(content_type="application/pdf", size=len(PDF))
    signed = parse_qs(urlparse(intent.url).query)["X-Amz-SignedHeaders"][0].split(";")
    assert {"content-type", "content-length"} <= set(signed)
    assert intent.key.startswith("pending/")


@pytest.mark.parametrize(
    ("content_type", "size"),
    [("image/svg+xml", 10), ("text/html", 10), ("application/pdf", 0),
     ("application/pdf", storage.MAX_BYTES + 1)],
)
def test_intent_rejects_bad_type_or_size(bucket, content_type, size):
    with pytest.raises(storage.UploadRejected):
        storage.create_intent(content_type=content_type, size=size)


def test_confirm_moves_valid_upload_to_files(bucket):
    intent = storage.create_intent(content_type="application/pdf", size=len(PDF))
    assert put(intent, PDF) == 200
    final = storage.confirm_upload(key=intent.key, content_type="application/pdf", size=len(PDF))
    assert final.startswith("files/") and final.endswith(".pdf")
    keys = [o["Key"] for o in bucket.list_objects_v2(Bucket=BUCKET)["Contents"]]
    assert keys == [final]


def test_confirm_rejects_mismatched_content(bucket):
    body = b"just some text, not a pdf at all"
    intent = storage.create_intent(content_type="application/pdf", size=len(body))
    assert put(intent, body) == 200
    with pytest.raises(storage.UploadRejected):
        storage.confirm_upload(key=intent.key, content_type="application/pdf", size=len(body))
    assert bucket.list_objects_v2(Bucket=BUCKET).get("KeyCount") == 0


def test_confirm_rejects_size_mismatch(bucket):
    intent = storage.create_intent(content_type="application/pdf", size=len(PDF))
    assert put(intent, PDF) == 200
    with pytest.raises(storage.UploadRejected):
        storage.confirm_upload(key=intent.key, content_type="application/pdf", size=len(PDF) + 1)


@pytest.mark.parametrize("key", ["files/abc.pdf", "pending/../files/x", "other/x", ""])
def test_confirm_rejects_key_outside_pending(bucket, key):
    with pytest.raises(storage.UploadRejected):
        storage.confirm_upload(key=key, content_type="application/pdf", size=10)


def test_download_url_forces_attachment(bucket):
    intent = storage.create_intent(content_type="application/pdf", size=len(PDF))
    put(intent, PDF)
    final = storage.confirm_upload(key=intent.key, content_type="application/pdf", size=len(PDF))
    response = requests.get(storage.download_url(key=final, filename="grades.pdf"), timeout=10)
    assert response.status_code == 200
    assert response.headers["Content-Disposition"] == 'attachment; filename="grades.pdf"'
    assert response.content == PDF


@pytest.mark.parametrize("key", ["pending/x", "files/../pending/x", "x"])
def test_download_rejects_key_outside_files(bucket, key):
    with pytest.raises(storage.UploadRejected):
        storage.download_url(key=key, filename="a.pdf")
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m uv run pytest probe/tests/test_storage.py`
Expected: FAIL (`ImportError: cannot import name 'storage' from 'probe'`).

- [ ] **Step 3: Implement `probe/storage.py`**

```python
"""Direct-to-R2 file flow: presigned PUT to pending/, confirm by sniffing, presigned GET."""

import re
import uuid
from dataclasses import dataclass
from typing import Any

import filetype
from django.conf import settings

ALLOWED_TYPES = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}
MAX_BYTES = 10 * 1024 * 1024
SNIFF_BYTES = 4096
PENDING_KEY = re.compile(r"^pending/[0-9a-f-]{36}$")
FINAL_KEY = re.compile(r"^files/[0-9a-f-]{36}\.(pdf|jpg|png)$")
SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


class UploadRejected(ValueError):
    pass


@dataclass(frozen=True)
class UploadIntent:
    key: str
    url: str
    headers: dict[str, str]


def _client() -> Any:
    import boto3  # imported lazily: keeps cold starts fast for requests that don't touch files
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name=settings.R2_REGION,
        config=Config(signature_version="s3v4"),
    )


def create_intent(*, content_type: str, size: int) -> UploadIntent:
    if content_type not in ALLOWED_TYPES:
        raise UploadRejected("This file type isn't allowed.")
    if not 0 < size <= MAX_BYTES:
        raise UploadRejected("The file is empty or larger than 10 MB.")
    key = f"pending/{uuid.uuid4()}"
    url = _client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.R2_BUCKET,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": size,
        },
        ExpiresIn=600,
    )
    return UploadIntent(key=key, url=url, headers={"Content-Type": content_type})


def confirm_upload(*, key: str, content_type: str, size: int) -> str:
    if not PENDING_KEY.fullmatch(key) or content_type not in ALLOWED_TYPES:
        raise UploadRejected("Unknown upload.")
    client = _client()
    bucket = settings.R2_BUCKET
    head = client.head_object(Bucket=bucket, Key=key)
    head_bytes = client.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{SNIFF_BYTES - 1}")
    sniffed = filetype.guess(head_bytes["Body"].read())
    if head["ContentLength"] != size or sniffed is None or sniffed.mime != content_type:
        client.delete_object(Bucket=bucket, Key=key)
        raise UploadRejected("The file's contents don't match its type or size.")
    final = f"files/{key.removeprefix('pending/')}.{ALLOWED_TYPES[content_type]}"
    client.copy_object(
        Bucket=bucket,
        Key=final,
        CopySource={"Bucket": bucket, "Key": key},
        ContentType=content_type,
        MetadataDirective="REPLACE",
    )
    client.delete_object(Bucket=bucket, Key=key)
    return final


def download_url(*, key: str, filename: str) -> str:
    if not FINAL_KEY.fullmatch(key):
        raise UploadRejected("Unknown file.")
    safe_name = SAFE_FILENAME.sub("_", filename) or "download"
    return _client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.R2_BUCKET,
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{safe_name}"',
        },
        ExpiresIn=300,
    )
```

- [ ] **Step 4: Run the storage tests**

Run: `python -m uv run pytest probe/tests/test_storage.py`
Expected: 16 passed.

- [ ] **Step 5: Write the failing view tests**

`probe/tests/test_file_views.py`:
```python
import json

import pytest
import requests

TOKEN = {"HTTP_AUTHORIZATION": "Bearer spike-token"}
PDF = b"%PDF-1.7\n%%EOF\n"


@pytest.fixture(autouse=True)
def _token(settings):
    settings.SPIKE_TOKEN = "spike-token"


def post_json(client, path, payload, **headers):
    return client.post(path, json.dumps(payload), content_type="application/json", **headers)


def test_full_flow_through_views(client, bucket):
    intent = post_json(
        client, "/probe/files/intent/", {"content_type": "application/pdf", "size": len(PDF)}, **TOKEN
    ).json()
    assert requests.put(intent["url"], data=PDF, headers=intent["headers"], timeout=10).ok
    confirmed = post_json(
        client,
        "/probe/files/confirm/",
        {"key": intent["key"], "content_type": "application/pdf", "size": len(PDF)},
        **TOKEN,
    ).json()
    response = client.get(
        "/probe/files/download/", {"key": confirmed["key"], "name": "a.pdf"}, **TOKEN
    )
    assert response.status_code == 302
    assert "response-content-disposition=attachment" in response["Location"]


def test_intent_rejection_is_400(client, bucket):
    response = post_json(
        client, "/probe/files/intent/", {"content_type": "text/html", "size": 5}, **TOKEN
    )
    assert response.status_code == 400
    assert response.json() == {"error": "This file type isn't allowed."}


def test_malformed_json_is_400(client, bucket):
    response = client.post(
        "/probe/files/intent/", "not json", content_type="application/json", **TOKEN
    )
    assert response.status_code == 400


def test_file_endpoints_need_token(client, bucket):
    assert post_json(client, "/probe/files/intent/", {}).status_code == 403
    assert client.get("/probe/files/download/", {"key": "files/x.pdf"}).status_code == 403


def test_upload_page_renders_without_token_in_url(client, vite_build):
    response = client.get("/probe/upload/")
    assert response.status_code == 200
    assert b'name="token"' in response.content
```

- [ ] **Step 6: Run the view tests and confirm they fail**

Run: `python -m uv run pytest probe/tests/test_file_views.py`
Expected: FAIL (404s: the routes don't exist yet).

- [ ] **Step 7: Implement the views, page and script**

Append to `probe/views.py`:
```python
import json

from django.http import HttpResponseBadRequest, HttpResponseRedirect

from probe import storage


def _json_body(request: HttpRequest) -> dict | None:
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


@csrf_exempt  # bearer-token API, no cookies involved
@require_POST
@require_token("SPIKE_TOKEN")
def file_intent(request: HttpRequest) -> JsonResponse:
    body = _json_body(request)
    if body is None:
        return JsonResponse({"error": "Expected a JSON object."}, status=400)
    try:
        intent = storage.create_intent(
            content_type=str(body.get("content_type", "")), size=int(body.get("size", 0))
        )
    except (storage.UploadRejected, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"key": intent.key, "url": intent.url, "headers": intent.headers})


@csrf_exempt  # bearer-token API, no cookies involved
@require_POST
@require_token("SPIKE_TOKEN")
def file_confirm(request: HttpRequest) -> JsonResponse:
    body = _json_body(request)
    if body is None:
        return JsonResponse({"error": "Expected a JSON object."}, status=400)
    try:
        final = storage.confirm_upload(
            key=str(body.get("key", "")),
            content_type=str(body.get("content_type", "")),
            size=int(body.get("size", 0)),
        )
    except (storage.UploadRejected, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"key": final})


@require_GET
@require_token("SPIKE_TOKEN")
def file_download(request: HttpRequest):
    try:
        url = storage.download_url(
            key=request.GET.get("key", ""), filename=request.GET.get("name", "download")
        )
    except storage.UploadRejected:
        return HttpResponseBadRequest("Unknown file.")
    return HttpResponseRedirect(url)


@require_GET
def upload_page(request: HttpRequest):
    return render(request, "probe/upload.html")
```
Move the new imports (`json`, `HttpResponseBadRequest`, `HttpResponseRedirect`, `from probe import storage`) to the
top import block so that ruff's `I` and `E402` rules pass.

Add to `probe/urls.py` `urlpatterns`:
```python
    path("probe/files/intent/", views.file_intent, name="probe-file-intent"),
    path("probe/files/confirm/", views.file_confirm, name="probe-file-confirm"),
    path("probe/files/download/", views.file_download, name="probe-file-download"),
    path("probe/upload/", views.upload_page, name="probe-upload"),
```

`templates/probe/upload.html`:
```html
{% load django_vite %}<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Upload probe</title>
  {% vite_hmr_client %}
  {% vite_asset 'src/main.ts' %}
  {% vite_asset 'src/upload.ts' %}
</head>
<body>
  <main>
    <h1>Upload probe</h1>
    <form id="upload-form">
      <p><label>Spike token <input name="token" type="password" autocomplete="off" required></label></p>
      <p><label>File (PDF, JPEG or PNG, up to 10 MB) <input name="file" type="file" accept=".pdf,.jpg,.jpeg,.png" required></label></p>
      <p><button type="submit">Upload</button></p>
    </form>
    <p id="upload-status" role="status" aria-live="polite"></p>
  </main>
</body>
</html>
```

`frontend/src/upload.ts`:
```ts
type Intent = { key: string; url: string; headers: Record<string, string> };

const form = document.querySelector<HTMLFormElement>("#upload-form");
const status = document.querySelector<HTMLElement>("#upload-status");

function report(message: string): void {
  if (status) status.textContent = message;
}

async function postJson<T>(path: string, token: string, payload: object): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  const body = (await response.json()) as T & { error?: string };
  if (!response.ok) throw new Error(body.error ?? `HTTP ${response.status}`);
  return body;
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  const token = String(data.get("token") ?? "");
  const file = data.get("file");
  if (!(file instanceof File) || file.size === 0) {
    report("Choose a file first.");
    return;
  }
  try {
    report("Requesting upload URL…");
    const intent = await postJson<Intent>("/probe/files/intent/", token, {
      content_type: file.type,
      size: file.size,
    });
    report("Uploading to storage…");
    const put = await fetch(intent.url, { method: "PUT", headers: intent.headers, body: file });
    if (!put.ok) throw new Error(`Storage refused the upload (HTTP ${put.status}).`);
    report("Checking the file…");
    const done = await postJson<{ key: string }>("/probe/files/confirm/", token, {
      key: intent.key,
      content_type: file.type,
      size: file.size,
    });
    const download = await fetch(
      `/probe/files/download/?key=${encodeURIComponent(done.key)}&name=${encodeURIComponent(file.name)}`,
      { headers: { Authorization: `Bearer ${token}` }, redirect: "manual" },
    );
    report(`Stored as ${done.key}. Download check: HTTP ${download.status} (0 or 302 = redirect issued).`);
  } catch (error) {
    report(error instanceof Error ? error.message : "Upload failed.");
  }
});
```

In `frontend/vite.config.ts`, add the second entry:
```ts
      input: {
        main: resolve(__dirname, "src/main.ts"),
        upload: resolve(__dirname, "src/upload.ts"),
      },
```

- [ ] **Step 8: Rebuild, then run everything**

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run build
python -m uv run pytest
python -m uv run ruff check .
```
Expected: the typecheck exits 0; 42 passed; `All checks passed!`

- [ ] **Step 9: Commit**

```powershell
git add probe templates frontend/src frontend/vite.config.ts
git commit -m "feat(spike): add R2 presigned upload, confirm and download probe"
```

---

### Task 6: External accounts

No code. The maintainer creates the accounts and handles the secrets himself, and notes each step when it's done.

- [ ] **Step 1: Vercel CLI and login.** In PowerShell: `npm install -g vercel@63.1.2`, then `vercel login`
  (interactive). Check: `vercel whoami` prints your username.
- [ ] **Step 2: Link a throwaway project.** In the repo, on `spike/vercel`: `vercel link`. Choose your personal scope,
  "Link to existing project? No", a throwaway project name, and leave the code directory as `./`. Don't connect
  the GitHub repo: deploys come from the CLI, so nothing gets pushed.
- [ ] **Step 3: Neon.**
  1. In the Vercel dashboard → the spike project → Storage → Create → Neon. Pick the Singapore region, connect it to Production and Preview, and turn on "Create database branch for deployment"
     for Preview.
  2. In the Neon console, create a branch `preview-base` from the main branch. If the integration lets you choose the parent for
     preview branches, set it to `preview-base`. If it doesn't, note that: it's a spike finding.
  3. Confirm that Vercel shows the env vars `DATABASE_URL` and `DATABASE_URL_UNPOOLED`.
- [ ] **Step 4: Cloudflare R2.**
  1. Create a throwaway bucket with location hint Asia-Pacific.
  2. Under Settings, set the CORS policy:
     ```json
     [{"AllowedOrigins": ["https://<spike-project>.vercel.app", "https://*.vercel.app"],
       "AllowedMethods": ["PUT", "GET", "HEAD"], "AllowedHeaders": ["content-type"], "MaxAgeSeconds": 3600}]
     ```
  3. Add a lifecycle rule: prefix `pending/`, delete objects after 1 day.
  4. Under API tokens, create a token with **Object Read & Write** scoped to this bucket only. Note the Access Key ID,
     Secret Access Key, and the S3 endpoint `https://<account-id>.r2.cloudflarestorage.com`.
- [ ] **Step 5: Resend.** Create an account and an API key with "Sending access". Without a verified domain, Resend only
  delivers from `onboarding@resend.dev` to your own signup address. That's enough for the spike.
- [ ] **Step 6: Environment variables.** Set these in the Vercel dashboard (or with `vercel env add <NAME>`) for
  **Production and Preview**:

  | Name | Value |
  |---|---|
  | `DJANGO_SECRET_KEY` | output of `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
  | `SPIKE_TOKEN` | a second `token_urlsafe(32)` value |
  | `CRON_SECRET` | a third `token_urlsafe(32)` value |
  | `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | from step 4 |
  | `R2_BUCKET` | the bucket from step 4 |
  | `R2_REGION` | `auto` |
  | `EMAIL_BACKEND` | `anymail.backends.resend.EmailBackend` |
  | `RESEND_API_KEY` | from step 5 |
  | `DEFAULT_FROM_EMAIL` | `ScholarSync <onboarding@resend.dev>` |
  | `DJANGO_DEBUG` | `false` |

  Keep `SPIKE_TOKEN` and `CRON_SECRET` somewhere private: Task 7's checks need them, and Kenneth runs those commands
  himself.

---

### Task 7: Deploy, measure, decide

The maintainer runs the commands that use his tokens, with the tokens in his shell's environment variables
(`$env:SPIKE_TOKEN`, `$env:CRON_SECRET`); those values are never printed. Results are recorded as a table: check | result | evidence.

- [ ] **Step 1: Deploy a preview, then production.**
  `vercel deploy` (preview URL printed), then `vercel deploy --prod`.
  Check: both builds succeed. If one fails, record the error and then fix it, or record it as a no-go finding.
- [ ] **Step 2: Build order.** Run `vercel inspect <production-url> --logs`. Record:
  - the `build: staticfiles present at start = …` line;
  - the migrate output;
  - `build: vite manifest present = True`;
  - whether Vercel's own collectstatic step appears after our script.

  Pass: migrations applied, and the manifest present.
- [ ] **Step 3: Assets.**
  ```powershell
  curl.exe -s https://<spike-project>.vercel.app/ | Select-String "/static/dist/assets/"
  curl.exe -sI https://<spike-project>.vercel.app/static/dist/assets/<main-file-from-previous-output>
  ```
  Pass: the page links hashed assets, and the asset returns 200 from the CDN (`x-vercel-cache` header present).
  Opening the page in a browser shows "JavaScript bundle loaded."
- [ ] **Step 4: Runtime, region and database.**
  ```powershell
  curl.exe -s -H "Authorization: Bearer $env:SPIKE_TOKEN" https://<spike-project>.vercel.app/probe/runtime/
  ```
  Pass: `vercel_region` is `sin1`, and `db_host` contains `-pooler`. Repeat against the preview URL: a different
  `db_host`/branch means Neon preview branching works.
- [ ] **Step 5: Cold start.** Leave the deployment idle for 15 minutes, then:
  ```powershell
  curl.exe -s -o NUL -w "%{time_total}`n" -H "Authorization: Bearer $env:SPIKE_TOKEN" https://<spike-project>.vercel.app/probe/runtime/
  ```
  Run it three times. Record the first (cold) and the next two (warm), plus `uptime_s`/`request_no` from the JSON to
  confirm a new instance. Pass: cold ≤ 3 s, warm ≤ 300 ms.
- [ ] **Step 6: Client IP.** Compare `curl.exe -s https://api.ipify.org` with `/probe/ip/`.
  1. Pick the header that equals your public IP (expected: `x-real-ip` or `x-vercel-forwarded-for`).
  2. Set `ALLAUTH_TRUSTED_CLIENT_IP_HEADER` to that header, then run `vercel deploy --prod` again.
  3. Pass: `allauth_client_ip` equals your public IP.
- [ ] **Step 7: Files.**
  1. Open `https://<spike-project>.vercel.app/probe/upload/`, enter the token, and upload a real PDF. Pass: "Stored
     as files/….pdf" and download check 0/302.
  2. Rename a `.txt` file to `.pdf` and upload it. Pass: "The file's contents don't match…".
  3. Wrong-size check: request an intent for size 100, then PUT 50 bytes.
     ```powershell
     $i = curl.exe -s -X POST -H "Authorization: Bearer $env:SPIKE_TOKEN" -H "Content-Type: application/json" -d '{\"content_type\":\"application/pdf\",\"size\":100}' https://<spike-project>.vercel.app/probe/files/intent/ | ConvertFrom-Json
     [IO.File]::WriteAllBytes("$env:TEMP\half.bin", [byte[]]::new(50))
     curl.exe -s -o NUL -w "%{http_code}`n" -X PUT -H "Content-Type: application/pdf" --data-binary "@$env:TEMP\half.bin" $i.url
     ```
     Pass: 403 (signature mismatch). R2 must enforce the signed length.
- [ ] **Step 8: Email.**
  ```powershell
  curl.exe -s -X POST -H "Authorization: Bearer $env:SPIKE_TOKEN" -d "to=<your Resend signup email>" https://<spike-project>.vercel.app/probe/email/
  ```
  Pass: `{"sent": 1, "message_id": "…"}`, and the email arrives.
- [ ] **Step 9: Cron.**
  - `curl.exe -s -H "Authorization: Bearer $env:CRON_SECRET" https://<spike-project>.vercel.app/_cron/ping/` returns
    `{"ok": true}`, and the same call with a wrong token returns 403.
  - The next day, `/probe/runtime/` shows a `last_cron` near 01:00 UTC, set by Vercel's scheduled call. Record it when
    seen.
- [ ] **Step 10: Bundle size and gating.**
  - Record the function size from the Vercel dashboard (Deployment → Functions). Pass: well under 500 MB.
  - Production gating (spec §11): `vercel build` must run on Linux, because psycopg wheels are platform-specific, so
    the prebuilt route is verified in M2 once CI exists. Record "CI job on ubuntu: `vercel build` + `vercel deploy
    --prebuilt --prod`" as the chosen method, unless Vercel deployment checks prove simpler during the spike.
- [ ] **Step 11: Decide and record.**
  - **Go** if steps 2–4 and 6–8 pass, and cold start is ≤ 3 s.
  - **No-go** on any must-pass failure that can't be fixed with configuration. In that case, choose the fallback host
    (Docker on Fly.io or Render, Singapore).

  Record the results and the decision.
- [ ] **Step 12: Tidy up.** Keep the `spike/vercel` branch for reference (don't merge it into `main`). Optionally delete
  the spike's Vercel project, Neon database, R2 bucket and keys once the results are recorded, then revoke
  the R2 token and Resend key.
