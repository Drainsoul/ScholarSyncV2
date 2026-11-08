from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower


class Program(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

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
