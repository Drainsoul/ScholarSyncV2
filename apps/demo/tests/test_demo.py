import subprocess
from pathlib import Path

import pytest
from django.conf import settings
from django.core.checks import run_checks
from django.core.management import call_command
from django.core.management.base import CommandError


def test_demo_is_installed_but_inactive_under_test_settings():
    assert "apps.demo" in settings.INSTALLED_APPS
    assert settings.DEMO_ACTIVE is False


def test_load_demo_refuses_in_production():
    with pytest.raises(CommandError, match="production"):
        call_command("load_demo")


def test_load_demo_runs_when_active(settings, capsys):
    settings.DEMO_ACTIVE = True
    call_command("load_demo")
    assert "Demo data: 0 new objects." in capsys.readouterr().out


def test_deploy_check_fails_while_the_demo_is_installed():
    errors = run_checks(include_deployment_checks=True)
    assert any(e.id == "demo.E001" for e in errors)


def test_nothing_outside_the_demo_imports_it():
    root = Path(__file__).resolve().parents[3]
    tracked = subprocess.run(
        ["git", "ls-files", "*.py"],  # noqa: S607
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    offenders = []
    for rel in tracked:
        if rel.startswith("apps/demo/") or rel == "config/settings.py":
            continue
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "apps.demo" in text or "from apps import demo" in text:
            offenders.append(rel)
    assert offenders == []
