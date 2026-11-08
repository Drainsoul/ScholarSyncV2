import hashlib
from datetime import date, timedelta
from typing import Any

import pytest
from allauth.account.models import EmailAddress
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.accounts.models import ConsentRecord, User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.models import Program, ProgramMembership
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.students.models import ProfileInvite, StudentProfile
from apps.students.selectors import find_invite
from apps.students.services import claim_profile, create_staff_profile, issue_invite
from apps.students.tests.factories import ProfileFactory
from apps.workspace.models import EmailOutbox

EMAIL = "paolo@example.com"


def _create(
    staff: User, program: Program, email: str = "Paolo@Example.com"
) -> tuple[StudentProfile, ProfileInvite]:
    return create_staff_profile(
        actor=staff,
        program=program,
        first_name="Paolo",
        middle_name="",
        last_name="Villanueva",
        suffix="",
        birth_date=date(2007, 5, 1),
        email=email,
    )


def _token_of(row: EmailOutbox) -> str:
    return str(row.context["claim_url"]).rstrip("/").rsplit("/", 1)[-1]


def _latest_token() -> str:
    return _token_of(EmailOutbox.objects.filter(kind="profile_invite").latest("pk"))


def _setup() -> tuple[User, Program, StudentProfile, ProfileInvite, str]:
    membership = MembershipFactory.create()
    staff, program = membership.user, membership.program
    profile, invite = _create(staff, program)
    return staff, program, profile, invite, _latest_token()


def _student(email: str = EMAIL) -> User:
    return UserFactory.create(email=email, verified=True)


def test_create_staff_profile_and_invite(db: Any) -> None:
    staff = MembershipFactory.create().user
    program = staff.memberships.get().program
    profile, invite = _create(staff, program)
    assert profile.user is None and profile.created_for == program and profile.created_by == staff
    assert invite.email == "paolo@example.com"
    row = EmailOutbox.objects.get(kind="profile_invite")
    assert row.to == "paolo@example.com"
    assert set(row.context) == {"claim_url"}
    token = _token_of(row)
    assert invite.token_hash == hashlib.sha256(token.encode()).hexdigest() != token
    event = AuditEvent.objects.get(action="profile.created_by_staff")
    assert event.program == program and event.data == {}
    sent = AuditEvent.objects.get(action="invite.sent")
    assert sent.program == program and sent.data == {}
    assert token not in str(list(AuditEvent.objects.values_list("data", flat=True)))


def test_office_may_create(db: Any) -> None:
    office = UserFactory.create(role=User.Role.SUPER_ADMIN)
    profile, _ = _create(office, ProgramFactory.create())
    assert profile.created_by == office


def test_head_may_create(db: Any) -> None:
    head = MembershipFactory.create(level=ProgramMembership.Level.HEAD)
    profile, _ = _create(head.user, head.program)
    assert profile.pk


def test_other_program_staff_cannot_create(db: Any) -> None:
    staff = MembershipFactory.create().user
    with pytest.raises(PermissionDenied):
        _create(staff, ProgramFactory.create())
    assert not StudentProfile.objects.exists()


def test_student_and_inactive_office_cannot_create(db: Any) -> None:
    program = ProgramFactory.create()
    with pytest.raises(PermissionDenied):
        _create(UserFactory.create(), program)
    with pytest.raises(PermissionDenied):
        _create(UserFactory.create(role=User.Role.SUPER_ADMIN, is_active=False), program)


def test_resend_kills_older_links(db: Any) -> None:
    staff, _, profile, first, _ = _setup()
    second = issue_invite(actor=staff, profile=profile)
    first.refresh_from_db()
    assert not first.is_usable and second.is_usable
    assert EmailOutbox.objects.filter(kind="profile_invite").count() == 2


def test_resend_to_a_new_address(db: Any) -> None:
    staff, _, profile, _, _ = _setup()
    invite = issue_invite(actor=staff, profile=profile, email=" New@Example.com ")
    assert invite.email == "new@example.com"
    assert EmailOutbox.objects.filter(kind="profile_invite").latest("pk").to == "new@example.com"


