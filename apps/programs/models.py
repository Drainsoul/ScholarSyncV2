from django.conf import settings
from django.db import models


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
