import pytest


@pytest.mark.django_db
def test_security_headers_on_success(client):
    response = client.get("/healthz")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response["X-Frame-Options"] == "DENY"
    assert "camera=()" in response["Permissions-Policy"]


def test_security_headers_on_404(client, vite_build):
    response = client.get("/definitely-not-a-page/")
    assert response.status_code == 404
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "Permissions-Policy" in response
    assert (
        "Content-Security-Policy-Report-Only" in response or "Content-Security-Policy" in response
    )


@pytest.mark.django_db
def test_csp_enforced_by_default(client, settings):
    response = client.get("/healthz")
    policy = response["Content-Security-Policy"]
    assert "default-src 'self'" in policy
    assert "script-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "object-src 'none'" in policy
    assert "report-uri" not in policy
    assert "Content-Security-Policy-Report-Only" not in response


@pytest.mark.django_db
def test_csp_report_only_when_asked(client, settings):
    settings.CONTENT_SECURITY_POLICY_REPORT_ONLY = settings.CONTENT_SECURITY_POLICY
    settings.CONTENT_SECURITY_POLICY = None
    response = client.get("/healthz")
    assert "default-src 'self'" in response["Content-Security-Policy-Report-Only"]
    assert "Content-Security-Policy" not in response


@pytest.mark.django_db
def test_server_error_carries_security_headers(client, settings, vite_build):
    settings.ROOT_URLCONF = "apps.core.tests.boom_urls"
    client.raise_request_exception = False
    response = client.get("/boom/")
    assert response.status_code == 500
    assert "default-src 'self'" in response["Content-Security-Policy"]
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"


@pytest.mark.django_db
def test_tests_run_with_production_security_settings(client, settings):
    response = client.get("/healthz")
    assert response["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert settings.SECURE_SSL_REDIRECT is True
    assert settings.SESSION_COOKIE_SECURE is True
    assert settings.CSRF_COOKIE_SECURE is True


def test_plain_http_redirects_to_https():
    from django.test import Client

    response = Client().get("/healthz")
    assert response.status_code == 301
    assert response["Location"] == "https://testserver/healthz"
