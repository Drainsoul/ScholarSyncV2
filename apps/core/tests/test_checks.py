import pytest
from django.core.checks import run_checks


@pytest.mark.parametrize("present", [True, False])
def test_deploy_check_follows_the_demo_folder(monkeypatch, present):
    monkeypatch.setattr("apps.core.checks.demo_installed", lambda base_dir: present)
    errors = run_checks(include_deployment_checks=True)
    assert any(e.id == "demo.E001" for e in errors) is present


def test_demo_check_is_deploy_only(monkeypatch):
    monkeypatch.setattr("apps.core.checks.demo_installed", lambda base_dir: True)
    assert not [e for e in run_checks() if e.id == "demo.E001"]
