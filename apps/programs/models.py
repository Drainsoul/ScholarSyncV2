from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from apps.files.policy import JPEG, MB, PDF, PNG

ALLOWED_DOCUMENT_TYPES = [PDF, JPEG, PNG]


def default_accepted_types() -> list[str]:
    return list(ALLOWED_DOCUMENT_TYPES)


class School(models.Model):
    class Type(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"
        SUC = "suc", "State university or college"
        LCU = "lcu", "Local college or university"

    class Scale(models.TextChoices):
        PERCENT = "percent", "Percent (0-100)"
        ONE_TO_FIVE = "one_to_five", "1.00 to 5.00 (1.00 highest)"
        FOUR_POINT = "four_point", "4.00 point (4.00 highest)"

    name = models.CharField(max_length=200)
    type = models.CharField(max_length=10, choices=Type)
    grading_scale = models.CharField(max_length=12, choices=Scale)
    is_in_taguig = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="programs_school_name_unique_ci"),
            models.CheckConstraint(
                condition=Q(type__in=["public", "private", "suc", "lcu"]),
                name="programs_school_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(grading_scale__in=["percent", "one_to_five", "four_point"]),
                name="programs_school_scale_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Program(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    applications_open_on = models.DateField(null=True, blank=True)
    applications_close_on = models.DateField(null=True, blank=True)
    max_terms = models.PositiveSmallIntegerField(null=True, blank=True)
    claim_location_default = models.CharField(max_length=200, blank=True)
    min_gwa_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    max_gwa_one_to_five = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    renewal_min_gwa_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    renewal_max_gwa_one_to_five = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    merit_min_gwa_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    merit_max_gwa_one_to_five = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    min_units = models.PositiveSmallIntegerField(null=True, blank=True)
    renewal_min_units = models.PositiveSmallIntegerField(null=True, blank=True)
    min_residency_years = models.PositiveSmallIntegerField(null=True, blank=True)
    requires_registered_voter = models.BooleanField(default=False)
    renewal_no_failing_grades = models.BooleanField(default=False)
    allowed_school_types = ArrayField(
        models.CharField(max_length=10, choices=School.Type), default=list, blank=True
    )
    allowed_schools = models.ManyToManyField(School, blank=True, related_name="programs")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(applications_open_on__isnull=True)
                | Q(applications_close_on__isnull=True)
                | Q(applications_open_on__lte=F("applications_close_on")),
                name="programs_program_window_order",
            ),
            models.CheckConstraint(
                condition=Q(allowed_school_types__contained_by=["public", "private", "suc", "lcu"]),
                name="programs_program_school_types_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ProgramMembership(models.Model):
    class Level(models.TextChoices):
        HEAD = "head", "Program head"
        STAFF = "staff", "Program staff"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="memberships")
    level = models.CharField(max_length=10, choices=Level, default=Level.STAFF)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "program"], name="unique_membership_per_user_program"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.program_id} ({self.level})"


class AcademicTerm(models.Model):
    class Term(models.IntegerChoices):
        FIRST = 1, "1st semester"
        SECOND = 2, "2nd semester"
        SUMMER = 3, "Summer"

    school_year_start = models.PositiveSmallIntegerField()
    term = models.PositiveSmallIntegerField(choices=Term)
    starts_on = models.DateField()
    ends_on = models.DateField()
    is_current = models.BooleanField(default=False)
    sort_key = models.GeneratedField(
        expression=F("school_year_start") * 10 + F("term"),
        output_field=models.IntegerField(),
        db_persist=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_key"]
        constraints = [
            models.CheckConstraint(
                condition=Q(term__in=[1, 2, 3]), name="programs_term_value_valid"
            ),
            models.CheckConstraint(
                condition=Q(starts_on__lt=F("ends_on")), name="programs_term_starts_before_ends"
            ),
            models.UniqueConstraint(
                fields=["school_year_start", "term"], name="programs_term_unique_per_year"
            ),
            models.UniqueConstraint(
                fields=["is_current"],
                condition=Q(is_current=True),
                name="programs_one_current_term",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.get_term_display()}, SY {self.school_year_start}–{self.school_year_start + 1}"
        )


class BenefitTier(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="tiers")
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=80)
    base_amount = models.DecimalField(max_digits=12, decimal_places=2)
    merit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    effective_from = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name="+")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["program", "code", "effective_from"],
                name="programs_tier_unique_per_term",
            ),
            models.CheckConstraint(
                condition=Q(base_amount__gte=0), name="programs_tier_base_amount_gte_0"
            ),
            models.CheckConstraint(
                condition=Q(merit_amount__gte=0), name="programs_tier_merit_amount_gte_0"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class RequiredDocument(models.Model):
    class AppliesTo(models.TextChoices):
        NEW = "new", "New applicants"
        RENEWAL = "renewal", "Renewals"
        BOTH = "both", "New applicants and renewals"

    program = models.ForeignKey(
        Program, on_delete=models.CASCADE, related_name="required_documents"
    )
    code = models.SlugField(max_length=40)
    label = models.CharField(max_length=200)
    help_text = models.TextField(blank=True)
    applies_to = models.CharField(max_length=10, choices=AppliesTo, default=AppliesTo.BOTH)
    is_required = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    accepted_types = ArrayField(models.CharField(max_length=100), default=default_accepted_types)
    max_bytes = models.PositiveIntegerField(default=10 * MB)
    # Switched off, never deleted (M11b): uploads point to it.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["program", "code"], name="programs_doc_unique_code"),
            models.CheckConstraint(
                condition=Q(accepted_types__contained_by=ALLOWED_DOCUMENT_TYPES)
                & ~Q(accepted_types=[]),
                name="programs_doc_types_valid",
            ),
            models.CheckConstraint(
                condition=Q(max_bytes__gt=0) & Q(max_bytes__lte=10 * MB),
                name="programs_doc_max_bytes_valid",
            ),
            models.CheckConstraint(
                condition=Q(applies_to__in=["new", "renewal", "both"]),
                name="programs_doc_applies_to_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.label
