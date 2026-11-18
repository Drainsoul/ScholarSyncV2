"""Request ids and user ids on every log line (M13, ASVS V16.2.1)."""

import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.core.logging import JsonFormatter

ROOT = Path(__file__).resolve().parents[3]


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(json.loads(self.format(record)))


@pytest.fixture
def captured() -> Any:
    handler = _Capture()
    logger = logging.getLogger("django.request")
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)


@pytest.mark.django_db
def test_request_id_echoed_and_logged(client: Any, captured: Any, vite_build: Any) -> None:
    response = client.get("/no-such-page/", HTTP_X_REQUEST_ID="abcd1234-ef56")
    assert response["X-Request-ID"] == "abcd1234-ef56"
    assert any(line.get("request_id") == "abcd1234-ef56" for line in captured.lines)


@pytest.mark.django_db
def test_invalid_request_id_replaced(client: Any) -> None:
    response = client.get("/healthz", HTTP_X_REQUEST_ID="bad id!")
    assert re.fullmatch(r"[0-9a-f]{32}", response["X-Request-ID"])


@pytest.mark.django_db
def test_log_line_has_user_id_after_sign_in(client: Any, captured: Any, vite_build: Any) -> None:
    user = UserFactory.create(verified=True)
    client.force_login(user)
    client.get("/me/applications/999999/")
    lines = [line for line in captured.lines if "Not Found" in line["msg"]]
    assert lines and lines[-1]["user_id"] == user.pk


def test_log_line_outside_a_request_has_no_ids() -> None:
    record = logging.LogRecord("apps.test", logging.INFO, __file__, 1, "hello", None, None)
    payload = json.loads(JsonFormatter().format(record))
    assert "request_id" not in payload and "user_id" not in payload


def test_access_log_format_has_request_id() -> None:
    assert "%({x-request-id}o)s" in (ROOT / "Dockerfile").read_text(encoding="utf-8")
