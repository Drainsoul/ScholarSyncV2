"""Student profile writes. Every service is audited; audit data holds field names, never values."""

from collections.abc import Iterable, Mapping

from django.core.exceptions import PermissionDenied
from django.db import models, transaction

from apps.accounts.models import User
from apps.core import audit
from apps.files.models import StoredFile
from apps.students.models import EducationRecord, FamilyMember, StudentProfile

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
    education.save()
    if education.is_current:
        _clear_other_current(education)
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
        record.save(update_fields=[*changed, "updated_at"])
        if record.is_current:
            _clear_other_current(record)
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
    profile.photo = file
    profile.save(update_fields=["photo", "updated_at"])
    audit.record(
        actor=user, action="profile.photo_set", target=profile, data={"file": str(file.id)}
    )
    return profile


@transaction.atomic
def remove_photo(*, user: User) -> StudentProfile:
    profile = ensure_profile(user=user)
    profile.photo = None
    profile.save(update_fields=["photo", "updated_at"])
    audit.record(actor=user, action="profile.photo_removed", target=profile)
    return profile
