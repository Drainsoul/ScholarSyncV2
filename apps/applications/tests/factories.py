import factory

from apps.applications.models import Application, Document, DocumentFile
from apps.files.models import StoredFile
from apps.files.tests.factories import StoredFileFactory
from apps.programs.tests.factories import (
    AcademicTermFactory,
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
