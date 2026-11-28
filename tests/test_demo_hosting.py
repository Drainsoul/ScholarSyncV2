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


def _wsgi_restores_paths(public_demo: str | None, tmp_path: Path) -> bool:
    """Import config.wsgi in a fresh process and say whether it restores rewritten paths."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "SCHOLARSYNC_"))}
    env.update(
        {
            "DJANGO_ENV_FILE": str(tmp_path / "absent.env"),
            "DJANGO_SECRET_KEY": "x" * 50,
            "DJANGO_ALLOWED_HOSTS": "scholarsync.example",
            "SITE_OPERATOR_NAME": "ScholarSync Test",
            "PRIVACY_CONTACT_EMAIL": "privacy@scholarsync.test",
            "DATABASE_URL": "postgres://u:p@localhost:5433/db",
            "EMAIL_URL": "" if public_demo else "smtp://localhost:25",
            "CRON_SECRET": "c" * 32,
        }
    )
    if public_demo is not None:
        env["SCHOLARSYNC_PUBLIC_DEMO"] = public_demo
    code = "import config.wsgi as w; print(getattr(w.application, 'restores_path', False))"
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip() == "True"


def test_wsgi_restores_paths_in_the_public_demo(tmp_path: Path) -> None:
    """Whatever entry the runtime loads (api/index.py or WSGI_APPLICATION), it is this one."""
    assert _wsgi_restores_paths("true", tmp_path)


def test_wsgi_untouched_outside_the_public_demo(tmp_path: Path) -> None:
    assert not _wsgi_restores_paths(None, tmp_path)


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
    """The Python packager bundles every tracked file; ignoring any at upload broke early deploys
    (ENOENT on apps/accounts/tests/__init__.py, then docs/accessibility/wcag-22-aa.md)."""
    lines = (ROOT / f".{HOST}ignore").read_text(encoding="utf-8").split()
    assert "tests/" not in lines
    assert "docs/" not in lines


def _seen_by_django(query: str, path: str = "/api/index") -> tuple[str, str]:
    """Run the path restore and report the path and query string Django would see."""
    from config.rewrite_path import restore_path

    seen: dict[str, str] = {}

    def fake_django(environ: dict[str, Any], start_response: Any) -> list[bytes]:
        seen["path"] = environ["PATH_INFO"]
        seen["query"] = environ["QUERY_STRING"]
        return [b""]

    restore_path(fake_django)({"PATH_INFO": path, "QUERY_STRING": query}, lambda *a: None)
    return seen["path"], seen["query"]


def test_entry_restores_the_visitors_path() -> None:
    """The runtime hands Django the rewrite's destination (/api/index); the first deploy 404'd
    on every page until the original path came back."""
    assert _seen_by_django("__path=accounts/login/") == ("/accounts/login/", "")


def test_entry_keeps_the_visitors_query_string() -> None:
    path, query = _seen_by_django("next=%2Fme%2F&__path=accounts/login/&page=2")
    assert path == "/accounts/login/"
    assert query == "next=%2Fme%2F&page=2"


def test_entry_maps_the_bare_domain_to_root() -> None:
    assert _seen_by_django("__path=") == ("/", "")


def test_entry_keeps_plus_signs_and_escapes_in_the_path() -> None:
    assert _seen_by_django("__path=files/a+b%20c/") == ("/files/a+b c/", "")


def test_entry_leaves_requests_without_the_marker_alone() -> None:
    assert _seen_by_django("x=1", path="/healthz") == ("/healthz", "x=1")


def test_rewrite_passes_the_original_path() -> None:
    assert _config()["rewrites"] == [{"source": "/(.*)", "destination": "/api/index?__path=$1"}]
