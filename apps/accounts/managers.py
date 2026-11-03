from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from .models import User


def normalise_email(email: str | None) -> str:
    """Strip and lower-case the whole address: login is an exact match on the stored value."""
    return (email or "").strip().lower()


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create(self, email: str, password: str | None, **extra: Any) -> "User":
        email = normalise_email(email)
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=email, **extra)
        if password is None:
            user.set_unusable_password()
        else:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def get_by_natural_key(self, username: str | None) -> "User":
        return super().get_by_natural_key(normalise_email(username))

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str, **extra: Any) -> "User":
        # A technical account only: it can use /django-admin/ but holds no program or office role.
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", "staff")
        return self._create(email, password, **extra)
