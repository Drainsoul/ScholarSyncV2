from allauth.account.forms import default_token_generator
from allauth.account.internal.stagekit import LOGIN_SESSION_KEY
from allauth.account.models import EmailAddress, EmailConfirmation
from allauth.account.utils import user_pk_to_url_str
from allauth.socialaccount.models import SocialAccount
from allauth.usersessions.models import UserSession
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.urls import reverse

from apps.core.audit import client_ip, hash_ip, record
from apps.core.permissions import require_office
from apps.workspace.emails import enqueue

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
    UserSession.objects.filter(user=user).delete()
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


EMAIL_TAKEN = "An account with this email already exists."


def _email_taken(email: str) -> bool:
    """Any account's email, or any address a user added in allauth (verified or not)."""
    return (
        User.objects.filter(email__iexact=email).exists()
        or EmailAddress.objects.filter(email__iexact=email).exists()
    )


NOT_YOURSELF = "You can't deactivate your own account."
KEEP_ONE_OFFICE = "Keep at least one active scholarship office account."


def set_password_url(user: User) -> str:
    """allauth's password-reset-from-key link: the account's first password, valid for
    PASSWORD_RESET_TIMEOUT (3 days); after that the person uses "Forgot password"."""
    return settings.SITE_URL + reverse(
        "account_reset_password_from_key",
        kwargs={
            "uidb36": user_pk_to_url_str(user),
            "key": default_token_generator.make_token(user),
        },
    )


def send_welcome(*, actor: User, user: User) -> None:
    """Email the set-password link (again). Only active staff and office accounts, and only
    before the first sign-in; a no-op otherwise."""
    require_office(actor)
    if user.role == User.Role.STUDENT or user.last_login is not None or not user.is_active:
        return
    enqueue(
        to=user.email,
        kind="staff_welcome",
        context={
            "full_name": user.full_name,
            "role_label": user.get_role_display(),
            "set_password_url": set_password_url(user),
        },
    )


@transaction.atomic
def create_account(
    *,
    actor: User,
    email: str,
    full_name: str,
    role: User.Role,
    request: HttpRequest | None = None,
) -> User:
    """A staff or office account with no password yet, and the email to set one."""
    require_office(actor)
    email = normalise_email(email)
    if _email_taken(email):
        raise ValidationError({"email": EMAIL_TAKEN})
    try:
        with transaction.atomic():
            user = create_staff_user(
                actor=actor, email=email, full_name=full_name.strip(), role=role
            )
    except IntegrityError:  # a second post raced past the check
        raise ValidationError({"email": EMAIL_TAKEN}) from None
    send_welcome(actor=actor, user=user)
    return user


@transaction.atomic
def end_all_sessions(*, actor: User | None, user: User, request: HttpRequest | None = None) -> int:
    """Sign an account out everywhere. `actor=None` is the operator's command line."""
    if actor is not None:
        require_office(actor)
    ended = _end_sessions(user)
    record(
        actor=actor,
        action="user.sessions_ended",
        target=user,
        data={"account": user.pk, "sessions_ended": ended},
        request=request,
    )
    return ended


@transaction.atomic
def remove_mfa(*, actor: User, user: User, request: HttpRequest | None = None) -> None:
    """Remove a staff or office account's authenticators (a lost phone) and end its sessions; the
    person sets up a new one at the next sign-in."""
    from allauth.mfa.models import Authenticator

    require_office(actor)
    if user.role == User.Role.STUDENT:
        raise ValidationError("Only staff and office accounts are managed here.")
    Authenticator.objects.filter(user=user).delete()
    _end_sessions(user)
    record(
        actor=actor, action="mfa.removed", target=user, data={"account": user.pk}, request=request
    )


@transaction.atomic
def set_account_active(
    *, actor: User, user: User, active: bool, request: HttpRequest | None = None
) -> User:
    """Deactivate (ending every session) or reactivate a staff or office account."""
    require_office(actor)
    # Every active office account first, in pk order: two office accounts deactivating each
    # other at once then decide one after the other, so one always stays active (M12).
    list(
        User.objects.select_for_update()
        .filter(role=User.Role.SUPER_ADMIN, is_active=True)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    locked = User.objects.select_for_update().get(pk=user.pk)
    if locked.role == User.Role.STUDENT:
        raise ValidationError("Only staff and office accounts are managed here.")
    if locked.is_active == active:
        return locked
    if not active:
        if locked.pk == actor.pk:
            raise ValidationError(NOT_YOURSELF)
        others = User.objects.filter(role=User.Role.SUPER_ADMIN, is_active=True).exclude(
            pk=locked.pk
        )
        if locked.role == User.Role.SUPER_ADMIN and not others.exists():
            raise ValidationError(KEEP_ONE_OFFICE)
    locked.is_active = active
    locked.save(update_fields=["is_active"])
    ended = _end_sessions(locked) if not active else 0
    record(
        actor=actor,
        action="user.reactivated" if active else "user.deactivated",
        target=locked,
        data={"role": str(locked.role), "sessions_ended": ended},
        request=request,
    )
    return locked
