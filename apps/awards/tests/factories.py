import factory

from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.models import Award, ScholarTerm
from apps.programs.tests.factories import AcademicTermFactory, BenefitTierFactory


class AwardFactory(factory.django.DjangoModelFactory[Award]):
    class Meta:
        model = Award

    source_application = factory.declarations.SubFactory(
        ApplicationFactory, status=Application.Status.APPROVED
    )
    profile = factory.declarations.SelfAttribute("source_application.profile")
    program = factory.declarations.SelfAttribute("source_application.program")
    tier = factory.declarations.SubFactory(
        BenefitTierFactory, program=factory.declarations.SelfAttribute("..program")
    )
    started_term = factory.declarations.SelfAttribute("source_application.term")
    status = Award.Status.ACTIVE
    source = Award.Source.APPLIED


class ScholarTermFactory(factory.django.DjangoModelFactory[ScholarTerm]):
    class Meta:
        model = ScholarTerm

    award = factory.declarations.SubFactory(AwardFactory)
    term = factory.declarations.SubFactory(AcademicTermFactory)


class RenewalFactory(ApplicationFactory):
    """A renewal of an award: same profile and program; the term defaults to a new one."""

    kind = Application.Kind.RENEWAL
    award = factory.declarations.SubFactory(AwardFactory)
    profile = factory.declarations.SelfAttribute("award.profile")  # type: ignore[assignment]
    program = factory.declarations.SelfAttribute("award.program")  # type: ignore[assignment]
