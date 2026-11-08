from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.files.models import StoredFile
from apps.programs.models import Program, School
from apps.students.barangays import BARANGAYS


class StudentProfile(models.Model):
    class Sex(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    suffix = models.CharField(max_length=20, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=10, choices=Sex, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address_line = models.CharField(max_length=255, blank=True)
    barangay = models.CharField(max_length=40, choices=BARANGAYS, blank=True)
    residing_since = models.PositiveSmallIntegerField(null=True, blank=True)
    is_registered_voter = models.BooleanField(null=True, blank=True)
    monthly_household_income = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    photo = models.ForeignKey(
        StoredFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_for = models.ForeignKey(
        Program,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_profiles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(sex__in=["female", "male", ""]), name="students_profile_sex_valid"
            ),
            models.CheckConstraint(
                condition=Q(barangay__in=[value for value, _ in BARANGAYS] + [""]),
                name="students_profile_barangay_valid",
            ),
            models.CheckConstraint(
                condition=Q(monthly_household_income__isnull=True)
                | Q(monthly_household_income__gte=0),
                name="students_profile_income_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return self.full_name

    @property
    def full_name(self) -> str:
        parts = (self.first_name, self.middle_name, self.last_name, self.suffix)
        return " ".join(part for part in parts if part)


class FamilyMember(models.Model):
    class Relation(models.TextChoices):
        FATHER = "father", "Father"
        MOTHER = "mother", "Mother"
        GUARDIAN = "guardian", "Guardian"
        SIBLING = "sibling", "Sibling"

    profile = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="family")
    relation = models.CharField(max_length=10, choices=Relation)
    name = models.CharField(max_length=200)
    occupation = models.CharField(max_length=100, blank=True)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    contact = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(relation__in=["father", "mother", "guardian", "sibling"]),
                name="students_family_relation_valid",
            ),
            models.CheckConstraint(
                condition=Q(monthly_income__isnull=True) | Q(monthly_income__gte=0),
                name="students_family_income_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.relation})"


class EducationRecord(models.Model):
    class Level(models.TextChoices):
        ELEMENTARY = "elementary", "Elementary"
        JHS = "jhs", "Junior high school"
        SHS = "shs", "Senior high school"
        ALS = "als", "ALS"
        COLLEGE = "college", "College"

    profile = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="education")
    level = models.CharField(max_length=12, choices=Level)
    school = models.ForeignKey(School, null=True, blank=True, on_delete=models.PROTECT)
    school_name = models.CharField(max_length=200, blank=True)
    school_type = models.CharField(max_length=10, choices=School.Type, blank=True)
    gwa_scale = models.CharField(max_length=12, choices=School.Scale, blank=True)
    course = models.CharField(max_length=200, blank=True)
    year_level = models.PositiveSmallIntegerField(null=True, blank=True)
    gwa = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    units = models.PositiveSmallIntegerField(null=True, blank=True)
    year_from = models.PositiveSmallIntegerField(null=True, blank=True)
    year_to = models.PositiveSmallIntegerField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(level__in=["elementary", "jhs", "shs", "als", "college"]),
                name="students_education_level_valid",
            ),
            models.CheckConstraint(
                condition=Q(school__isnull=False, school_name="")
                | Q(school__isnull=True, school_name__gt=""),
                name="students_education_one_school_source",
            ),
            models.CheckConstraint(
                condition=Q(year_from__isnull=True)
                | Q(year_to__isnull=True)
                | Q(year_from__lte=F("year_to")),
                name="students_education_years_ordered",
            ),
            models.CheckConstraint(
                condition=Q(gwa__isnull=True) | ~Q(gwa_scale=""),
                name="students_education_gwa_needs_scale",
            ),
            models.CheckConstraint(
                condition=Q(gwa__isnull=True)
                | (Q(gwa_scale="percent") & Q(gwa__gte=50) & Q(gwa__lte=100))
                | (Q(gwa_scale="one_to_five") & Q(gwa__gte=1) & Q(gwa__lte=5))
                | (Q(gwa_scale="four_point") & Q(gwa__gte=0) & Q(gwa__lte=4)),
                name="students_education_gwa_in_scale_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_level_display()}: {self.school or self.school_name}"
