import json
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import Http404

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.files.models import StoredFile
from apps.files.tests.factories import StoredFileFactory
from apps.programs.models import School
from apps.programs.tests.factories import SchoolFactory
from apps.students import selectors, services
from apps.students.models import EducationRecord, FamilyMember, StudentProfile
from apps.students.tests.factories import (
    EducationRecordFactory,
    FamilyMemberFactory,
    FullProfileFactory,
    ProfileFactory,
)

pytestmark = pytest.mark.django_db


def _owner(profile: StudentProfile) -> User:
    assert profile.user is not None
    return profile.user


def _student() -> User:
    return UserFactory.create(verified=True)


def test_ensure_profile_creates_once_and_audits() -> None:
    user = _student()
    first = services.ensure_profile(user=user)
    second = services.ensure_profile(user=user)
    assert first == second
    event = AuditEvent.objects.get(action="profile.created")
    assert event.data == {}
    assert event.target_id == str(first.pk)


def test_update_personal_audits_field_names_only() -> None:
    user = _student()
    services.update_personal(
        user=user, data={"first_name": "Niña", "last_name": "Reyes", "phone": "+639171234567"}
    )
    event = AuditEvent.objects.get(action="profile.updated")
    assert event.data == {"fields": ["first_name", "last_name", "phone"]}
    assert "Niña" not in json.dumps(event.data)
    user.refresh_from_db()
    assert user.full_name == "Niña Reyes"


def test_no_audit_when_nothing_changed() -> None:
    user = _student()
    data = {"first_name": "Ana", "last_name": "Cruz"}
    services.update_personal(user=user, data=data)
    services.update_personal(user=user, data=data)
    assert AuditEvent.objects.filter(action="profile.updated").count() == 1


def test_own_rows_only() -> None:
    mine, theirs = FamilyMemberFactory.create(), FamilyMemberFactory.create()
    assert selectors.own_family_member(_owner(mine.profile), mine.pk) == mine
    with pytest.raises(Http404):
        selectors.own_family_member(_owner(mine.profile), theirs.pk)
    record, other = EducationRecordFactory.create(), EducationRecordFactory.create()
    with pytest.raises(Http404):
        selectors.own_education_record(_owner(record.profile), other.pk)
    with pytest.raises(Http404):
        selectors.own_education_record(_student(), record.pk)


def test_family_add_update_remove_audit() -> None:
    user = _student()
    member = services.add_family_member(
        user=user, data={"relation": "mother", "name": "Rosa Reyes", "occupation": "Nurse"}
    )
    assert AuditEvent.objects.get(action="family.added").data == {"relation": "mother"}
    services.update_family_member(user=user, member=member, data={"occupation": "Teacher"})
    updated = AuditEvent.objects.get(action="family.updated")
    assert updated.data == {"relation": "mother", "fields": ["occupation"]}
    services.update_family_member(user=user, member=member, data={"occupation": "Teacher"})
    assert AuditEvent.objects.filter(action="family.updated").count() == 1
    pk = member.pk
    services.remove_family_member(user=user, member=member)
    assert not FamilyMember.objects.filter(pk=pk).exists()
    removed = AuditEvent.objects.get(action="family.removed")
    assert removed.data == {"relation": "mother"}
    assert removed.target_id == str(pk)


def test_family_service_refuses_someone_elses_row() -> None:
    theirs = FamilyMemberFactory.create()
    with pytest.raises(PermissionDenied):
        services.remove_family_member(user=_student(), member=theirs)
    assert FamilyMember.objects.filter(pk=theirs.pk).exists()


def test_only_one_current_school() -> None:
    user = _student()
    old = services.add_education(
        user=user,
        data={
            "level": "shs",
            "school_name": "Old High",
            "school_type": "public",
            "is_current": True,
        },
    )
    school = SchoolFactory.create(grading_scale=School.Scale.PERCENT)
    new = services.add_education(
        user=user, data={"level": "college", "school": school, "is_current": True}
    )
    old.refresh_from_db()
    assert old.is_current is False
    assert new.is_current is True
    services.update_education(user=user, record=old, data={"is_current": True})
    assert not EducationRecord.objects.get(pk=new.pk).is_current
    assert EducationRecord.objects.filter(profile__user=user, is_current=True).count() == 1