def test_resend_by_other_program_staff_refused(db: Any) -> None:
    _, _, profile, _, _ = _setup()
    other = MembershipFactory.create().user
    with pytest.raises(PermissionDenied):
        issue_invite(actor=other, profile=profile)


def test_cannot_invite_a_claimed_profile(db: Any) -> None:
    membership = MembershipFactory.create()
    profile = ProfileFactory.create(created_for=membership.program)
    with pytest.raises(ValidationError, match="already been claimed"):
        issue_invite(actor=membership.user, profile=profile, email=EMAIL)


@pytest.mark.parametrize(
    ("case", "message_start"),
    [
        ("expired", "This link has expired"),
        ("claimed", "This link has expired"),
        ("other_address", "This invitation was sent to a different email"),
        ("unverified", "This invitation was sent to a different email"),
        ("has_profile", "Your account already has a profile"),
        ("staff_user", "Only student accounts"),
    ],
)
def test_claim_refusals(db: Any, case: str, message_start: str) -> None:
    _, _, profile, invite, token = _setup()
    user = _student()
    if case == "expired":
        invite.expires_at = timezone.now() - timedelta(seconds=1)
        invite.save()
    elif case == "claimed":
        invite.claimed_at = timezone.now()
        invite.save()
    elif case == "other_address":
        user = _student("someone@example.com")
    elif case == "unverified":
        EmailAddress.objects.filter(user=user).update(verified=False)
    elif case == "has_profile":
        ProfileFactory.create(user=user)
    elif case == "staff_user":
        user.delete()
        user = UserFactory.create(email=EMAIL, role=User.Role.STAFF, verified=True)
    audits = AuditEvent.objects.count()
    with pytest.raises(ValidationError) as caught:
        claim_profile(user=user, token=token, request=None)
    assert caught.value.messages[0].startswith(message_start)
    profile.refresh_from_db()
    assert profile.user is None
    assert not ConsentRecord.objects.filter(user=user).exists()
    assert AuditEvent.objects.count() == audits


def test_claim_when_profile_already_attached(db: Any) -> None:
    _, _, profile, _, token = _setup()
    profile.user = UserFactory.create()
    profile.save()
    with pytest.raises(ValidationError, match="expired or has already been used"):
        claim_profile(user=_student(), token=token, request=None)


def test_claim_unknown_token(db: Any) -> None:
    with pytest.raises(ValidationError, match="expired or has already been used"):
        claim_profile(user=_student(), token="nope", request=None)


def test_claim_attaches_records_consent_and_is_single_use(db: Any) -> None:
    _, program, profile, invite, token = _setup()
    student = _student()
    EmailAddress.objects.filter(user=student).update(email="PAOLO@example.com")
    claimed = claim_profile(user=student, token=token, request=None)
    profile.refresh_from_db()
    invite.refresh_from_db()
    assert claimed.pk == profile.pk and profile.user == student
    assert invite.claimed_by == student and invite.claimed_at and not invite.is_usable
    student.refresh_from_db()
    assert student.full_name == "Paolo Villanueva"
    assert ConsentRecord.objects.filter(user=student).count() == 1
    event = AuditEvent.objects.get(action="profile.claimed")
    assert event.program == program and event.data == {} and event.actor == student
    with pytest.raises(ValidationError):
        claim_profile(user=student, token=token, request=None)
    assert ConsentRecord.objects.filter(user=student).count() == 1


def test_claim_expires_other_invites(db: Any) -> None:
    staff, _, profile, first, _ = _setup()
    issue_invite(actor=staff, profile=profile)
    claim_profile(user=_student(), token=_latest_token(), request=None)
    first.refresh_from_db()
    assert not first.is_usable
    assert not any(i.is_usable for i in ProfileInvite.objects.filter(profile=profile))


def test_token_lookup_ignores_unknown(db: Any) -> None:
    assert find_invite("nope") is None
    assert find_invite("") is None


def test_token_lookup_finds_by_hash(db: Any) -> None:
    _, _, profile, invite, token = _setup()
    found = find_invite(token)
    assert found is not None and found.pk == invite.pk and found.profile.pk == profile.pk
    assert find_invite(invite.token_hash) is None  # the hash itself is not a token
