from django.conf import settings
from django.core.checks import Error, run_checks


def test_no_legacy_csp_settings_names():
    """django-csp 4 flags any CSP_* setting as old-format config (csp.E001)."""
    assert [name for name in dir(settings) if name.startswith("CSP_")] == []


def test_csp_system_checks_pass():
    errors = [m for m in run_checks(include_deployment_checks=True) if isinstance(m, Error)]
    assert [e.id for e in errors if e.id and e.id.startswith("csp.")] == []