def test_listed_school_sets_scale_and_clears_name() -> None:
    user = _student()
    school = SchoolFactory.create(grading_scale=School.Scale.ONE_TO_FIVE)
    record = services.add_education(
        user=user,
        data={
            "level": "college",
            "school": school,
            "school_name": "Typed",
            "school_type": "private",
            "gwa_scale": "percent",
        },
    )
    assert record.school == school
    assert record.school_name == ""
    assert record.school_type == ""
    assert record.gwa_scale == "one_to_five"
    assert AuditEvent.objects.get(action="education.added").data == {"level": "college"}


def test_education_update_and_remove_audit() -> None:
    user = _student()
    record = services.add_education(
        user=user, data={"level": "jhs", "school_name": "X High", "school_type": "public"}
    )
    services.update_education(user=user, record=record, data={"course": "STEM"})
    assert AuditEvent.objects.get(action="education.updated").data == {
        "level": "jhs",
        "fields": ["course"],
    }
    services.remove_education(user=user, record=record)
    assert AuditEvent.objects.get(action="education.removed").data == {"level": "jhs"}
    assert not EducationRecord.objects.filter(pk=record.pk).exists()


def test_photo_set_and_remove() -> None:
    user = _student()
    file = StoredFileFactory.create(
        uploaded_by=user, purpose="photo", status="ready", sha256="a" * 64, sniffed_type="image/png"
    )
    profile = services.set_photo(user=user, file=file)
    assert profile.photo_id == file.id
    assert AuditEvent.objects.get(action="profile.photo_set").data == {"file": str(file.id)}
    profile = services.remove_photo(user=user)
    assert profile.photo_id is None
    assert AuditEvent.objects.filter(action="profile.photo_removed").count() == 1


def test_profile_page_with_profile() -> None:
    profile = FullProfileFactory.create()
    FamilyMemberFactory.create(profile=profile)
    EducationRecordFactory.create(profile=profile)
    found, comp = selectors.profile_page(_owner(profile))
    assert found == profile
    assert comp.percent > 0


def test_profile_page_without_profile_makes_one_query(
    django_assert_max_num_queries: Any,
) -> None:
    user = _student()
    with django_assert_max_num_queries(1):
        profile, comp = selectors.profile_page(user)
    assert profile is None
    assert comp.percent == 0


def test_profile_page_query_budget(django_assert_max_num_queries: Any) -> None:
    profile = FullProfileFactory.create()
    FamilyMemberFactory.create(profile=profile)
    EducationRecordFactory.create(profile=profile)
    with django_assert_max_num_queries(3):
        selectors.profile_page(_owner(profile))


def test_family_and_education_ordering() -> None:
    profile = ProfileFactory.create()
    sibling = FamilyMemberFactory.create(profile=profile, relation="sibling", name="A")
    guardian = FamilyMemberFactory.create(profile=profile, relation="guardian", name="B")
    mother = FamilyMemberFactory.create(profile=profile, relation="mother", name="Z")
    father = FamilyMemberFactory.create(profile=profile, relation="father", name="M")
    assert list(selectors.family_for(profile)) == [father, mother, guardian, sibling]
    past = EducationRecordFactory.create(profile=profile, is_current=False, year_from=2010)
    recent = EducationRecordFactory.create(profile=profile, is_current=False, year_from=2020)
    current = EducationRecordFactory.create(profile=profile, is_current=True, year_from=2000)
    assert list(selectors.education_for(profile)) == [current, recent, past]


