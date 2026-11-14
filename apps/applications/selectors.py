from dataclasses import dataclass
from typing import Literal, cast

from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import Http404

from apps.accounts.models import User
from apps.applications.models import Application, Document, DocumentFile
from apps.awards.selectors import holds_active_award
from apps.core.permissions import require_program_staff
from apps.files.models import StoredFile
from apps.programs.models import AcademicTerm, Program, RequiredDocument
from apps.programs.selectors import required_documents_for
from apps.students.models import StudentProfile


@dataclass(frozen=True)
class DocumentRow:
    requirement: RequiredDocument
    document: Document | None
    current: StoredFile | None


def own_applications(user: User) -> QuerySet[Application]:
    """The student's own applications, unordered. Services lock rows from this queryset."""
    return Application.objects.filter(profile__user=user)


def applications_for_student(user: User) -> QuerySet[Application]:
    return own_applications(user).select_related("program", "term").order_by("-created_at", "-pk")


def own_application(user: User, pk: int) -> Application:
    application = (
        own_applications(user)
        .select_related("program", "term", "requested_tier")
        .filter(pk=pk)
        .first()
    )
    if application is None:
        raise Http404("No such application.")
    return application


def open_application(
    profile: StudentProfile, program: Program, term: AcademicTerm
) -> Application | None:
    return Application.objects.filter(
        profile=profile, program=program, term=term, status__in=Application.OPEN_STATUSES
    ).first()


def holds_scholarship(profile: StudentProfile, program: Program, term: AcademicTerm) -> bool:
    """An approved application for this program and term, or an active award in the program."""
    return Application.objects.filter(
        profile=profile, program=program, term=term, status=Application.Status.APPROVED
    ).exists() or holds_active_award(profile, program)


def document_rows(application: Application) -> list[DocumentRow]:
    """One row per requirement for the application's kind, in order. Three queries."""
    requirements = list(
        required_documents_for(
            application.program, cast(Literal["new", "renewal"], application.kind)
        )
    )
    documents = {
        document.requirement_id: document
        for document in Document.objects.filter(application=application)
    }
    current = {
        row.document_id: row.file
        for row in DocumentFile.objects.filter(
            document__application=application, is_current=True
        ).select_related("file")
    }
    rows = []
    for requirement in requirements:
        document = documents.get(requirement.pk)
        rows.append(
            DocumentRow(
                requirement=requirement,
                document=document,
                current=current.get(document.pk) if document is not None else None,
            )
        )
    return rows


def staff_can_download(user: User, file: StoredFile) -> bool:
    """True when the file backs any version of a submitted application's document, and the user
    is staff of that application's program (or the office). One query."""
    row = (
        DocumentFile.objects.filter(file=file, document__application__submitted_at__isnull=False)
        .select_related("document__application__program")
        .first()
    )
    if row is None:
        return False
    try:
        require_program_staff(user, row.document.application.program)
    except PermissionDenied:
        return False
    return True


def missing_documents(application: Application) -> list[RequiredDocument]:
    """Required documents with no current file, and any document staff declined."""
    return [
        row.requirement
        for row in document_rows(application)
        if (row.requirement.is_required and row.current is None)
        or (row.document is not None and row.document.status == Document.Status.DECLINED)
    ]
