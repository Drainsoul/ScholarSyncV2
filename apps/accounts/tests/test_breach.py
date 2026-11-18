"""Breached passwords refused (M13, ASVS V6.2.12)."""

import hashlib
import io
import logging
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from django.core.exceptions import ValidationError

from apps.accounts import breach
from config.tests.test_settings import settings_values

PASSWORD = "correct-horse-battery-1"


def _suffix(password: str) -> tuple[str, str]:
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    return digest[:5], digest[5:]


class _Response(io.BytesIO):
    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _fake_range(monkeypatch: pytest.MonkeyPatch, body: str, seen: list[Any]) -> None:
    def urlopen(request: Any, timeout: float) -> _Response:
        seen.append((request.full_url, dict(request.header_items()), timeout))
        return _Response(body.encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def test_breached_password_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _prefix, suffix = _suffix(PASSWORD)
    _fake_range(monkeypatch, f"0000000000000000000000000000000000A:0\r\n{suffix}:42\r\n", [])
    with pytest.raises(ValidationError) as caught:
        breach.BreachedPasswordValidator().validate(PASSWORD)
    assert caught.value.messages == [
        "This password has appeared in a data breach. Choose another one."
    ]


def test_clean_password_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_range(monkeypatch, "0000000000000000000000000000000000A:3\r\n", [])
    breach.BreachedPasswordValidator().validate(PASSWORD)


def test_padding_rows_with_zero_count_never_match(monkeypatch: pytest.MonkeyPatch) -> None:
    _prefix, suffix = _suffix(PASSWORD)
    _fake_range(monkeypatch, f"{suffix}:0\r\n", [])
    breach.BreachedPasswordValidator().validate(PASSWORD)


def test_only_five_hex_characters_are_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []
    _fake_range(monkeypatch, "", seen)
    breach.BreachedPasswordValidator().validate(PASSWORD)
    prefix, suffix = _suffix(PASSWORD)
    url, headers, timeout = seen[0]
    assert url == f"https://api.pwnedpasswords.com/range/{prefix}"
    assert suffix not in url and PASSWORD not in url
    assert headers.get("Add-padding") == "true"
    assert timeout == 3


def test_network_error_fails_open_and_logs_no_password(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def down(request: Any, timeout: float) -> None:
        raise OSError("network unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", down)
    with caplog.at_level(logging.WARNING):
        breach.BreachedPasswordValidator().validate(PASSWORD)
    assert "Breached-password check skipped" in caplog.text
    assert PASSWORD not in caplog.text and _suffix(PASSWORD)[0] not in caplog.text


def test_on_in_production_off_elsewhere(tmp_path: Path) -> None:
    name = "apps.accounts.breach.BreachedPasswordValidator"

    def validators(**env: str) -> list[str]:
        values = settings_values(
            tmp_path, ["AUTH_PASSWORD_VALIDATORS"], _unset=["PASSWORD_BREACH_CHECK"], **env
        )
        return [item["NAME"] for item in values["AUTH_PASSWORD_VALIDATORS"]]

    assert name in validators()
    assert name not in validators(DJANGO_DEBUG="true")
