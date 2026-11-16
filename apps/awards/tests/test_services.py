from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404

from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.models import Award, ScholarTerm
from apps.awards.selectors import next_year_level
from apps.awards.services import (
    FUTURE_TERM,
    GRADUATED_NO_RECORD,
    NEED_END_REASON,
    NEED_HOLD_REASON,
    STATUS_REASON_TOO_LONG,
    TERM_EXISTS,
    TermData,
    add_term,
    already_holds,
    award_from_application,
    change_status,
    confirm_merit,
    edit_term,
    update_award,
)
from apps.awards.tests.factories import AwardFactory
from apps.awards.tests.scholars import make_scholar
from apps.core.models import AuditEvent
from apps.core.transitions import InvalidTransition
from apps.programs.models import AcademicTerm, Program, School
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


# --- Term records and merit ---


def term_data(term: AcademicTerm, **fields: Any) -> TermData:
    values: dict[str, Any] = {
        "term": term,
        "school": None,
        "school_name": "Walk-in College",
        "school_type": "private",
        "gwa_scale": "percent",
        "course": "BSED",
        "year_level": 2,
        "gwa": Decimal("85.00"),
        "units": 18,
        "compliance_checked": False,
    }
    values.update(fields)
    return TermData(**values)


def add(scholars: Scholars, award: Award, data: TermData) -> ScholarTerm:
    return add_term(actor=scholars.actor, program=scholars.program, award=award, data=data)


def test_add_term_for_past_term_with_compliance(scholars: Scholars) -> None:
    older = AcademicTermFactory.create(school_year_start=2025, term=1)
    award = scholars.award()
    record = add(scholars, award, term_data(older, compliance_checked=True))
    assert (record.term, record.school_name, record.gwa, record.units) == (
        older,
        "Walk-in College",
        Decimal("85.00"),
        18,
    )
    assert record.compliance == ScholarTerm.Compliance.COMPLETE
    assert record.merit_confirmed_by is None
    event = AuditEvent.objects.get(action="scholar_term.created")
    assert event.data == {
        "award": award.pk,
        "term": older.pk,
        "source": "staff",
        "tier": "standard",
    }


def test_add_term_for_current_term_incomplete(scholars: Scholars) -> None:
    record = add(scholars, scholars.award(), term_data(scholars.current))
    assert record.compliance == ScholarTerm.Compliance.INCOMPLETE


def test_add_term_future_refused(scholars: Scholars) -> None:
    future = AcademicTermFactory.create(school_year_start=2026, term=2)
    with pytest.raises(ValidationError) as caught:
        add(scholars, scholars.award(), term_data(future))
    assert caught.value.messages == [FUTURE_TERM]


def test_add_term_duplicate_refused(scholars: Scholars) -> None:
    award = scholars.award()
    with pytest.raises(ValidationError) as caught:
        add(scholars, award, term_data(scholars.previous))
    assert caught.value.messages == [TERM_EXISTS.format(term=scholars.previous)]


def test_add_term_graduated_refused(scholars: Scholars) -> None:
    award = scholars.award(status=Award.Status.GRADUATED)
    with pytest.raises(ValidationError) as caught:
        add(scholars, award, term_data(scholars.current))
    assert caught.value.messages == [GRADUATED_NO_RECORD]


def test_add_term_allowed_while_suspended(scholars: Scholars) -> None:
    award = scholars.award(status=Award.Status.SUSPENDED)
    assert add(scholars, award, term_data(scholars.current)).award == award


def test_add_term_tier_by_code(scholars: Scholars) -> None:
    repriced = BenefitTierFactory.create(
        program=scholars.program, effective_from=scholars.current, code="standard"
    )
    record = add(scholars, scholars.award(), term_data(scholars.current))
    assert record.tier == repriced


def test_add_term_listed_school_copies_type_and_scale(scholars: Scholars) -> None:
    school = SchoolFactory.create(type=School.Type.LCU, grading_scale=School.Scale.ONE_TO_FIVE)
    record = add(
        scholars,
        scholars.award(),
        term_data(scholars.current, school=school, school_name="", gwa=Decimal("1.75")),
    )
    assert (record.school, record.school_name, record.school_type, record.gwa_scale) == (
        school,
        "",
        "lcu",
        "one_to_five",
    )


