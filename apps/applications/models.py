from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.files.models import StoredFile
from apps.programs.models import AcademicTerm, BenefitTier, Program, RequiredDocument, School
from apps.students.models import StudentProfile


class Application(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        RETURNED = "returned", "Returned"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    class Kind(models.TextChoices):
        NEW = "new", "New"
        RENEWAL = "renewal", "Renewal"

    OPEN_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {Status.DRAFT, Status.SUBMITTED, Status.UNDER_REVIEW, Status.RETURNED}
    )
    TRANSITIONS: ClassVar[dict[str, frozenset[str]]] = {
        Status.DRAFT: frozenset({Status.SUBMITTED, Status.WITHDRAWN}),
        Status.SUBMITTED: frozenset({Status.UNDER_REVIEW, Status.WITHDRAWN}),
        Status.UNDER_REVIEW: frozenset({Status.RETURNED, Status.APPROVED, Status.REJECTED}),
        Status.RETURNED: frozenset({Status.SUBMITTED, Status.WITHDRAWN}),
    }

    profile = models.ForeignKey(
        StudentProfile, on_delete=models.PROTECT, related_name="applications"
    )
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="applications")
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=10, choices=Kind, default=Kind.NEW)
    requested_tier = models.ForeignKey(
        BenefitTier, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    school = models.ForeignKey(
        School, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    school_name = models.CharField(max_length=200, blank=True)
    school_type = models.CharField(max_length=10, choices=School.Type, blank=True)
    course = models.CharField(max_length=200, blank=True)
    year_level = models.PositiveSmallIntegerField(null=True, blank=True)
    gwa = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    gwa_scale = models.CharField(max_length=12, choices=School.Scale, blank=True)
    units = models.PositiveSmallIntegerField(null=True, blank=True)
    match_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=Status, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    first_submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    decision_reason = models.TextField(blank=True)
    on_behalf = models.BooleanField(default=False)
    override_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "draft",
                        "submitted",
                        "under_review",
                        "returned",
                        "approved",
                        "rejected",
                        "withdrawn",
                    ]
                ),
                name="applications_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=["new", "renewal"]), name="applications_kind_valid"
            ),
            models.CheckConstraint(
                condition=Q(school__isnull=True) | Q(school_name=""),
                name="applications_one_school_source",
            ),
            # Submitting freezes the school, so every row past draft has one (a draft withdrawn
            # before it was ever submitted has no snapshot).
            models.CheckConstraint(
                condition=Q(status="draft")
                | Q(status="withdrawn", submitted_at__isnull=True)
                | Q(school__isnull=False)
                | ~Q(school_name=""),
                name="applications_submitted_has_school",
            ),
            models.CheckConstraint(
                condition=Q(on_behalf=True) | Q(override_reason=""),
                name="applications_override_only_on_behalf",
            ),
            models.UniqueConstraint(
                fields=["profile", "program", "term"],
                condition=Q(status__in=["draft", "submitted", "under_review", "returned"]),
                name="applications_one_open_per_term",
            ),
        ]

    def __str__(self) -> str:
        return f"Application {self.pk} ({self.status})"

    @property
    def is_editable(self) -> bool:
        return self.status in (self.Status.DRAFT, self.Status.RETURNED)


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"

    TRANSITIONS: ClassVar[dict[str, frozenset[str]]] = {
        Status.PENDING: frozenset({Status.APPROVED, Status.DECLINED}),
        Status.DECLINED: frozenset({Status.PENDING}),
    }

    requirement = models.ForeignKey(RequiredDocument, on_delete=models.PROTECT)
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="documents")
    status = models.CharField(max_length=10, choices=Status, default=Status.PENDING)
    decline_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["pending", "approved", "declined"]),
                name="applications_document_status_valid",
            ),
            models.UniqueConstraint(
                fields=["application", "requirement"],
                name="applications_document_one_per_requirement",
            ),
        ]

    def __str__(self) -> str:
        return f"Document {self.pk} ({self.status})"


class DocumentFile(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="files")
    file = models.ForeignKey(StoredFile, on_delete=models.PROTECT, related_name="+")
    version = models.PositiveSmallIntegerField()
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["version"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "version"], name="applications_docfile_unique_version"
            ),
            models.UniqueConstraint(
                fields=["document"],
                condition=Q(is_current=True),
                name="applications_docfile_one_current",
            ),
            models.UniqueConstraint(fields=["file"], name="applications_docfile_unique_file"),
        ]

    def __str__(self) -> str:
        return f"Document {self.document_id} v{self.version}"
