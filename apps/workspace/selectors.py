"""Reads for the workspace: notifications."""

from django.db.models import QuerySet

from apps.accounts.models import User

from .models import Notification


def notifications_for(user: User) -> QuerySet[Notification]:
    """The user's own notifications, newest first."""
    return Notification.objects.filter(recipient=user).order_by("-created_at", "-pk")


def unread_count(user: User) -> int:
    return Notification.objects.filter(recipient=user, read_at=None).count()
