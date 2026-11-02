import importlib.util
from pathlib import Path

import pytest
from django.test import Client

PROBE = Path(__file__).resolve().parents[3] / "docker" / "healthcheck.py"


def _probe_headers(monkeypatch, allowed_hosts):
    spec = importlib.util.spec_from_file_location("healthcheck_probe", PROBE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", allowed_hosts)
    return module.probe_headers()


@pytest.mark.django_db
def test_probe_gets_200_under_production_settings(settings, monkeypatch):
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = ["scholarships.example.org", "www.example.org"]
    settings.SECURE_SSL_REDIRECT = True
    headers = _probe_headers(monkeypatch, "scholarships.example.org,www.example.org")
    assert headers["Host"] == "scholarships.example.org"
    wsgi = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()}
    response = Client().get("/healthz", secure=False, **wsgi)
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.django_db
def test_plain_http_requests_still_redirect_in_production(settings):
    settings.ALLOWED_HOSTS = ["scholarships.example.org"]
    settings.SECURE_SSL_REDIRECT = True
    response = Client().get("/", secure=False, HTTP_HOST="scholarships.example.org")
    assert response.status_code == 301
    assert response["Location"].startswith("https://")
