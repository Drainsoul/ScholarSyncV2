from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.models import Award, ScholarTerm
from apps.awards.services import award_from_application
from apps.awards.tests.factories import AwardFactory
from apps.core.models import AuditEvent
from apps.programs.models import School
from apps.programs.tests.factories import BenefitTierFactory, MembershipFactory, SchoolFactory

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
