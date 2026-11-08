import hashlib

from allauth.account.models import EmailAddress
from django.db.models import Case, F, IntegerField, OuterRef, QuerySet, Subquery, Value, When
from django.http import Http404

from apps.accounts.models import User
from apps.programs.models import Program
from apps.students.completion import Completion, completion
from apps.students.models import EducationRecord, FamilyMember, ProfileInvite, StudentProfile

INVALID_LINK = (
    "This link has expired or has already been used. Ask the scholarship staff to send a new one."
)

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
    return profile.education.select_related("school").order_by(
        "-is_current", F("year_from").desc(nulls_last=True), "pk"
    )


def current_education(profile: StudentProfile) -> EducationRecord | None:
    return profile.education.select_related("school").filter(is_current=True).first()


def effective_school_type(record: EducationRecord) -> str:
    """The listed school's type, else the type the student typed ("" if unknown)."""
    return record.school.type if record.school is not None else record.school_type


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


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def find_invite(token: str) -> ProfileInvite | None:
    """The invite for this emailed token. Lookup is by hash; the token is never stored."""
    return (
        ProfileInvite.objects.select_related("profile").filter(token_hash=hash_token(token)).first()
    )


def mask_email(email: str) -> str:
    """The address with most of the local part hidden: p•••@example.com."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}•••@{domain}"


def claim_problem(invite: ProfileInvite, user: User) -> str | None:
    """Why this user cannot claim this invite now, as a sentence for them, or None."""
    if not invite.is_usable:
        return INVALID_LINK
    if not user.is_student:
        return "Only student accounts can claim a profile."
    verified = EmailAddress.objects.filter(user=user, verified=True, email__iexact=invite.email)
    if not verified.exists():
        return (
            "This invitation was sent to a different email address. "
            "Sign in with that address to claim the profile."
        )
    if profile_for(user) is not None:
        return "Your account already has a profile. Contact the scholarship office to combine them."
    return None


def unclaimed_profiles_for(program: Program) -> QuerySet[StudentProfile]:
    """Profiles staff created for this program that no student has claimed, newest first.

    Each row carries its latest invite's email, expiry and claim time (one query in all).
    """
    latest = ProfileInvite.objects.filter(profile=OuterRef("pk")).order_by("-pk")
    return (
        StudentProfile.objects.filter(created_for=program, user__isnull=True)
        .annotate(
            invite_email=Subquery(latest.values("email")[:1]),
            invite_expires_at=Subquery(latest.values("expires_at")[:1]),
            invite_claimed_at=Subquery(latest.values("claimed_at")[:1]),
        )
        .order_by("-created_at", "-pk")
    )
