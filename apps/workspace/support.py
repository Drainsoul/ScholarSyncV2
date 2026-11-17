"""Students' messages to the scholarship office: reads and writes.

Messages are free text, so they never go into an email (spec §9); the office reads them in its
inbox and replies from its own mail client.
"""

from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet

from apps.accounts.models import User
from apps.core.audit import record
from apps.programs.models import Program

from .models import SupportRequest

DAILY_LIMIT = 5
LIMIT_MESSAGE = "You've sent 5 messages today. The office will reply by email; try again tomorrow."
OFFICE_TABS = {"open": "Open", "answered": "Answered"}


@transaction.atomic
def send(
    *, sender: User, topic: str, program: Program | None, message: str, now: datetime
) -> SupportRequest:
    """Send a message, at most `DAILY_LIMIT` in any 24 hours per student.

    The sender's row is locked first, so two posts at once can't both slip under the limit."""
    User.objects.select_for_update().get(pk=sender.pk)
    recent = SupportRequest.objects.filter(
        sender=sender, created_at__gt=now - timedelta(hours=24)
    ).count()
    if recent >= DAILY_LIMIT:
        raise ValidationError(LIMIT_MESSAGE)
    row = SupportRequest.objects.create(
        sender=sender, topic=topic, program=program, message=message
    )
    record(
        actor=sender,
        action="support.sent",
        target=row,
        program=program,
        data={"topic": topic, "program": program.pk if program is not None else None},
    )
    return row


@transaction.atomic
def answer(*, actor: User, request_row: SupportRequest, now: datetime) -> SupportRequest:
    """Mark a request answered; one that already is stays as it was, with no second event."""
    row = SupportRequest.objects.select_for_update().get(pk=request_row.pk)
    if row.status == SupportRequest.Status.ANSWERED:
        return row
    row.status = SupportRequest.Status.ANSWERED
    row.answered_by = actor
    row.answered_at = now
    row.save(update_fields=["status", "answered_by", "answered_at"])
    record(actor=actor, action="support.answered", target=row, program=row.program)
    return row


def open_count() -> int:
    return SupportRequest.objects.filter(status=SupportRequest.Status.OPEN).count()


def office_rows(tab: str) -> QuerySet[SupportRequest]:
    """Open requests oldest first (the next to answer on top); answered ones newest first."""
    rows = SupportRequest.objects.select_related("sender", "program")
    if tab == "answered":
        return rows.filter(status=SupportRequest.Status.ANSWERED).order_by("-created_at", "-pk")
    return rows.filter(status=SupportRequest.Status.OPEN).order_by("created_at", "pk")


def own_rows(user: User) -> QuerySet[SupportRequest]:
    return (
        SupportRequest.objects.filter(sender=user)
        .select_related("program")
        .order_by("-created_at", "-pk")
    )
