import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from apps.applications.models import Application
from apps.awards.models import Award, ScholarTerm
from apps.awards.tests.factories import AwardFactory, RenewalFactory, ScholarTermFactory
from apps.core.transitions import InvalidTransition, assert_transition
from apps.programs.tests.factories import ProgramFactory, SchoolFactory

pytestmark = pytest.mark.django_db


def manual_award(first: Award, **overrides: object) -> Award:
    values: dict[str, object] = {
        "profile": first.profile,
        "program": first.program,
        "tier": first.tier,
        "started_term": first.started_term,
        "source": Award.Source.MANUAL,
        "source_application": None,
    }
    values.update(overrides)
    return AwardFactory.create(**values)


def test_one_active_award_per_profile_and_program() -> None:
    first = AwardFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        manual_award(first)
    Award.objects.filter(pk=first.pk).update(status=Award.Status.INACTIVE)
    manual_award(first)
    AwardFactory.create(
        profile=first.profile,
        program=ProgramFactory.create(),
        started_term=first.started_term,
        source=Award.Source.MANUAL,
        source_application=None,
    )
    assert Award.objects.count() == 3


def test_applied_award_needs_its_application() -> None:
    award = AwardFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        Award.objects.filter(pk=award.pk).update(source_application=None)
    Award.objects.filter(pk=award.pk).update(source="manual", source_application=None)


def test_an_application_backs_one_award() -> None:
    award = AwardFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        AwardFactory.create(
            source_application=award.source_application,
            profile=award.profile,
            program=award.program,
            status=Award.Status.INACTIVE,
        )


def test_one_scholar_term_per_award_and_term() -> None:
    scholar_term = ScholarTermFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        ScholarTermFactory.create(award=scholar_term.award, term=scholar_term.term)


def test_scholar_term_school_and_school_name_not_both() -> None:
    school = SchoolFactory.create()
    ScholarTermFactory.create(school=school)
    ScholarTermFactory.create(school_name="Typed College")
    with pytest.raises(IntegrityError), transaction.atomic():
        ScholarTermFactory.create(school=school, school_name="Typed College")


def test_status_source_and_compliance_check_constraints() -> None:
    award = AwardFactory.create()
    scholar_term = ScholarTermFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        Award.objects.filter(pk=award.pk).update(status="bogus")
    with pytest.raises(IntegrityError), transaction.atomic():
        Award.objects.filter(pk=award.pk).update(source="bogus")
    with pytest.raises(IntegrityError), transaction.atomic():
        ScholarTerm.objects.filter(pk=scholar_term.pk).update(compliance="bogus")


def test_factory_builds_a_consistent_approved_application() -> None:
    award = AwardFactory.create()
    application = award.source_application
    assert application is not None
    assert application.status == Application.Status.APPROVED
    assert (application.profile, application.program) == (award.profile, award.program)
    assert award.tier.program == award.program
    assert application.source_award == award


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("active", "suspended"),
        ("active", "inactive"),
        ("active", "graduated"),
        ("suspended", "active"),
        ("suspended", "inactive"),
        ("suspended", "graduated"),
        ("inactive", "active"),
    ],
)
def test_award_transitions_allowed(start: str, end: str) -> None:
    award = Award(status=start)
    assert_transition(award, end)


@pytest.mark.parametrize(
    ("start", "end"),
    [("graduated", "active"), ("inactive", "suspended"), ("inactive", "graduated")],
)
def test_award_transitions_refused(start: str, end: str) -> None:
    with pytest.raises(InvalidTransition):
        assert_transition(Award(status=start), end)


def test_held_statuses() -> None:
    assert Award.HELD_STATUSES == frozenset({"active", "suspended"})


def test_status_reason_defaults_blank() -> None:
    assert AwardFactory.create().status_reason == ""


def test_renewal_factory_builds_a_consistent_renewal() -> None:
    renewal = RenewalFactory.create()
    assert renewal.kind == Application.Kind.RENEWAL
    assert renewal.award is not None
    assert (renewal.profile, renewal.program) == (renewal.award.profile, renewal.award.program)


@pytest.mark.django_db(transaction=True)
def test_backfill_sets_term_tier() -> None:
    before = [("awards", "0001_initial")]
    after = [("awards", "0002_status_reason_term_tier")]
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        old = executor.loader.project_state(before).apps
        profile = old.get_model("students", "StudentProfile").objects.create()
        program = old.get_model("programs", "Program").objects.create(slug="bf", name="Backfill")
        term = old.get_model("programs", "AcademicTerm").objects.create(
            school_year_start=2026, term=1, starts_on="2026-08-01", ends_on="2026-12-31"
        )
        tier = old.get_model("programs", "BenefitTier").objects.create(
            program=program, code="standard", name="Standard", base_amount=5000, effective_from=term
        )
        award = old.get_model("awards", "Award").objects.create(
            profile=profile, program=program, tier=tier, source="manual", started_term=term
        )
        row = old.get_model("awards", "ScholarTerm").objects.create(award=award, term=term)

        executor = MigrationExecutor(connection)
        executor.migrate(after)
        new_term = executor.loader.project_state(after).apps.get_model("awards", "ScholarTerm")
        assert new_term.objects.get(pk=row.pk).tier_id == tier.pk
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
