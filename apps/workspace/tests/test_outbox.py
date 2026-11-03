import threading
from datetime import timedelta
from io import StringIO
from pathlib import Path
from smtplib import SMTPException
from typing import Any

import pytest
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command
from django.db import connections, transaction
from django.utils import timezone

from apps.workspace import emails
from apps.workspace.emails import MAX_ATTEMPTS, enqueue, send
from apps.workspace.models import EmailOutbox

TEST_TEMPLATES = Path(__file__).parent / "templates"
TO = "ana@scholarsync.test"


@pytest.fixture(autouse=True)
def _test_kind(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # Assign a new list so the setting_changed signal resets the cached template engine.
    templates = [dict(engine) for engine in settings.TEMPLATES]
    templates[0]["DIRS"] = [TEST_TEMPLATES, *templates[0]["DIRS"]]
    settings.TEMPLATES = templates
    monkeypatch.setitem(emails.KINDS, "test_message", frozenset({"greeting"}))


def _fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: Any, *args: Any, **kwargs: Any) -> int:
        raise SMTPException("down")

    monkeypatch.setattr(EmailMultiAlternatives, "send", boom)


def _row(**extra: Any) -> EmailOutbox:
    return EmailOutbox.objects.create(
        to=TO, kind="test_message", context={"greeting": "Hi"}, **extra
    )


def test_enqueue_sends_after_commit_and_forgets_the_context(
    db: Any, mailoutbox: Any, django_capture_on_commit_callbacks: Any
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        row = enqueue(to=TO, kind="test_message", context={"greeting": "Hi", "secret": "x"})
    row.refresh_from_db()
    assert row.status == "sent" and row.context == {} and row.provider_message_id.startswith("<")
    assert row.sent_at is not None
    assert mailoutbox[0].to == [TO] and "Hi" in mailoutbox[0].body
    assert "\n" not in mailoutbox[0].subject
    assert mailoutbox[0].alternatives  # HTML part


def test_unknown_kind_is_refused(db: Any) -> None:
    with pytest.raises(KeyError):
        enqueue(to=TO, kind="nope", context={})
    assert EmailOutbox.objects.count() == 0


def test_unlisted_context_keys_are_dropped(db: Any) -> None:
    row = enqueue(to=TO, kind="test_message", context={"greeting": "Hi", "secret": "x"})
    row.refresh_from_db()
    assert row.context == {"greeting": "Hi"}


def test_smtp_failure_marks_the_row_failed_without_raising(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail(monkeypatch)
    row = _row()
    assert send(row.pk) is False
    row.refresh_from_db()
    assert row.status == "failed" and row.attempts == 1
    assert row.last_error == "SMTPException: down"
    assert row.context == {"greeting": "Hi"}  # kept for the retry


def test_send_outbox_retries_failed_rows_until_five_attempts(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail(monkeypatch)
    row = _row()
    assert send(row.pk) is False  # the commit-hook attempt; the rest are retries
    for _ in range(6):
        call_command("send_outbox", stdout=StringIO())
    row.refresh_from_db()
    assert row.attempts == MAX_ATTEMPTS == 5
    assert row.status == "failed" and row.context == {}


def test_send_outbox_reports_counts(db: Any, mailoutbox: Any) -> None:
    EmailOutbox.objects.filter().delete()
    row = _row()
    EmailOutbox.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(hours=1))
    out = StringIO()
    call_command("send_outbox", stdout=out)
    assert "Outbox: 1 sent, 0 failed." in out.getvalue()


def test_send_outbox_picks_up_stale_queued_rows(
    db: Any, mailoutbox: Any, time_machine: Any
) -> None:
    now = timezone.now()
    time_machine.move_to(now - timedelta(minutes=6), tick=False)
    old = _row()
    time_machine.move_to(now - timedelta(minutes=1), tick=False)
    fresh = _row()
    time_machine.move_to(now, tick=False)
    call_command("send_outbox", stdout=StringIO())
    old.refresh_from_db()
    fresh.refresh_from_db()
    assert old.status == "sent" and fresh.status == "queued"
    assert len(mailoutbox) == 1


def test_a_sent_row_is_not_sent_again(db: Any, mailoutbox: Any) -> None:
    row = _row()
    assert send(row.pk) is True
    assert send(row.pk) is False
    assert len(mailoutbox) == 1


def test_a_locked_row_is_not_sent_twice(transactional_db: Any, mailoutbox: Any) -> None:
    row = _row()
    locked = threading.Event()
    release = threading.Event()

    def hold() -> None:
        try:
            with transaction.atomic():
                list(EmailOutbox.objects.select_for_update().filter(pk=row.pk))
                locked.set()
                release.wait(10)
        finally:
            connections.close_all()

    thread = threading.Thread(target=hold)
    thread.start()
    try:
        assert locked.wait(10)
        assert send(row.pk) is False
        assert len(mailoutbox) == 0
    finally:
        release.set()
        thread.join()
    row.refresh_from_db()
    assert row.status == "queued"


def test_cleanup_purges_sent_rows_after_90_days(db: Any, time_machine: Any) -> None:
    now = timezone.now()
    for name, status, age in [
        ("old", "sent", 91),
        ("recent", "sent", 89),
        ("failed", "failed", 91),
    ]:
        EmailOutbox.objects.create(
            to=f"{name}@scholarsync.test",
            kind="test_message",
            status=status,
            sent_at=now - timedelta(days=age) if status == "sent" else None,
        )
    call_command("cleanup")
    assert set(EmailOutbox.objects.values_list("to", flat=True)) == {
        "recent@scholarsync.test",
        "failed@scholarsync.test",
    }


def test_a_render_error_never_stores_context_values(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: Any, **kwargs: Any) -> str:
        raise ValueError("bad value tok-12345")

    monkeypatch.setattr(emails, "render_to_string", boom)
    row = _row()
    assert send(row.pk) is False
    row.refresh_from_db()
    assert row.status == "failed" and row.attempts == 1
    assert row.last_error == "ValueError while rendering"
    assert "tok-12345" not in row.last_error


def test_a_missing_template_counts_as_an_attempt_and_wipes_at_five(db: Any) -> None:
    row = EmailOutbox.objects.create(to=TO, kind="no_such_kind", context={"greeting": "Hi"})
    for attempt in range(1, MAX_ATTEMPTS + 1):
        assert send(row.pk) is False
        row.refresh_from_db()
        assert row.attempts == attempt
        assert row.last_error == "TemplateDoesNotExist while rendering"
        assert row.context == ({} if attempt == MAX_ATTEMPTS else {"greeting": "Hi"})
    assert send(row.pk) is False
    row.refresh_from_db()
    assert row.attempts == MAX_ATTEMPTS


def test_cleanup_purges_exhausted_failed_rows_after_90_days(db: Any) -> None:
    now = timezone.now()
    for name, attempts, age in [
        ("old", MAX_ATTEMPTS, 91),
        ("recent", MAX_ATTEMPTS, 89),
        ("retrying", 2, 91),
    ]:
        row = EmailOutbox.objects.create(
            to=f"{name}@scholarsync.test",
            kind="test_message",
            status="failed",
            attempts=attempts,
        )
        EmailOutbox.objects.filter(pk=row.pk).update(updated_at=now - timedelta(days=age))
    call_command("cleanup")
    assert set(EmailOutbox.objects.values_list("to", flat=True)) == {
        "recent@scholarsync.test",
        "retrying@scholarsync.test",
    }
