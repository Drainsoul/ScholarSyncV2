from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404

from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.models import Award, ScholarTerm
from apps.awards.services import (
    NEED_END_REASON,
    NEED_HOLD_REASON,
    STATUS_REASON_TOO_LONG,
    already_holds,
    award_from_application,
    change_status,
    update_award,
)
from apps.awards.tests.factories import AwardFactory
from apps.awards.tests.scholars import make_scholar
from apps.core.models import AuditEvent
from apps.core.transitions import InvalidTransition
from apps.programs.models import School
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
    SchoolFactory,
)

pytestmark = pytest.mark.django_db

S = Application.Status


def approved_application(**kwargs: object) -> Application:
    kwargs.setdefault("status", S.APPROVED)
    return ApplicationFactory.create(
        year_level=2,
        course="BS Accountancy",
        gwa=Decimal("91.50"),
        gwa_scale=School.Scale.PERCENT,
        units=21,
        **kwargs,
    )


def test_award_from_application_creates_award_term_and_audit() -> None:
    application = approved_application(match_snapshot={"merit_likely": True})
    tier = BenefitTierFactory.create(program=application.program, effective_from=application.term)
    actor = MembershipFactory.create(program=application.program).user
    award = award_from_application(actor=actor, application=application, tier=tier)
    assert (award.profile, award.program, award.tier) == (
        application.profile,
        application.program,
        tier,
    )
    assert award.status == Award.Status.ACTIVE
    assert award.source == Award.Source.APPLIED
    assert award.source_application == application
    assert award.started_term == application.term
    assert award.ended_term is None
    term = ScholarTerm.objects.get(award=award)
    assert term.term == application.term
    assert (term.school, term.school_name, term.school_type) == (None, "Factory College", "")
    assert (term.year_level, term.course, term.gwa, term.gwa_scale, term.units) == (
        2,
        "BS Accountancy",
        Decimal("91.50"),
        School.Scale.PERCENT,
        21,
    )
    assert term.merit is True
    assert term.merit_confirmed_by is None
    assert term.compliance == ScholarTerm.Compliance.COMPLETE
    event = AuditEvent.objects.get(action="award.created")
    assert event.actor == actor
    assert event.program == application.program
    assert event.target_type == "awards.award"
    assert event.target_id == str(award.pk)
    assert event.data == {"source": "applied", "application": application.pk, "tier": tier.code}


def test_award_from_application_copies_a_listed_school() -> None:
    school = SchoolFactory.create()
    application = approved_application(school=school)
    tier = BenefitTierFactory.create(program=application.program, effective_from=application.term)
    award = award_from_application(
        actor=MembershipFactory.create(program=application.program).user,
        application=application,
        tier=tier,
    )
    term = award.terms.get()
    assert (term.school, term.school_name, term.school_type) == (school, "", "")


def test_award_from_application_turns_integrity_error_into_sentence() -> None:
    application = approved_application()
    program = application.program
    # An active award for the same profile and program, created behind the service's back.
    AwardFactory.create(
        source_application=ApplicationFactory.create(
            profile=application.profile, program=program, status=S.APPROVED
        )
    )
    tier = BenefitTierFactory.create(program=program, effective_from=application.term)
    with pytest.raises(ValidationError) as exc:
        award_from_application(
            actor=MembershipFactory.create(program=program).user,
            application=application,
            tier=tier,
        )
    assert exc.value.messages == [f"This student already holds an active {program.name} award."]
    # The savepoint rolled back only the failed insert: the outer transaction still works.
    assert Award.objects.count() == 1
    assert not ScholarTerm.objects.exists()
    assert not AuditEvent.objects.filter(action="award.created").exists()


def test_award_from_application_reraises_other_integrity_errors() -> None:
    application = approved_application()
    program = application.program
    AwardFactory.create(source_application=application, status=Award.Status.INACTIVE)
    tier = BenefitTierFactory.create(program=program, effective_from=application.term)
    with pytest.raises(IntegrityError), transaction.atomic():
        award_from_application(
            actor=MembershipFactory.create(program=program).user,
            application=application,
            tier=tier,
        )


@pytest.mark.parametrize(
    ("snapshot", "merit"),
    [
        ({"merit_likely": True}, True),
        ({"merit_likely": False}, False),
        ({"merit_likely": None}, False),
        ({}, False),
    ],
)
def test_merit_follows_the_snapshot(snapshot: dict[str, object], merit: bool) -> None:
    application = approved_application(match_snapshot=snapshot)
    tier = BenefitTierFactory.create(program=application.program, effective_from=application.term)
    award = award_from_application(
        actor=MembershipFactory.create(program=application.program).user,
        application=application,
        tier=tier,
    )
    assert award.terms.get().merit is merit


def test_first_term_records_approval_tier() -> None:
    application = approved_application()
    tier = BenefitTierFactory.create(program=application.program, effective_from=application.term)
    actor = MembershipFactory.create(program=application.program).user
    award = award_from_application(actor=actor, application=application, tier=tier)
    assert ScholarTerm.objects.get(award=award).tier == tier


# --- Status changes and edits ---


class Scholars:
    def __init__(self) -> None:
        self.previous = AcademicTermFactory.create(school_year_start=2025, term=2)
        self.current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
        self.program = ProgramFactory.create()
        self.tier = BenefitTierFactory.create(
            program=self.program, effective_from=self.previous, code="standard"
        )
        self.actor = MembershipFactory.create(program=self.program).user

    def award(self, **fields: Any) -> Award:
        return make_scholar(self.program, self.tier, [self.previous], **fields)

    def change(self, award: Award, to: str, reason: str = "") -> Award:
        return change_status(
            actor=self.actor, program=self.program, award=award, to=to, reason=reason
        )


