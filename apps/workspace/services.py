"""Writes for the workspace: notifications."""

from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.models import User

from .emails import enqueue
from .models import Notification


def _fit(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def notify(
    *,
    user: User,
    kind: str,
    title: str,
    body: str = "",
    url: str = "",
    email_context: dict[str, str] | None = None,
) -> Notification:
    """Tell one user something in the app and, given an email context, by email too.

    The caller's change is already audited, so this writes no audit event of its own.
    """
    row = Notification.objects.create(
        recipient=user,
        kind=kind,
        title=_fit(title, 200),
        body=_fit(body, 500),
        url=url,
    )
    if email_context is not None:
        enqueue(to=user.email, kind=kind, context=email_context)
    return row


def mark_read(*, user: User, pk: int) -> Notification:
    """Mark one of the user's notifications read; the first time it was read is kept."""
    row = get_object_or_404(Notification, recipient=user, pk=pk)
    if row.read_at is None:
        row.read_at = timezone.now()
        row.save(update_fields=["read_at"])
    return row


def mark_all_read(*, user: User) -> int:
    return Notification.objects.filter(recipient=user, read_at=None).update(read_at=timezone.now())
