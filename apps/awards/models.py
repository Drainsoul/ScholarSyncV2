from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.applications.models import Application
from apps.programs.models import AcademicTerm, BenefitTier, Program, School
from apps.students.models import StudentProfile


class Award(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        INACTIVE = "inactive", "Inactive"
        GRADUATED = "graduated", "Graduated"

    class Source(models.TextChoices):
        APPLIED = "applied", "Applied"
        IMPORTED = "imported", "Imported"
        MANUAL = "manual", "Manual"

    profile = models.ForeignKey(StudentProfile, on_delete=models.PROTECT, related_name="awards")
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="awards")
    tier = models.ForeignKey(BenefitTier, on_delete=models.PROTECT, related_name="+")
    student_number = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=12, choices=Status, default=Status.ACTIVE)
    source = models.CharField(max_length=10, choices=Source)
    source_application = models.OneToOneField(
        Application, null=True, blank=True, on_delete=models.PROTECT, related_name="award"
    )
    started_term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name="+")
    ended_term = models.ForeignKey(
        AcademicTerm, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["active", "suspended", "inactive", "graduated"]),
                name="awards_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(source__in=["applied", "imported", "manual"]),
                name="awards_source_valid",
            ),
            models.UniqueConstraint(
                fields=["profile", "program"],
                condition=Q(status="active"),
                name="awards_one_active_per_program",
            ),
            models.CheckConstraint(
                condition=~Q(source="applied") | Q(source_application__isnull=False),
                name="awards_applied_has_application",
            ),
        ]

    def __str__(self) -> str:
        return f"Award {self.pk} ({self.status})"


class ScholarTerm(models.Model):
    class Compliance(models.TextChoices):
        INCOMPLETE = "incomplete", "Incomplete"
        COMPLETE = "complete", "Complete"

    award = models.ForeignKey(Award, on_delete=models.PROTECT, related_name="terms")
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name="+")
    year_level = models.PositiveSmallIntegerField(null=True, blank=True)
    course = models.CharField(max_length=200, blank=True)
    school = models.ForeignKey(
        School, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    school_name = models.CharField(max_length=200, blank=True)
    school_type = models.CharField(max_length=10, choices=School.Type, blank=True)
    gwa = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    gwa_scale = models.CharField(max_length=12, choices=School.Scale, blank=True)
    units = models.PositiveSmallIntegerField(null=True, blank=True)
    merit = models.BooleanField(default=False)
    merit_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    compliance = models.CharField(max_length=12, choices=Compliance, default=Compliance.INCOMPLETE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["award", "term"], name="awards_one_term_per_award"),
            models.CheckConstraint(
                condition=Q(school__isnull=True) | Q(school_name=""),
                name="awards_term_one_school_source",
            ),
            models.CheckConstraint(
                condition=Q(compliance__in=["incomplete", "complete"]),
                name="awards_compliance_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"Scholar term {self.pk} (award {self.award_id})"
