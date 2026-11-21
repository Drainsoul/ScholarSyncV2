"""Support requests and their replies: reads and writes (spec §4.8 rev 35).

A student's message is free text, so it is never emailed. A staff reply is either kept in the app
(the student gets a notification) or emailed from the app to the student's account email; either
way it is saved, so the student reads every answer under Replies. Text never goes into audit data.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, QuerySet
from django.http import Http404, HttpRequest
from django.urls import reverse

from apps.accounts.models import User
from apps.core.audit import record
from apps.programs.models import Program

from .emails import enqueue
from .models import ReplyTemplate, SupportReply, SupportRequest
from .services import notify

DAILY_LIMIT = 5
LIMIT_MESSAGE = "You've sent 5 messages today. Try again tomorrow."
SEND_SUCCESS = "Message sent. You'll find the answer under Replies."
DUPLICATE_MESSAGE = "This reply was already sent."
CLOSED_ACCOUNT_MESSAGE = "This student's account is closed. Reply in the app instead."
DUPLICATE_WINDOW = timedelta(seconds=60)
OFFICE_TABS = {"open": "Open", "answered": "Answered"}
OFFICE_NAME = "The scholarship office"


@transaction.atomic
def send(
    *,
    sender: User,
    topic: str,
    program: Program | None,
    message: str,
    now: datetime,
    request: HttpRequest | None = None,
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
        request=request,
    )
    return row


def _mark_answered(
    row: SupportRequest, actor: User, now: datetime, request: HttpRequest | None
) -> None:
    """Answer a locked open row; an answered one stays as it was."""
    if row.status == SupportRequest.Status.ANSWERED:
        return
    row.status = SupportRequest.Status.ANSWERED
    row.answered_by = actor
    row.answered_at = now
    row.save(update_fields=["status", "answered_by", "answered_at"])
    record(actor=actor, action="support.answered", target=row, program=row.program, request=request)


@transaction.atomic
def answer(
    *,
    actor: User,
    request_row: SupportRequest,
    now: datetime,
    request: HttpRequest | None = None,
) -> SupportRequest:
    """Mark a request answered; one that already is stays as it was, with no second event."""
    row = SupportRequest.objects.select_for_update().get(pk=request_row.pk)
    _mark_answered(row, actor, now, request)
    return row


def signer(request_row: SupportRequest, author: User) -> str:
    """Who a reply comes from, as the student reads it: never the person's name."""
    if author.is_super_admin or request_row.program is None:
        return OFFICE_NAME
    return request_row.program.name


def replies_url() -> str:
    return settings.SITE_URL + reverse("support:replies")


def _add_reply(
    *,
    actor: User,
    request_row: SupportRequest,
    channel: str,
    subject: str,
    body: str,
    template: ReplyTemplate | None,
    now: datetime,
    request: HttpRequest | None,
) -> SupportReply:
    row = (
        SupportRequest.objects.select_for_update(of=("self",))
        .select_related("sender", "program")
        .get(pk=request_row.pk)
    )
    sender = row.sender
    if channel == SupportReply.Channel.EMAIL and not sender.is_active:
        raise ValidationError(CLOSED_ACCOUNT_MESSAGE)
    if SupportReply.objects.filter(
        request=row,
        author=actor,
        channel=channel,
        body=body,
        created_at__gte=now - DUPLICATE_WINDOW,
    ).exists():
        raise ValidationError(DUPLICATE_MESSAGE)
    reply = SupportReply(
        request=row, author=actor, channel=channel, subject=subject, body=body, template=template
    )
    if channel == SupportReply.Channel.EMAIL:
        reply.email = enqueue(
            to=sender.email,
            kind="support_reply",
            context={
                "full_name": sender.full_name or "there",
                "subject": subject,
                "body": body,
                "replies_url": replies_url(),
            },
        )
    reply.save()
    _mark_answered(row, actor, now, request)
    notify(
        user=sender,
        kind="support_replied",
        title=f"{signer(row, actor)} answered your message",
        url=reverse("support:replies"),
    )
    record(
        actor=actor,
        action="support.replied",
        target=row,
        program=row.program,
        data={
            "request": row.pk,
            "reply": reply.pk,
            "channel": channel,
            "template": template.pk if template is not None else None,
            "program": row.program_id,
        },
        request=request,
    )
    return reply


@transaction.atomic
def reply(
    *,
    actor: User,
    request_row: SupportRequest,
    body: str,
    template: ReplyTemplate | None,
    now: datetime,
    request: HttpRequest | None = None,
) -> SupportReply:
    """Answer in the app: saved, and the student gets a notification (no email)."""
    return _add_reply(
        actor=actor,
        request_row=request_row,
        channel=SupportReply.Channel.APP,
        subject="",
        body=body,
        template=template,
        now=now,
        request=request,
    )


@transaction.atomic
def email_reply(
    *,
    actor: User,
    request_row: SupportRequest,
    subject: str,
    body: str,
    template: ReplyTemplate | None,
    now: datetime,
    request: HttpRequest | None = None,
) -> SupportReply:
    """Answer by email to the sender's account email; also saved and notified in the app."""
    return _add_reply(
        actor=actor,
        request_row=request_row,
        channel=SupportReply.Channel.EMAIL,
        subject=subject,
        body=body,
        template=template,
        now=now,
        request=request,
    )


def _scope(program: Program | None) -> QuerySet[SupportRequest]:
    """The office (None) sees every request; a program's staff see that program's."""
    rows = SupportRequest.objects.all()
    return rows if program is None else rows.filter(program=program)


def open_count(program: Program | None = None) -> int:
    return _scope(program).filter(status=SupportRequest.Status.OPEN).count()


def inbox_rows(program: Program | None, tab: str) -> QuerySet[SupportRequest]:
    """Open requests oldest first (the next to answer on top); answered ones newest first."""
    rows = (
        _scope(program)
        .select_related("sender", "program", "answered_by")
        .annotate(reply_count=Count("replies"))
    )
    if tab == "answered":
        return rows.filter(status=SupportRequest.Status.ANSWERED).order_by("-created_at", "-pk")
    return rows.filter(status=SupportRequest.Status.OPEN).order_by("created_at", "pk")


def scoped_request(program: Program | None, pk: int) -> SupportRequest:
    found = _scope(program).select_related("sender", "program", "answered_by").filter(pk=pk)
    row = found.first()
    if row is None:
        raise Http404
    return row


def own_rows(user: User) -> QuerySet[SupportRequest]:
    return (
        SupportRequest.objects.filter(sender=user)
        .select_related("program")
        .annotate(reply_count=Count("replies"))
        .order_by("-created_at", "-pk")
    )


def _own_replies(user: User) -> QuerySet[SupportReply]:
    return SupportReply.objects.filter(request__sender=user)


def student_replies(user: User) -> QuerySet[SupportReply]:
    return (
        _own_replies(user)
        .select_related("request", "request__program", "author")
        .order_by("-created_at", "-pk")
    )


def unread_replies(user: User) -> int:
    return _own_replies(user).filter(read_at=None).count()


def mark_replies_read(user: User, now: datetime) -> int:
    return _own_replies(user).filter(read_at=None).update(read_at=now)
