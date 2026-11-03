from datetime import timedelta
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.workspace.models import EmailOutbox


class Command(BaseCommand):
    help = "Delete expired housekeeping rows (sessions, old sent emails)."

    def handle(self, *args: Any, **options: Any) -> None:
        call_command("clearsessions")
        cutoff = timezone.now() - timedelta(days=90)
        EmailOutbox.objects.filter(status=EmailOutbox.Status.SENT, sent_at__lt=cutoff).delete()
