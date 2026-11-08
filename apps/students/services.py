"""Student profile writes. Every service is audited; audit data holds field names, never values."""

import secrets
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import models, transaction
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import record_consent
from apps.core import audit
from apps.files.models import StoredFile
from apps.programs.models import Program
from apps.programs.selectors import membership_for
from apps.students.models import EducationRecord, FamilyMember, ProfileInvite, StudentProfile
from apps.students.selectors import INVALID_LINK, claim_problem, find_invite, hash_token
from apps.workspace.emails import enqueue

PERSONAL_FIELDS = (
    "first_name",
    "middle_name",
    "last_name",
    "suffix",
    "birth_date",
    "sex",
    "phone",
    "address_line",
    "barangay",
    "residing_since",
    "is_registered_voter",
    "monthly_household_income",
)
FAMILY_FIELDS = ("relation", "name", "occupation", "monthly_income", "contact")
EDUCATION_FIELDS = (
    "level",
    "school",
    "school_name",
    "school_type",
    "gwa_scale",
    "course",
    "year_level",
    "gwa",
    "units",
    "year_from",
    "year_to",
    "is_current",
)


def _require_student(user: User) -> None:
    if not user.is_student:
        raise PermissionDenied("Only students can edit a profile.")


def _require_owner(user: User, profile: StudentProfile) -> None:
    if profile.user_id != user.pk:
        raise PermissionDenied("Not your profile.")


def _snapshot(instance: models.Model, fields: Iterable[str]) -> dict[str, object]:
    return {name: getattr(instance, name) for name in fields}


def _assign(instance: models.Model, data: Mapping[str, object], fields: Iterable[str]) -> None:
    for name in fields:
        if name in data:
            setattr(instance, name, data[name])


def _changed(instance: models.Model, before: Mapping[str, object]) -> list[str]:
    return sorted(name for name, value in before.items() if getattr(instance, name) != value)


def _normalise_school(education: EducationRecord) -> None:
    """A listed school supplies the scale and replaces any typed name and type."""
    if education.school is not None:
        education.gwa_scale = education.school.grading_scale
        education.school_name = ""
        education.school_type = ""


def _clear_other_current(education: EducationRecord) -> None:
    education.profile.education.filter(is_current=True).exclude(pk=education.pk).update(
        is_current=False
    )


@transaction.atomic
def ensure_profile(*, user: User) -> StudentProfile:
    _require_student(user)
    profile, created = StudentProfile.objects.get_or_create(user=user)
    if created:
        audit.record(actor=user, action="profile.created", target=profile)
    return profile


@transaction.atomic
def update_personal(*, user: User, data: Mapping[str, object]) -> StudentProfile:
    profile = ensure_profile(user=user)
    before = _snapshot(profile, PERSONAL_FIELDS)
    _assign(profile, data, PERSONAL_FIELDS)
    changed = _changed(profile, before)
    if not changed:
        return profile
    profile.save(update_fields=[*changed, "updated_at"])
    if user.full_name != profile.full_name:
        user.full_name = profile.full_name
        user.save(update_fields=["full_name"])
    audit.record(actor=user, action="profile.updated", target=profile, data={"fields": changed})
    return profile


@transaction.atomic
def add_family_member(*, user: User, data: Mapping[str, object]) -> FamilyMember:
    profile = ensure_profile(user=user)
    member = FamilyMember(profile=profile)
    _assign(member, data, FAMILY_FIELDS)
    member.save()
    audit.record(
        actor=user, action="family.added", target=member, data={"relation": member.relation}
    )
    return member


@transaction.atomic
def update_family_member(
    *, user: User, member: FamilyMember, data: Mapping[str, object]
) -> FamilyMember:
    _require_student(user)
    _require_owner(user, member.profile)
    before = _snapshot(member, FAMILY_FIELDS)
    _assign(member, data, FAMILY_FIELDS)
    changed = _changed(member, before)
    if changed:
        member.save(update_fields=[*changed, "updated_at"])
        audit.record(
            actor=user,
            action="family.updated",
            target=member,
            data={"relation": member.relation, "fields": changed},
        )
    return member


@transaction.atomic
def remove_family_member(*, user: User, member: FamilyMember) -> None:
    _require_student(user)
    _require_owner(user, member.profile)
    audit.record(
        actor=user, action="family.removed", target=member, data={"relation": member.relation}
    )
    member.delete()


@transaction.atomic
def add_education(*, user: User, data: Mapping[str, object]) -> EducationRecord:
    profile = ensure_profile(user=user)
    education = EducationRecord(profile=profile)
    _assign(education, data, EDUCATION_FIELDS)
    _normalise_school(education)
    if education.is_current:
        _clear_other_current(education)
    education.save()
    audit.record(
        actor=user, action="education.added", target=education, data={"level": education.level}
    )
    return education


@transaction.atomic
def update_education(
    *, user: User, record: EducationRecord, data: Mapping[str, object]
) -> EducationRecord:
    _require_student(user)
    _require_owner(user, record.profile)
    before = _snapshot(record, EDUCATION_FIELDS)
    _assign(record, data, EDUCATION_FIELDS)
    _normalise_school(record)
    changed = _changed(record, before)
    if changed:
        if record.is_current:
            _clear_other_current(record)
        record.save(update_fields=[*changed, "updated_at"])
        audit.record(
            actor=user,
            action="education.updated",
            target=record,
            data={"level": record.level, "fields": changed},
        )
    return record


