from typing import ClassVar

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        STAFF = "staff", "Program staff"
        SUPER_ADMIN = "super_admin", "Scholarship office"

    email = models.EmailField(max_length=254)
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=20, choices=Role, default=Role.STUDENT)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
            models.CheckConstraint(
                condition=models.Q(role__in=["student", "staff", "super_admin"]),
                name="accounts_user_role_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else self.email

    @property
    def is_student(self) -> bool:
        return self.role == self.Role.STUDENT

    @property
    def is_program_staff(self) -> bool:
        return self.role == self.Role.STAFF

    @property
    def is_super_admin(self) -> bool:
        return self.role == self.Role.SUPER_ADMIN
