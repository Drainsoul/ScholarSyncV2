"""Vercel build step: front end, static files, then migrations on the unpooled database URL.

Vercel runs this after installing Python dependencies (pyproject `[tool.vercel.scripts] build`).
collectstatic runs here, after the Vite build, so `staticfiles.json` never depends on when
Vercel's own collectstatic runs (it runs after this script; see STATE.md → Spike results).
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
        [python, "manage.py", "collectstatic", "--noinput"],
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
    npm = shutil.which("npm") or "npm"
    env = migration_env(os.environ)
    for command in steps(npm, sys.executable):
        print("build: running", " ".join(command[1:]), flush=True)
        subprocess.run(command, check=True, cwd=ROOT, env=env)  # noqa: S603
    return 0


if __name__ == "__main__":
    sys.exit(main())
