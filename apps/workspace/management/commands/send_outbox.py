from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.workspace import emails
from apps.workspace.models import EmailOutbox


class Command(BaseCommand):
    help = "Send failed emails again and queued emails that were never sent."

    def handle(self, *args: Any, **options: Any) -> None:
        stale = timezone.now() - timedelta(minutes=5)
        ids = list(
            EmailOutbox.objects.filter(
                Q(status=EmailOutbox.Status.FAILED, attempts__lt=emails.MAX_ATTEMPTS)
                | Q(status=EmailOutbox.Status.QUEUED, created_at__lt=stale)
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        sent = sum(1 for pk in ids if emails.send(pk))
        self.stdout.write(f"Outbox: {sent} sent, {len(ids) - sent} failed.")
