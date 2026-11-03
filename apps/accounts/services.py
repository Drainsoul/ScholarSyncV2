from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest

from apps.core.audit import client_ip, hash_ip, record

from .managers import normalise_email
from .models import ConsentRecord, User


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
    if actor is not None and not (actor.is_super_admin and actor.is_active):
        raise PermissionDenied("Only the scholarship office can create staff accounts.")
    email = normalise_email(email)
    if password is not None:
        validate_password(password, user=User(email=email, full_name=full_name))
    user = User.objects.create_user(email=email, password=password, full_name=full_name, role=role)
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    record(actor=actor, action="user.created", target=user, data={"role": str(role)})
    return user


@transaction.atomic
def promote_to_office(*, user: User, full_name: str, password: str) -> User:
    """Make an existing account the scholarship office's, from the command line.

    For an operator whose address signed up on the site before `create_office_admin` ran. The
    command decides whether that is allowed; this sets the role, name and password and marks the
    address verified and primary. The password change also signs out every existing session.
    """
    was_verified = EmailAddress.objects.filter(
        user=user, email__iexact=user.email, verified=True
    ).exists()
    validate_password(password, user=User(email=user.email, full_name=full_name))
    user.role = User.Role.SUPER_ADMIN
    user.full_name = full_name
    user.set_password(password)
    user.save()
    EmailAddress.objects.filter(user=user).exclude(email__iexact=user.email).update(primary=False)
    address = EmailAddress.objects.filter(user=user, email__iexact=user.email).first()
    if address is None:
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    else:
        address.verified = True
        address.primary = True
        address.save(update_fields=["verified", "primary"])
    record(
        actor=None,
        action="user.promoted",
        target=user,
        data={"role": str(User.Role.SUPER_ADMIN), "was_verified": was_verified},
    )
    return user


@transaction.atomic
def record_consent(*, user: User, request: HttpRequest | None) -> ConsentRecord:
    """Store that this user accepted the current privacy notice."""
    consent = ConsentRecord.objects.create(
        user=user,
        notice_version=settings.PRIVACY_NOTICE_VERSION,
        ip_hash=hash_ip(client_ip(request)),
    )
    record(
        actor=user,
        action="consent.recorded",
        target=consent,
        data={"notice_version": consent.notice_version},
        request=request,
    )
    return consent
