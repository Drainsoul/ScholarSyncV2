from datetime import timedelta
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.files.models import StoredFile
from apps.workspace.emails import MAX_ATTEMPTS
from apps.workspace.models import EmailOutbox


class Command(BaseCommand):
    help = "Delete expired housekeeping rows (sessions, old sent emails, stale uploads)."

    def handle(self, *args: Any, **options: Any) -> None:
        call_command("clearsessions")
        cutoff = timezone.now() - timedelta(days=90)
        EmailOutbox.objects.filter(
            Q(status=EmailOutbox.Status.SENT, sent_at__lt=cutoff)
            | Q(
                status=EmailOutbox.Status.FAILED,
                attempts__gte=MAX_ATTEMPTS,
                updated_at__lt=cutoff,
            )
        ).delete()
        # Stale uploads: abandoned pending rows and old rejections. The objects are already gone
        # (the pending/ lifecycle rule, or confirm removed them).
        StoredFile.objects.filter(
            Q(
                status=StoredFile.Status.PENDING,
                created_at__lt=timezone.now() - timedelta(days=1),
            )
            | Q(
                status=StoredFile.Status.REJECTED,
                updated_at__lt=timezone.now() - timedelta(days=30),
            )
        ).delete()
