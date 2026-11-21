from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Length
from django.db.models.lookups import GreaterThanOrEqual, LessThanOrEqual

from apps.files.models import StoredFile
from apps.programs.models import Program


class Report(models.Model):
    """A program's periodic report to the scholarship office (spec §4.8, M11c; the head reviews a
    staff member's report first, rev 33)."""

    class Status(models.TextChoices):
        WITH_HEAD = "with_head", "Waiting for the head"
        APPROVED = "approved", "Approved, not sent yet"
        SUBMITTED = "submitted", "Waiting for the office"
        ACCEPTED = "accepted", "Accepted"
        RETURNED = "returned", "Returned"

    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="reports")
    title = models.CharField(max_length=200)
    period_start = models.DateField()
    period_end = models.DateField()
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.SUBMITTED)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    submitted_at = models.DateTimeField()
    # The head reviews a staff member's report first (rev 33).
    head_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    head_reviewed_at = models.DateTimeField(null=True, blank=True)
    # Who last sent it to the office, and when; unset until the office first sees it (rev 33).
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=["with_head", "approved", "submitted", "accepted", "returned"]
                ),
                name="reports_report_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(period_end__gte=F("period_start")),
                name="reports_report_period_order",
            ),
            models.CheckConstraint(
                condition=GreaterThanOrEqual(Length("title"), 1),
                name="reports_report_title_len",
            ),
            models.CheckConstraint(
                condition=LessThanOrEqual(Length("description"), 2000),
                name="reports_report_description_len",
            ),
            models.CheckConstraint(
                condition=LessThanOrEqual(Length("review_note"), 1000),
                name="reports_report_note_len",
            ),
        ]
        indexes = [
            models.Index(fields=["program", "status", "submitted_at"]),
            models.Index(fields=["status", "submitted_at"]),
        ]

    def __str__(self) -> str:
        return f"Report #{self.pk}"


class ReportFile(models.Model):
    """One version of a report's PDF; a resubmission may add another."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="files")
    file = models.OneToOneField(StoredFile, on_delete=models.PROTECT, related_name="report_file")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return f"Report file #{self.pk}"