@pytest.fixture
def scholars() -> Scholars:
    return Scholars()


def status_events() -> list[AuditEvent]:
    return list(AuditEvent.objects.filter(action="award.status_changed").order_by("pk"))


@pytest.mark.parametrize(
    ("start", "to", "reason"),
    [
        ("active", "suspended", "Missing enrolment."),
        ("active", "inactive", "Transferred."),
        ("active", "graduated", ""),
        ("suspended", "active", ""),
        ("suspended", "inactive", "No reply."),
        ("suspended", "graduated", ""),
        ("inactive", "active", ""),
    ],
)
def test_status_transitions_allowed(scholars: Scholars, start: str, to: str, reason: str) -> None:
    award = scholars.award(status=start)
    changed = scholars.change(award, to, reason)
    assert changed.status == to
    [event] = status_events()
    assert event.data == {"from": start, "to": to}


@pytest.mark.parametrize(
    ("start", "to"), [("graduated", "active"), ("inactive", "suspended"), ("active", "active")]
)
def test_status_transitions_refused(scholars: Scholars, start: str, to: str) -> None:
    award = scholars.award(status=start)
    with pytest.raises(InvalidTransition):
        scholars.change(award, to, "Because.")
    assert status_events() == []


@pytest.mark.parametrize(
    ("to", "message"), [("suspended", NEED_HOLD_REASON), ("inactive", NEED_END_REASON)]
)
def test_hold_and_end_need_reason(scholars: Scholars, to: str, message: str) -> None:
    award = scholars.award()
    with pytest.raises(ValidationError) as caught:
        scholars.change(award, to, "   ")
    assert caught.value.messages == [message]
    award.refresh_from_db()
    assert award.status == Award.Status.ACTIVE


def test_reason_too_long(scholars: Scholars) -> None:
    award = scholars.award()
    with pytest.raises(ValidationError) as caught:
        scholars.change(award, "suspended", "x" * 1001)
    assert caught.value.messages == [STATUS_REASON_TOO_LONG]


def test_reason_stored_not_in_audit(scholars: Scholars) -> None:
    award = scholars.change(scholars.award(), "suspended", "Secret family matter.")
    assert award.status_reason == "Secret family matter."
    assert "Secret" not in str(status_events()[0].data)


def test_end_and_graduate_set_ended_term(scholars: Scholars) -> None:
    ended = scholars.change(scholars.award(), "inactive", "Moved away.")
    graduated = scholars.change(scholars.award(), "graduated")
    assert ended.ended_term == scholars.current
    assert graduated.ended_term == scholars.current


def test_reinstate_clears_ended_term_and_reason(scholars: Scholars) -> None:
    award = scholars.change(scholars.award(), "inactive", "Moved away.")
    award = scholars.change(award, "active")
    assert award.ended_term is None
    assert award.status_reason == ""


def test_reinstate_conflict_already_holds(scholars: Scholars) -> None:
    held = scholars.award(status=Award.Status.SUSPENDED)
    make_scholar(scholars.program, scholars.tier, [scholars.previous], profile=held.profile)
    with pytest.raises(ValidationError) as caught:
        scholars.change(held, "active")
    assert caught.value.messages == [already_holds(scholars.program)]
    held.refresh_from_db()
    assert held.status == Award.Status.SUSPENDED
    assert status_events() == []


def test_update_award_tier_must_be_in_force(scholars: Scholars) -> None:
    award = scholars.award()
    elsewhere = BenefitTierFactory.create(effective_from=scholars.previous)
    with pytest.raises(ValidationError) as caught:
        update_award(
            actor=scholars.actor,
            program=scholars.program,
            award=award,
            student_number="",
            notes="",
            tier=elsewhere,
        )
    assert caught.value.messages == ["Choose one of this program's allowance tiers."]


def test_update_award_audit_lists_fields_only(scholars: Scholars) -> None:
    award = scholars.award()
    honors = BenefitTierFactory.create(
        program=scholars.program, effective_from=scholars.previous, code="honors"
    )
    updated = update_award(
        actor=scholars.actor,
        program=scholars.program,
        award=award,
        student_number=" 2026-0001 ",
        notes="Prefers email.",
        tier=honors,
    )
    assert (updated.student_number, updated.notes, updated.tier) == (
        "2026-0001",
        "Prefers email.",
        honors,
    )
    event = AuditEvent.objects.get(action="award.updated")
    assert event.data == {"fields": ["student_number", "notes", "tier"], "tier": "honors"}


def test_update_award_without_changes_audits_nothing(scholars: Scholars) -> None:
    award = scholars.award()
    update_award(
        actor=scholars.actor,
        program=scholars.program,
        award=award,
        student_number="",
        notes="",
        tier=award.tier,
    )
    assert not AuditEvent.objects.filter(action="award.updated").exists()


def test_writes_404_for_foreign_ids(scholars: Scholars) -> None:
    foreign = make_scholar(
        ProgramFactory.create(),
        BenefitTierFactory.create(effective_from=scholars.previous),
        [scholars.previous],
    )
    with pytest.raises(Http404):
        scholars.change(foreign, "suspended", "x")
    with pytest.raises(Http404):
        update_award(
            actor=scholars.actor,
            program=scholars.program,
            award=foreign,
            student_number="1",
            notes="",
            tier=scholars.tier,
        )
    assert not AuditEvent.objects.exists()


def test_status_change_needs_program_staff(scholars: Scholars) -> None:
    outsider = MembershipFactory.create(program=ProgramFactory.create()).user
    with pytest.raises(PermissionDenied):
        change_status(
            actor=outsider,
            program=scholars.program,
            award=scholars.award(),
            to="suspended",
            reason="x",
        )
