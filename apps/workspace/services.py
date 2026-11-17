"""Writes for the workspace: notifications."""

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
