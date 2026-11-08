"""Profile completion: a pure function over a profile and its prefetched rows.

13 items count: 10 personal fields, a parent or guardian, a current school and a photo.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from apps.students.models import EducationRecord, FamilyMember, StudentProfile

TOTAL_ITEMS = 13
_PARENT_RELATIONS = {
    FamilyMember.Relation.FATHER,
    FamilyMember.Relation.MOTHER,
    FamilyMember.Relation.GUARDIAN,
}


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    url_name: str
    missing: tuple[str, ...]

    @property
    def done(self) -> bool:
        return not self.missing


@dataclass(frozen=True)
class Completion:
    percent: int
    sections: tuple[Section, ...]


def _personal_missing(profile: StudentProfile) -> tuple[str, ...]:
    checks = (
        ("first name", bool(profile.first_name)),
        ("last name", bool(profile.last_name)),
        ("birth date", profile.birth_date is not None),
        ("sex", bool(profile.sex)),
        ("phone", bool(profile.phone)),
        ("address", bool(profile.address_line)),
        ("barangay", bool(profile.barangay)),
        ("residing since", profile.residing_since is not None),
        ("registered voter", profile.is_registered_voter is not None),
        ("household income", profile.monthly_household_income is not None),
    )
    return tuple(label for label, present in checks if not present)


def completion(
    profile: StudentProfile,
    *,
    family: Sequence[FamilyMember],
    education: Sequence[EducationRecord],
) -> Completion:
    has_parent = any(member.relation in _PARENT_RELATIONS for member in family)
    has_current_school = any(record.is_current for record in education)
    sections = (
        Section(
            "personal",
            "Personal details",
            "students:profile-personal",
            _personal_missing(profile),
        ),
        Section(
            "family",
            "Family",
            "students:profile-family",
            () if has_parent else ("a parent or guardian",),
        ),
        Section(
            "education",
            "Education",
            "students:profile-education",
            () if has_current_school else ("your current school",),
        ),
        Section(
            "photo",
            "Photo",
            "students:profile-photo",
            () if profile.photo_id is not None else ("a photo",),
        ),
    )
    missing_count = sum(len(section.missing) for section in sections)
    return Completion(percent=(TOTAL_ITEMS - missing_count) * 100 // TOTAL_ITEMS, sections=sections)
