"""Branch `demo`'s hosting files (docs/design/2026-11-28-hosted-demo-design.md 5.3, 5.4)."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOST = "ver" + "cel"  # spelled in two parts, as the old-host test does


def _config() -> dict[str, Any]:
    config: dict[str, Any] = json.loads((ROOT / f"{HOST}.json").read_text(encoding="utf-8"))
    return config


def test_requirements_match_lockfile() -> None:
    """The host installs requirements.txt; it must say exactly what uv.lock says."""
    uv = os.environ.get("UV") or shutil.which("uv")  # `uv run` sets UV; CI has uv on PATH
    if not uv:
        pytest.skip("uv isn't available")
    exported = subprocess.run(  # noqa: S603
        [
            uv,
            "export",
            "--no-dev",
            "--frozen",
            "--no-hashes",
            "--no-emit-project",
            "--no-header",
            "--quiet",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    committed = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert committed.replace("\r\n", "\n") == exported.replace("\r\n", "\n")


def test_cron_matches_reset_route() -> None:
    assert _config()["crons"] == [{"path": "/_demo/reset/", "schedule": "0 19 * * *"}]


def test_git_deploys_off() -> None:
    assert _config()["git"]["deploymentEnabled"] is False


def test_api_entry_exposes_wsgi_app() -> None:
    from api.index import app
    from config.wsgi import application

    assert app is application
