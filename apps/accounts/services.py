from allauth.account.models import EmailAddress
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.core.audit import record

from .managers import normalise_email
from .models import User


@transaction.atomic
def create_staff_user(
    *,
    actor: User | None,
    email: str,
    full_name: str,
    role: User.Role,
    password: str | None = None,
) -> User:
    """Create a program-staff or scholarship-office account.

    `actor=None` means the command line or the demo; otherwise the actor must be a super admin.
    """
    if role not in (User.Role.STAFF, User.Role.SUPER_ADMIN):
        raise ValueError("Only staff and scholarship-office accounts are created here.")
    if actor is not None and not actor.is_super_admin:
        raise PermissionDenied("Only the scholarship office can create staff accounts.")
    email = normalise_email(email)
    if password is not None:
        validate_password(password, user=User(email=email, full_name=full_name))
    user = User.objects.create_user(email=email, password=password, full_name=full_name, role=role)
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    record(actor=actor, action="user.created", target=user, data={"role": str(role)})
    return user