def test_add_term_proposes_merit(scholars: Scholars) -> None:
    Program.objects.filter(pk=scholars.program.pk).update(merit_min_gwa_percent=Decimal("90"))
    scholars.program.refresh_from_db()
    high = add(scholars, scholars.award(), term_data(scholars.current, gwa=Decimal("95")))
    low = add(scholars, scholars.award(), term_data(scholars.current, gwa=Decimal("85")))
    assert (high.merit, low.merit) == (True, False)


def test_edit_term_gwa_change_reproposes_merit(scholars: Scholars) -> None:
    Program.objects.filter(pk=scholars.program.pk).update(merit_min_gwa_percent=Decimal("90"))
    scholars.program.refresh_from_db()
    award = scholars.award()
    record = add(scholars, award, term_data(scholars.current, gwa=Decimal("85")))
    confirm_merit(
        actor=scholars.actor,
        program=scholars.program,
        award=award,
        scholar_term_id=record.pk,
        merit=False,
    )
    edited = edit_term(
        actor=scholars.actor,
        program=scholars.program,
        award=award,
        scholar_term_id=record.pk,
        data=term_data(scholars.previous, gwa=Decimal("93")),
    )
    assert edited.term == scholars.current  # the term never changes
    assert (edited.gwa, edited.merit, edited.merit_confirmed_by) == (Decimal("93.00"), True, None)
    event = AuditEvent.objects.get(action="scholar_term.updated")
    assert event.data == {"fields": ["gwa"]}


def test_confirm_and_deny_merit(scholars: Scholars) -> None:
    award = scholars.award()
    record = award.terms.get()
    confirmed = confirm_merit(
        actor=scholars.actor,
        program=scholars.program,
        award=award,
        scholar_term_id=record.pk,
        merit=True,
    )
    assert (confirmed.merit, confirmed.merit_confirmed_by) == (True, scholars.actor)
    denied = confirm_merit(
        actor=scholars.actor,
        program=scholars.program,
        award=award,
        scholar_term_id=record.pk,
        merit=False,
    )
    assert (denied.merit, denied.merit_confirmed_by) == (False, scholars.actor)
    events = AuditEvent.objects.filter(action="scholar_term.merit_confirmed").order_by("pk")
    assert [event.data for event in events] == [{"merit": True}, {"merit": False}]


def test_term_of_other_award_404(scholars: Scholars) -> None:
    award = scholars.award()
    other = scholars.award()
    with pytest.raises(Http404):
        confirm_merit(
            actor=scholars.actor,
            program=scholars.program,
            award=award,
            scholar_term_id=other.terms.get().pk,
            merit=True,
        )


def test_term_writes_404_for_foreign_ids(scholars: Scholars) -> None:
    foreign = make_scholar(
        ProgramFactory.create(),
        BenefitTierFactory.create(effective_from=scholars.previous),
        [scholars.previous],
    )
    with pytest.raises(Http404):
        add(scholars, foreign, term_data(scholars.current))
    with pytest.raises(Http404):
        edit_term(
            actor=scholars.actor,
            program=scholars.program,
            award=foreign,
            scholar_term_id=foreign.terms.get().pk,
            data=term_data(scholars.current),
        )
    assert not AuditEvent.objects.exists()


def test_academic_values_not_in_audit(scholars: Scholars) -> None:
    add(scholars, scholars.award(), term_data(scholars.current, gwa=Decimal("87.25")))
    for event in AuditEvent.objects.all():
        assert "87.25" not in str(event.data)
        assert "Walk-in College" not in str(event.data)


def test_next_year_level_new_school_year_and_same_year(scholars: Scholars) -> None:
    award = scholars.award()  # one record in 2025 term 2, year 2
    assert next_year_level(award, scholars.current) == 3
    same_year = AcademicTermFactory.create(school_year_start=2025, term=3)
    assert next_year_level(award, same_year) == 2
    bare = make_scholar(scholars.program, scholars.tier, [scholars.previous])
    bare.terms.all().delete()
    assert next_year_level(bare, scholars.current) is None
