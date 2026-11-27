"""Vercel Cron's reset call (branch `demo`, hosted demo design section 5.4)."""

from typing import Any

import pytest
from django.test import override_settings

from apps.demo import reset

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.demo.tests.reset_urls")]

URL = "/_demo/reset/"
SECRET = "s" * 40


@pytest.fixture
def calls(settings: Any, monkeypatch: Any) -> list[int]:
    settings.PUBLIC_DEMO = True
    settings.CRON_SECRET = SECRET
    made: list[int] = []

    def fake_reset() -> reset.ResetResult:
        made.append(1)
        return reset.ResetResult(files_deleted=3, accounts_created=7, seconds=1.5)

    monkeypatch.setattr(reset, "reset", fake_reset)
    return made


def test_reset_view_404_without_header(client: Any, calls: list[int]) -> None:
    assert client.get(URL).status_code == 404
    assert calls == []


def test_reset_view_404_with_wrong_secret(client: Any, calls: list[int]) -> None:
    response = client.get(URL, HTTP_AUTHORIZATION=f"Bearer {'t' * 40}")
    assert response.status_code == 404
    assert calls == []


def test_reset_view_404_with_empty_bearer(client: Any, calls: list[int], settings: Any) -> None:
    settings.CRON_SECRET = ""
    response = client.get(URL, HTTP_AUTHORIZATION="Bearer ")
    assert response.status_code == 404
    assert calls == []


def test_reset_view_404_when_flag_off(client: Any, calls: list[int], settings: Any) -> None:
    settings.PUBLIC_DEMO = False
    response = client.get(URL, HTTP_AUTHORIZATION=f"Bearer {SECRET}")
    assert response.status_code == 404
    assert calls == []


def test_reset_view_runs_with_right_secret(client: Any, calls: list[int]) -> None:
    response = client.get(URL, HTTP_AUTHORIZATION=f"Bearer {SECRET}")
    assert response.status_code == 200
    assert response.json() == {"files_deleted": 3, "accounts_created": 7, "seconds": 1.5}
    assert "no-store" in response["Cache-Control"] or "no-cache" in response["Cache-Control"]
    assert calls == [1]


def test_reset_view_rejects_post(client: Any, calls: list[int]) -> None:
    response = client.post(URL, HTTP_AUTHORIZATION=f"Bearer {SECRET}")
    assert response.status_code == 405
    assert calls == []


@override_settings(PUBLIC_DEMO=False, DEMO_ACTIVE=False)
@pytest.mark.urls("config.urls")
def test_route_absent_outside_public_demo(client: Any) -> None:
    assert client.get(URL).status_code == 404


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_reset_view_404_for_other_methods_without_secret(calls: list[int], method: str) -> None:
    """A 405, or CSRF's 403, would show the route exists (design 5.4: it can't be probed)."""
    from conftest import HttpsClient

    client = HttpsClient(enforce_csrf_checks=True)
    assert getattr(client, method)(URL).status_code == 404
    assert calls == []
