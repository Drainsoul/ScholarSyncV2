"""Distribution schedules, disbursements and budgets (spec §4.7)."""

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.awards.models import ScholarTerm
from apps.programs.models import AcademicTerm, Program


class DistributionSchedule(models.Model):
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="schedules")
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name="+")
    distribution_date = models.DateField()
    claim_location = models.CharField(max_length=200)
    frequency_label = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-distribution_date", "-pk"]

    def __str__(self) -> str:
        return f"{self.program_id}: {self.distribution_date:%Y-%m-%d}"


class Disbursement(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Prepared"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        RELEASED = "released", "Released"

    LIVE_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {Status.PENDING, Status.APPROVED, Status.RELEASED}
    )
    TRANSITIONS: ClassVar[dict[str, frozenset[str]]] = {
        Status.PENDING: frozenset({Status.APPROVED, Status.REJECTED}),
        Status.APPROVED: frozenset({Status.RELEASED, Status.PENDING}),
        Status.REJECTED: frozenset({Status.PENDING}),
        Status.RELEASED: frozenset(),
    }

    scholar_term = models.ForeignKey(
        ScholarTerm, on_delete=models.PROTECT, related_name="disbursements"
    )
    schedule = models.ForeignKey(
        DistributionSchedule, on_delete=models.PROTECT, related_name="disbursements"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    merit = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status, default=Status.PENDING)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scholar_term", "schedule"], name="money_one_payout_per_schedule"
            ),
            models.UniqueConstraint(
                fields=["scholar_term"],
                condition=Q(status__in=["pending", "approved", "released"]),
                name="money_one_live_payout_per_term",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "approved", "rejected", "released"]),
                name="money_status_valid",
            ),
            models.CheckConstraint(condition=Q(amount__gte=0), name="money_amount_gte_0"),
        ]

    def __str__(self) -> str:
        return f"{self.scholar_term_id} in {self.schedule_id} ({self.status})"


class Budget(models.Model):
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="budgets")
    fiscal_year = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["program", "fiscal_year"], name="money_one_budget_per_year"
            ),
            models.CheckConstraint(condition=Q(amount__gte=0), name="money_budget_gte_0"),
        ]

    def __str__(self) -> str:
        return f"{self.program_id} {self.fiscal_year}"
