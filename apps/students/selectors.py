from django.db.models import Case, IntegerField, QuerySet, Value, When
from django.http import Http404

from apps.accounts.models import User
from apps.students.completion import Completion, completion
from apps.students.models import EducationRecord, FamilyMember, StudentProfile

_RELATION_ORDER = (
    FamilyMember.Relation.FATHER,
    FamilyMember.Relation.MOTHER,
    FamilyMember.Relation.GUARDIAN,
    FamilyMember.Relation.SIBLING,
)


def profile_for(user: User) -> StudentProfile | None:
    return StudentProfile.objects.filter(user=user).first()


def family_for(profile: StudentProfile) -> QuerySet[FamilyMember]:
    rank = Case(
        *[
            When(relation=relation, then=Value(index))
            for index, relation in enumerate(_RELATION_ORDER)
        ],
        default=Value(len(_RELATION_ORDER)),
        output_field=IntegerField(),
    )
    return profile.family.annotate(relation_rank=rank).order_by("relation_rank", "name", "pk")


def education_for(profile: StudentProfile) -> QuerySet[EducationRecord]:
    return profile.education.select_related("school").order_by("-is_current", "-year_from", "pk")


def profile_page(user: User) -> tuple[StudentProfile | None, Completion]:
    """The profile and its completion in at most three queries."""
    profile = profile_for(user)
    if profile is None:
        return None, completion(StudentProfile(), family=[], education=[])
    return profile, completion(
        profile, family=list(family_for(profile)), education=list(education_for(profile))
    )


def own_family_member(user: User, pk: int) -> FamilyMember:
    try:
        return FamilyMember.objects.get(pk=pk, profile__user=user)
    except FamilyMember.DoesNotExist:
        raise Http404("No such family member.") from None


def own_education_record(user: User, pk: int) -> EducationRecord:
    try:
        return EducationRecord.objects.get(pk=pk, profile__user=user)
    except EducationRecord.DoesNotExist:
        raise Http404("No such education record.") from None
