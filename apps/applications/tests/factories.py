import factory

from apps.applications.models import Application, Document, DocumentFile
from apps.files.models import StoredFile
from apps.files.tests.factories import StoredFileFactory
from apps.programs.tests.factories import (
    AcademicTermFactory,
    MembershipFactory,
    ProgramFactory,
    RequiredDocumentFactory,
)
from apps.students.tests.factories import ProfileFactory


class ApplicationFactory(factory.django.DjangoModelFactory[Application]):
    class Meta:
        model = Application

    profile = factory.declarations.SubFactory(ProfileFactory)
    program = factory.declarations.SubFactory(ProgramFactory)
    term = factory.declarations.SubFactory(AcademicTermFactory)
    kind = Application.Kind.NEW
    status = Application.Status.DRAFT
    school = None
    # Rows past draft hold a frozen school (applications_submitted_has_school): a typed name here.
    school_name = factory.declarations.LazyAttribute(
        lambda o: (
            ""
            if o.school is not None
            or o.status == Application.Status.DRAFT
            or (o.status == Application.Status.WITHDRAWN and o.submitted_at is None)
            else "Factory College"
        )
    )
    submitted_at = None

    on_behalf = False
    # on_behalf=True is filed by a staff member of the application's own program. (Not a Trait:
    # factory_boy rejects a trait that shares its name with the field it sets.)
    created_by = factory.declarations.LazyAttribute(
        lambda o: MembershipFactory.create(program=o.program).user if o.on_behalf else None
    )


class DocumentFactory(factory.django.DjangoModelFactory[Document]):
    class Meta:
        model = Document

    application = factory.declarations.SubFactory(ApplicationFactory)
    requirement = factory.declarations.SubFactory(
        RequiredDocumentFactory,
        program=factory.declarations.SelfAttribute("..application.program"),
    )
    status = Document.Status.PENDING


class DocumentFileFactory(factory.django.DjangoModelFactory[DocumentFile]):
    class Meta:
        model = DocumentFile

    document = factory.declarations.SubFactory(DocumentFactory)
    file = factory.declarations.SubFactory(
        StoredFileFactory,
        status=StoredFile.Status.READY,
        purpose=StoredFile.Purpose.DOCUMENT,
        sha256="a" * 64,
        sniffed_type="application/pdf",
        uploaded_by=factory.declarations.SelfAttribute("..document.application.profile.user"),
    )
    version = 1
    is_current = True