def test_staff_cannot_use_student_services() -> None:
    staff = UserFactory.create(role=User.Role.STAFF)
    with pytest.raises(PermissionDenied):
        services.ensure_profile(user=staff)
    with pytest.raises(PermissionDenied):
        services.update_personal(user=staff, data={"first_name": "X"})
    with pytest.raises(PermissionDenied):
        services.add_family_member(user=staff, data={"relation": "mother", "name": "X"})
    with pytest.raises(PermissionDenied):
        services.add_education(user=staff, data={"level": "jhs", "school_name": "X"})
    assert not StudentProfile.objects.filter(user=staff).exists()


def _photo(user: User, **overrides: object) -> StoredFile:
    fields: dict[str, object] = {
        "uploaded_by": user,
        "purpose": "photo",
        "status": "ready",
        "sha256": "a" * 64,
        "sniffed_type": "image/png",
    }
    return StoredFileFactory.create(**{**fields, **overrides})


@pytest.mark.parametrize(
    "overrides",
    [
        {"uploaded_by": None},  # replaced below with another user
        {"status": "pending", "sha256": "", "sniffed_type": ""},
        {"purpose": "document"},
    ],
    ids=["someone-elses", "not-ready", "not-a-photo"],
)
def test_set_photo_refuses_unusable_files(overrides: dict[str, object]) -> None:
    user = _student()
    if overrides.get("uploaded_by", 1) is None:
        overrides = {"uploaded_by": _student()}
    file = _photo(user, **overrides)
    with pytest.raises(PermissionDenied):
        services.set_photo(user=user, file=file)
    assert not StudentProfile.objects.filter(user=user, photo__isnull=False).exists()
    assert not AuditEvent.objects.filter(action="profile.photo_set").exists()


def test_remove_photo_without_a_photo_does_nothing() -> None:
    user = _student()
    services.ensure_profile(user=user)
    before = StudentProfile.objects.get(user=user).updated_at
    services.remove_photo(user=user)
    assert not AuditEvent.objects.filter(action="profile.photo_removed").exists()
    assert StudentProfile.objects.get(user=user).updated_at == before


def test_education_update_and_remove_refuse_someone_elses_row() -> None:
    theirs = EducationRecordFactory.create()
    with pytest.raises(PermissionDenied):
        services.update_education(user=_student(), record=theirs, data={"course": "X"})
    with pytest.raises(PermissionDenied):
        services.remove_education(user=_student(), record=theirs)
    assert EducationRecord.objects.filter(pk=theirs.pk).exists()


def test_database_allows_one_current_education_per_profile() -> None:
    profile = ProfileFactory.create()
    EducationRecordFactory.create(profile=profile, is_current=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        EducationRecordFactory.create(profile=profile, is_current=True)
    EducationRecordFactory.create(profile=profile, is_current=False)
    EducationRecordFactory.create(profile=ProfileFactory.create(), is_current=True)


def test_current_education_and_effective_school_type() -> None:
    profile = ProfileFactory.create()
    assert selectors.current_education(profile) is None
    EducationRecordFactory.create(profile=profile, is_current=False)
    listed = EducationRecordFactory.create(
        profile=profile, is_current=True, school=SchoolFactory.create(type=School.Type.SUC)
    )
    found = selectors.current_education(profile)
    assert found == listed
    assert selectors.effective_school_type(listed) == "suc"
    typed = EducationRecordFactory.build(
        profile=profile, school=None, school_name="Elsewhere", school_type="private"
    )
    assert selectors.effective_school_type(typed) == "private"
    unknown = EducationRecordFactory.build(profile=profile, school=None, school_type="")
    assert selectors.effective_school_type(unknown) == ""


def test_undated_education_sorts_after_dated() -> None:
    profile = ProfileFactory.create()
    undated = EducationRecordFactory.create(profile=profile, is_current=False, year_from=None)
    dated = EducationRecordFactory.create(profile=profile, is_current=False, year_from=2015)
    assert list(selectors.education_for(profile)) == [dated, undated]
