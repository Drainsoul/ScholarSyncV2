from allauth.account.internal.stagekit import LOGIN_SESSION_KEY
from allauth.account.models import EmailAddress, EmailConfirmation
from allauth.account.utils import user_pk_to_url_str
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
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


def _end_sessions(user: User) -> int:
    """Delete every session signed in as `user`, or holding a half-finished login for it."""
    pending = user_pk_to_url_str(user)
    ended = 0
    for session in Session.objects.iterator():
        data = session.get_decoded()
        login = data.get(LOGIN_SESSION_KEY)
        if data.get(SESSION_KEY) == str(user.pk) or (
            isinstance(login, dict) and login.get("user_pk") == pending
        ):
            session.delete()
            ended += 1
    return ended


@transaction.atomic
def promote_to_office(*, user: User, full_name: str, password: str) -> User:
    """Make an existing account the scholarship office's, from the command line.

    For an operator whose address signed up on the site before `create_office_admin` ran. The
    command decides whether that is allowed. This sets the role, name and password, marks the
    address verified and primary, and removes every way back in for whoever created the account:
    its other addresses, linked Google accounts, pending confirmations and sessions.
    """
    was_verified = EmailAddress.objects.filter(
        user=user, email__iexact=user.email, verified=True
    ).exists()
    validate_password(password, user=User(email=user.email, full_name=full_name))
    user.role = User.Role.SUPER_ADMIN
    user.full_name = full_name
    user.set_password(password)  # also invalidates outstanding password-reset links
    user.save()
    # Deleting the other addresses also deletes their pending confirmations (CASCADE).
    others = EmailAddress.objects.filter(user=user).exclude(email__iexact=user.email)
    emails_removed = others.delete()[1].get(EmailAddress._meta.label, 0)
    social_removed = (
        SocialAccount.objects.filter(user=user).delete()[1].get(SocialAccount._meta.label, 0)
    )
    address = EmailAddress.objects.filter(user=user, email__iexact=user.email).first()
    if address is None:
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    else:
        EmailConfirmation.objects.filter(email_address=address).delete()
        address.verified = True
        address.primary = True
        address.save(update_fields=["verified", "primary"])
    sessions_ended = _end_sessions(user)
    record(
        actor=None,
        action="user.promoted",
        target=user,
        data={
            "role": str(User.Role.SUPER_ADMIN),
            "was_verified": was_verified,
            "emails_removed": emails_removed,
            "social_removed": social_removed,
            "sessions_ended": sessions_ended,
        },
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
