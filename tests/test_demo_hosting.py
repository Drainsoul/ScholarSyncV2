"""Branch `demo`'s hosting files (docs/design/2026-11-28-hosted-demo-design.md 5.3, 5.4)."""

import json
import os
import shutil
import subprocess
import sys
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


WORKFLOW = ROOT / ".github" / "workflows" / "demo.yml"


def test_deploy_workflow_pins_every_action_to_a_commit() -> None:
    """The deploy job holds the host's token: no action may float on a tag."""
    import re

    uses = re.findall(r"uses:\s*(\S+)", WORKFLOW.read_text(encoding="utf-8"))
    assert uses
    assert all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref) for ref in uses), uses


def test_deploy_workflow_keeps_secrets_off_command_lines() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "--token" not in text  # the CLI reads the token from the environment
    assert "set -a" not in text  # never export the whole production environment


def test_deploy_reads_only_the_direct_database_url() -> None:
    """The migrate step takes one value from the pulled settings, masked before it is used."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/demo_env_value.py DATABASE_URL_UNPOOLED" in text
    assert "::add-mask::" in text


def test_env_value_reads_one_value_literally(tmp_path: Path) -> None:
    """No shell expansion: a `$` or backtick in a credential comes through untouched."""
    env_file = tmp_path / ".env.production.local"
    env_file.write_text(
        '# Created by the CLI\nOTHER="x"\nDATABASE_URL_UNPOOLED="postgres://u:p$a`b@h/db?sslmode=require"\n',
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/demo_env_value.py", "DATABASE_URL_UNPOOLED", str(env_file)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "postgres://u:p$a`b@h/db?sslmode=require"


def test_env_value_fails_on_a_missing_or_empty_name(tmp_path: Path) -> None:
    """Sensitive variables come back empty from a pull: fail loudly, never migrate with nothing."""
    env_file = tmp_path / ".env.production.local"
    env_file.write_text('DATABASE_URL_UNPOOLED=""\n', encoding="utf-8")
    for name in ("DATABASE_URL_UNPOOLED", "MISSING"):
        result = subprocess.run(  # noqa: S603
            [sys.executable, "scripts/demo_env_value.py", name, str(env_file)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert name in result.stderr


def test_upload_ignore_keeps_files_the_function_traces() -> None:
    """The Python packager traces every package, tests included; ignoring them at upload broke the
    first deploy (ENOENT on apps/accounts/tests/__init__.py)."""
    lines = (ROOT / f".{HOST}ignore").read_text(encoding="utf-8").split()
    assert "tests/" not in lines