@transaction.atomic
def remove_education(*, user: User, record: EducationRecord) -> None:
    _require_student(user)
    _require_owner(user, record.profile)
    audit.record(
        actor=user, action="education.removed", target=record, data={"level": record.level}
    )
    record.delete()


@transaction.atomic
def set_photo(*, user: User, file: StoredFile) -> StudentProfile:
    profile = ensure_profile(user=user)
    if (
        file.uploaded_by_id != user.pk
        or file.status != StoredFile.Status.READY
        or file.purpose != StoredFile.Purpose.PHOTO
    ):
        raise PermissionDenied("That file can't be used as a profile photo.")
    profile.photo = file
    profile.save(update_fields=["photo", "updated_at"])
    audit.record(
        actor=user, action="profile.photo_set", target=profile, data={"file": str(file.id)}
    )
    return profile


@transaction.atomic
def remove_photo(*, user: User) -> StudentProfile:
    profile = ensure_profile(user=user)
    if profile.photo_id is None:
        return profile
    profile.photo = None
    profile.save(update_fields=["photo", "updated_at"])
    audit.record(actor=user, action="profile.photo_removed", target=profile)
    return profile


def _require_program_staff(actor: User, program: Program | None) -> None:
    """The office, or staff or head of this program. Nobody else, whatever their role says."""
    if not actor.is_active:
        raise PermissionDenied("Not allowed.")
    if actor.is_super_admin:
        return
    if program is not None and actor.is_program_staff and membership_for(actor, program):
        return
    raise PermissionDenied("Only this program's staff can do that.")


def _clean_email(email: str) -> str:
    cleaned = email.strip().lower()
    try:
        validate_email(cleaned)
    except ValidationError:
        raise ValidationError("Enter a valid email address.") from None
    return cleaned


def _expire_open_invites(profile: StudentProfile, now: datetime) -> None:
    profile.invites.filter(claimed_at__isnull=True, expires_at__gt=now).update(
        expires_at=now, updated_at=now
    )


@transaction.atomic
def create_staff_profile(
    *,
    actor: User,
    program: Program,
    first_name: str,
    middle_name: str,
    last_name: str,
    suffix: str,
    birth_date: date,
    email: str,
) -> tuple[StudentProfile, ProfileInvite]:
    _require_program_staff(actor, program)
    cleaned = _clean_email(email)
    profile = StudentProfile.objects.create(
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        suffix=suffix,
        birth_date=birth_date,
        created_by=actor,
        created_for=program,
    )
    audit.record(actor=actor, action="profile.created_by_staff", target=profile, program=program)
    return profile, issue_invite(actor=actor, profile=profile, email=cleaned)


@transaction.atomic
def issue_invite(
    *, actor: User, profile: StudentProfile, email: str | None = None
) -> ProfileInvite:
    """Send a fresh claim link; every older unclaimed link of this profile stops working."""
    _require_program_staff(actor, profile.created_for)
    locked = StudentProfile.objects.select_for_update().get(pk=profile.pk)
    if locked.user_id is not None:
        raise ValidationError("This profile has already been claimed.")
    if email is None:
        previous = locked.invites.order_by("-pk").first()
        if previous is None:
            raise ValidationError("Enter the student's email address.")
        email = previous.email
    cleaned = _clean_email(email)
    now = timezone.now()
    _expire_open_invites(locked, now)
    token = secrets.token_urlsafe(32)
    invite = ProfileInvite.objects.create(
        profile=locked,
        email=cleaned,
        token_hash=hash_token(token),
        expires_at=now + timedelta(days=ProfileInvite.INVITE_DAYS),
        created_by=actor,
    )
    # No name in the email: the address is unverified, so anyone could have been typed into it.
    enqueue(
        to=cleaned,
        kind="profile_invite",
        context={"claim_url": settings.SITE_URL + reverse("claim:start", args=[token])},
    )
    audit.record(actor=actor, action="invite.sent", target=invite, program=locked.created_for)
    return invite


@transaction.atomic
def claim_profile(*, user: User, token: str, request: HttpRequest | None) -> StudentProfile:
    """Attach the invited profile to this account. Everything is re-checked under row locks."""
    found = find_invite(token)
    if found is None:
        raise ValidationError(INVALID_LINK)
    # Lock order matches issue_invite: account, then profile, then invite. Opposite orders deadlock.
    locked_user = User.objects.select_for_update().get(pk=user.pk)
    StudentProfile.objects.select_for_update().get(pk=found.profile_id)
    invite = (
        ProfileInvite.objects.select_for_update(of=("self",))
        .select_related("profile")
        .get(pk=found.pk)
    )
    message = claim_problem(invite, locked_user)
    if message is not None:
        raise ValidationError(message)
    now = timezone.now()
    profile = invite.profile
    profile.user = locked_user
    profile.save(update_fields=["user", "updated_at"])
    invite.claimed_at = now
    invite.claimed_by = locked_user
    invite.save(update_fields=["claimed_at", "claimed_by", "updated_at"])
    _expire_open_invites(profile, now)
    locked_user.full_name = profile.full_name
    locked_user.save(update_fields=["full_name"])
    user.full_name = locked_user.full_name
    record_consent(user=locked_user, request=request)
    audit.record(
        actor=locked_user,
        action="profile.claimed",
        target=profile,
        program=profile.created_for,
        request=request,
    )
    return profile
