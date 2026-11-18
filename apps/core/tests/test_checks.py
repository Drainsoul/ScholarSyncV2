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


def test_deploy_check_warns_when_production_is_report_only(settings):
    settings.CONTENT_SECURITY_POLICY = None
    settings.CONTENT_SECURITY_POLICY_REPORT_ONLY = {"DIRECTIVES": {}}
    found = [
        e
        for e in run_checks(include_deployment_checks=True)
        if e.id == "security.W_CSP_REPORT_ONLY"
    ]
    assert found and "CSP_REPORT_ONLY" in (found[0].hint or "")
    settings.CONTENT_SECURITY_POLICY = {"DIRECTIVES": {}}
    assert not [
        e
        for e in run_checks(include_deployment_checks=True)
        if e.id == "security.W_CSP_REPORT_ONLY"
    ]
