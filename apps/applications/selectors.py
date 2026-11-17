from dataclasses import dataclass
from typing import Literal, cast

from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import Http404

from apps.accounts.models import User
from apps.applications.models import Application, Document, DocumentFile
from apps.awards.selectors import holds_award
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
    """An approved application for this program and term, or an award held in the program."""
    return Application.objects.filter(
        profile=profile, program=program, term=term, status=Application.Status.APPROVED
    ).exists() or holds_award(profile, program)


def rejected_this_term(profile: StudentProfile, program: Program, term: AcademicTerm) -> bool:
    """A rejected application for this program and term: the rejection stands until next term."""
    return Application.objects.filter(
        profile=profile, program=program, term=term, status=Application.Status.REJECTED
    ).exists()


def applicable_requirements(application: Application) -> QuerySet[RequiredDocument]:
    """The active requirements this application answers to (M11b).

    A draft follows the program's current list. Once submitted, a requirement added later
    applies only if the application already has an upload for it, so a new requirement never
    blocks an application in review."""
    rows = required_documents_for(
        application.program, cast(Literal["new", "renewal"], application.kind)
    )
    if application.first_submitted_at is None:
        return rows
    uploaded = Document.objects.filter(application=application).values("requirement_id")
    return rows.filter(Q(created_at__lte=application.first_submitted_at) | Q(pk__in=uploaded))


def document_rows(application: Application) -> list[DocumentRow]:
    """One row per requirement for the application's kind, in order. Three queries."""
    requirements = list(applicable_requirements(application))
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
    """True when the file backs any version of a document on a submitted application, or on an
    on-behalf application whatever its status, and the user is staff of that application's
    program (or the office). Two queries: the document row with its application and program,
    then (for staff, not the office) the membership."""
    row = (
        DocumentFile.objects.filter(
            Q(document__application__submitted_at__isnull=False)
            | Q(document__application__on_behalf=True),
            file=file,
        )
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


def student_can_download(user: User, file: StoredFile) -> bool:
    """True when the file backs a document on one of the student's own applications. One query."""
    return DocumentFile.objects.filter(
        file=file, document__application__profile__user=user
    ).exists()


def missing_documents(application: Application) -> list[RequiredDocument]:
    """Required documents with no current file, and any document staff declined."""
    return [
        row.requirement
        for row in document_rows(application)
        if (row.requirement.is_required and row.current is None)
        or (row.document is not None and row.document.status == Document.Status.DECLINED)
    ]


def undecided_rows(application: Application) -> list[DocumentRow]:
    """What still stands between the application and approval, in requirement order: a required
    requirement with no approved document, and any document still pending or declined."""
    return [
        row
        for row in document_rows(application)
        if (
            row.requirement.is_required
            and (row.document is None or row.document.status != Document.Status.APPROVED)
        )
        or (
            row.document is not None
            and row.document.status in (Document.Status.PENDING, Document.Status.DECLINED)
        )
    ]


def undecided_documents(application: Application) -> list[RequiredDocument]:
    """`undecided_rows`, as requirements."""
    return [row.requirement for row in undecided_rows(application)]
