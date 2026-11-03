"""Email committed during a request is sent after the response (spec section 9)."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.core.handlers.wsgi import WSGIHandler
from django.core.signals import request_finished, request_started
from django.db import close_old_connections, transaction
from django.test import RequestFactory

from apps.accounts.tests.factories import UserFactory
from apps.workspace import emails
from apps.workspace.models import EmailOutbox

ANA = "ana@scholarsync.test"


def _start_response(status: str, headers: Any, exc_info: Any = None) -> Any:
    return lambda data: None


@pytest.fixture
def sends(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Record every send() call, then send for real."""
    calls: list[int] = []
    real = emails.send

    def recording(row_id: int) -> bool:
        calls.append(row_id)
        return real(row_id)

    monkeypatch.setattr(emails, "send", recording)
    return calls


@pytest.fixture
def request_signals() -> Iterator[None]:
    """Fire the request signals by hand, as the test client does, without closing connections."""
    request_started.disconnect(close_old_connections)
    request_finished.disconnect(close_old_connections)
    try:
        yield
    finally:
        request_started.connect(close_old_connections)
        request_finished.connect(close_old_connections)
        emails._after_response.set(None)


def test_a_password_reset_responds_before_the_email_is_sent(
    transactional_db: Any, settings: Any, mailoutbox: Any, sends: list[int]
) -> None:
    # A bare WSGI call, as gunicorn makes it: the handler returns the response, the server
    # writes it out, then calls close(), which fires request_finished.
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if not m.endswith("CsrfViewMiddleware")]
    UserFactory.create(email=ANA, verified=True)
    request = RequestFactory().post("/accounts/password/reset/", {"email": ANA}, secure=True)
    response = WSGIHandler()(request.environ, _start_response)
    assert response.status_code == 302
    row = EmailOutbox.objects.get()
    assert row.kind == "password_reset_key" and row.status == "queued"
    assert sends == [] and mailoutbox == []
    response.close()
    assert sends == [row.pk] and len(mailoutbox) == 1
    row.refresh_from_db()
    assert row.status == "sent"


def test_the_test_client_still_delivers_by_the_end_of_the_request(
    client: Any, transactional_db: Any, mailoutbox: Any
) -> None:
    UserFactory.create(email=ANA, verified=True)
    client.post("/accounts/password/reset/", {"email": ANA})
    assert EmailOutbox.objects.get().status == "sent"
    assert len(mailoutbox) == 1


def test_outside_a_request_the_email_sends_on_commit(
    transactional_db: Any, mailoutbox: Any, sends: list[int]
) -> None:
    with transaction.atomic():
        row = emails.enqueue(to=ANA, kind="password_set", context={})
        assert sends == []
    assert sends == [row.pk] and len(mailoutbox) == 1


def test_a_raising_send_after_the_response_does_not_propagate(
    db: Any, monkeypatch: pytest.MonkeyPatch, request_signals: None, caplog: Any
) -> None:
    def boom(row_id: int) -> bool:
        raise RuntimeError("smtp down")

    monkeypatch.setattr(emails, "send", boom)
    request_started.send(sender=None)
    emails._send_or_defer(41)
    emails._send_or_defer(42)
    request_finished.send(sender=None)  # must not raise
    assert emails._after_response.get() is None
    assert [r.args for r in caplog.records if r.levelname == "ERROR"] == [(41,), (42,)]


def test_the_queue_is_cleared_after_each_request(
    db: Any, sends: list[int], request_signals: None
) -> None:
    request_started.send(sender=None)
    emails._send_or_defer(7)
    assert sends == []
    request_finished.send(sender=None)
    assert sends == [7]
    request_started.send(sender=None)
    request_finished.send(sender=None)
    assert sends == [7]
