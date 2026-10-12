import pytest


@pytest.mark.django_db
def test_security_headers_on_success(client):
    response = client.get("/healthz")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response["X-Frame-Options"] == "DENY"
    assert "camera=()" in response["Permissions-Policy"]


def test_security_headers_on_404(client):
    response = client.get("/definitely-not-a-page/")
    assert response.status_code == 404
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "Permissions-Policy" in response
    assert (
        "Content-Security-Policy-Report-Only" in response or "Content-Security-Policy" in response
    )


@pytest.mark.django_db
def test_csp_report_only_by_default(client, settings):
    response = client.get("/healthz")
    policy = response["Content-Security-Policy-Report-Only"]
    assert "default-src 'self'" in policy
    assert "script-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "object-src 'none'" in policy
    assert "Content-Security-Policy" not in response


@pytest.mark.django_db
def test_csp_enforced_when_report_only_disabled(client, settings):
    settings.CONTENT_SECURITY_POLICY = settings.CONTENT_SECURITY_POLICY_REPORT_ONLY
    settings.CONTENT_SECURITY_POLICY_REPORT_ONLY = None
    response = client.get("/healthz")
    assert "default-src 'self'" in response["Content-Security-Policy"]
