"""The email outbox: every message the app sends is a row first, so failures can be retried.

The context is a plain-string whitelist per kind and is emptied once the message is sent (or has
given up), so tokens and links never sit in the database longer than needed.

When the row is committed during a web request, the send waits for `request_finished`, after the
response has gone out: a slow SMTP server never delays a page, and a password reset for a known
address takes as long as one for an unknown address. Anywhere else (commands, the worker, the demo
loader) it sends as soon as the transaction commits.
"""

import logging
from contextvars import ContextVar
from typing import Any

from django.core.mail import EmailMultiAlternatives
from django.core.mail.message import make_msgid
from django.core.signals import request_finished, request_started
from django.db import connections, transaction
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailOutbox

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5

# kind -> the context keys its templates may use. Anything else is dropped at enqueue.
_NAME = frozenset({"full_name"})
KINDS: dict[str, frozenset[str]] = {
    # Sent before the address is verified, so no name: anyone can type anything into it.
    "email_confirmation_signup": frozenset({"activate_url"}),
    "email_confirmation": frozenset({"activate_url"}),
    "password_reset_key": frozenset({"password_reset_url", "full_name"}),
    "account_already_exists": frozenset({"signup_url", "password_reset_url", "full_name"}),
    "password_changed": _NAME,
    "password_reset": _NAME,
    "email_changed": _NAME,
    "email_deleted": frozenset({"deleted_email", "full_name"}),
    "password_set": _NAME,
    "account_connected": frozenset({"provider_name", "full_name"}),
    "account_disconnected": frozenset({"provider_name", "full_name"}),
    # The address is unverified, so no name either.
    "profile_invite": frozenset({"claim_url"}),
    # Sent to the student's own (verified) address, so the name is fine.
    "application_received": frozenset({"full_name", "program_name", "application_url"}),
    "application_returned": frozenset({"full_name", "program_name", "application_url"}),
    "application_decided": frozenset({"full_name", "program_name", "application_url", "outcome"}),
}


def enqueue(*, to: str, kind: str, context: dict[str, str]) -> EmailOutbox:
    allowed = KINDS[kind]  # KeyError for an unknown kind: a bug, not user input
    row = EmailOutbox.objects.create(
        to=to, kind=kind, context={k: v for k, v in context.items() if k in allowed}
    )
    transaction.on_commit(lambda: _send_or_defer(row.pk))
    return row


# Row ids committed during the current request; None outside a request.
_after_response: ContextVar[list[int] | None] = ContextVar("emails_after_response", default=None)


def _send_or_defer(row_id: int) -> None:
    queue = _after_response.get()
    if queue is None:
        send(row_id)
    else:
        queue.append(row_id)


@receiver(request_started, dispatch_uid="workspace.emails.start_queue")
def _start_queue(**kwargs: Any) -> None:
    _after_response.set([])


@receiver(request_finished, dispatch_uid="workspace.emails.send_queue")
def _send_queue(**kwargs: Any) -> None:
    queue = _after_response.get()
    _after_response.set(None)
    if not queue:
        return
    for row_id in queue:
        try:
            send(row_id)
        except Exception:  # send() never raises; a signal receiver must not either
            logger.exception("Email %s could not be sent after the response.", row_id)
    # Django closed the request's connections before this ran; close the one send() reopened
    # (outside a test transaction), as the next request would.
    for connection in connections.all(initialized_only=True):
        if not connection.in_atomic_block:
            connection.close_if_unusable_or_obsolete()


def send(row_id: int) -> bool:
    """Send one row. True only if this call sent it. Never raises."""
    try:
        with transaction.atomic():
            row = EmailOutbox.objects.select_for_update(skip_locked=True).filter(pk=row_id).first()
            if row is None or row.status == EmailOutbox.Status.SENT or row.attempts >= MAX_ATTEMPTS:
                return False
            try:
                parts = _render(row)
            except Exception as exc:
                # Template errors can echo context values (tokens, links): keep the class only.
                return _fail(row, f"{type(exc).__name__} while rendering")
            try:
                message_id = _deliver(row, *parts)
            except Exception as exc:
                return _fail(row, f"{type(exc).__name__}: {exc}"[:500])
            row.status = EmailOutbox.Status.SENT
            row.sent_at = timezone.now()
            row.provider_message_id = message_id
            row.context = {}
            row.last_error = ""
            row.save()
            return True
    except Exception:
        logger.exception("Email %s could not be processed.", row_id)
        return False


def _fail(row: EmailOutbox, error: str) -> bool:
    row.attempts += 1
    row.status = EmailOutbox.Status.FAILED
    row.last_error = error
    if row.attempts >= MAX_ATTEMPTS:
        row.context = {}
    row.save()
    logger.warning("Email %s failed (attempt %s).", row.pk, row.attempts)
    return False


def _render(row: EmailOutbox) -> tuple[str, str, str]:
    template = f"emails/{row.kind}"
    subject = " ".join(render_to_string(f"{template}_subject.txt", row.context).split())
    text = render_to_string(f"{template}.txt", row.context)
    html = render_to_string(f"{template}.html", row.context)
    return subject, text, html


def _deliver(row: EmailOutbox, subject: str, text: str, html: str) -> str:
    message_id = make_msgid()
    message = EmailMultiAlternatives(subject, text, to=[row.to], headers={"Message-ID": message_id})
    message.attach_alternative(html, "text/html")
    message.send(fail_silently=False)
    return message_id
