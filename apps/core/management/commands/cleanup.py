from datetime import datetime, timedelta
from typing import Any

from allauth.usersessions.models import UserSession
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import ProtectedError, Q
from django.utils import timezone

from apps.awards.models import ScholarImport
from apps.files import storage
from apps.files.models import StoredFile
from apps.workspace.emails import MAX_ATTEMPTS
from apps.workspace.models import EmailOutbox

# Import files hold names and birth dates; they leave storage a week after upload (spec §7, M12).
IMPORT_DAYS = 7
EXPIRED = "expired"


def purge_imports(now: datetime) -> int:
    """Delete the object of every import file older than IMPORT_DAYS and return how many.

    The row goes too, unless a ScholarImport points at it (PROTECT): that row is marked rejected
    ("expired") so nothing can use it again. Without storage nothing happens; a storage error
    leaves the row for the next run. Deleting an object that's already gone succeeds."""
    if not storage.is_configured():
        return 0
    referenced = set(ScholarImport.objects.values_list("file_id", flat=True))
    old = (
        StoredFile.objects.filter(
            purpose=StoredFile.Purpose.IMPORT, created_at__lt=now - timedelta(days=IMPORT_DAYS)
        )
        .exclude(status=StoredFile.Status.REJECTED, rejected_reason=EXPIRED)
        .order_by("created_at")
    )
    purged = 0
    for file in old.iterator():
        try:
            for key in {file.key, file.final_key}:
                storage.delete(key)
        except storage.StorageUnavailable:
            break  # one timeout per run, not one per file: the worker also sends email
        if file.pk not in referenced:
            try:
                file.delete()
                purged += 1
                continue
            except ProtectedError:
                pass  # an import started from this file since the run began
        StoredFile.objects.filter(pk=file.pk).update(
            status=StoredFile.Status.REJECTED, rejected_reason=EXPIRED, updated_at=now
        )
        purged += 1
    return purged


class Command(BaseCommand):
    help = "Delete expired housekeeping rows (sessions, old sent emails, stale uploads)."

    def handle(self, *args: Any, **options: Any) -> None:
        call_command("clearsessions")
        # The session list's rows (IP address, browser) go once their session has ended (M13).
        UserSession.objects.exclude(session_key__in=Session.objects.values("session_key")).delete()
        now = timezone.now()
        cutoff = now - timedelta(days=90)
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
        purge_imports(now)
        # An import record keeps its (expired) file row: the FK is PROTECT.
        StoredFile.objects.filter(
            Q(
                status=StoredFile.Status.PENDING,
                created_at__lt=now - timedelta(days=1),
            )
            | Q(
                status=StoredFile.Status.REJECTED,
                updated_at__lt=now - timedelta(days=30),
            )
        ).exclude(pk__in=ScholarImport.objects.values("file_id")).delete()
