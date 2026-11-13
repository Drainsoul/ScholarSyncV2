import pytest
from django.db import IntegrityError, transaction

from apps.applications.models import Application
from apps.awards.models import Award, ScholarTerm
from apps.awards.tests.factories import AwardFactory, ScholarTermFactory
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
    assert application.award == award
