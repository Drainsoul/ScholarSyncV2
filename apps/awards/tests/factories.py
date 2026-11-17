import factory

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application
from apps.applications.tests.factories import ApplicationFactory
from apps.awards.models import Award, ScholarImport, ScholarTerm
from apps.files.models import StoredFile
from apps.files.policy import CSV
from apps.files.tests.factories import StoredFileFactory
from apps.programs.tests.factories import AcademicTermFactory, BenefitTierFactory, ProgramFactory


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


class ScholarImportFactory(factory.django.DjangoModelFactory[ScholarImport]):
    class Meta:
        model = ScholarImport

    program = factory.declarations.SubFactory(ProgramFactory)
    imported_by = factory.declarations.SubFactory(UserFactory, verified=True)
    file = factory.declarations.SubFactory(
        StoredFileFactory,
        purpose=StoredFile.Purpose.IMPORT,
        status=StoredFile.Status.READY,
        declared_type=CSV,
        sniffed_type=CSV,
        sha256="0" * 64,
        uploaded_by=factory.declarations.SelfAttribute("..imported_by"),
    )
    row_count = 1
