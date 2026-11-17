from typing import Any

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.applications import review
from apps.applications.models import Application, Document
from apps.applications.selectors import document_rows, missing_documents
from apps.applications.tests.factories import ApplicationFactory, DocumentFactory
from apps.applications.tests.test_review import approvable, staff_of
from apps.core.models import AuditEvent
from apps.files.policy import MB
from apps.programs.models import Program, ProgramMembership, RequiredDocument
from apps.programs.tests.factories import (
    MembershipFactory,
    ProgramFactory,
    RequiredDocumentFactory,
)

pytestmark = pytest.mark.django_db


def _head(program: Program) -> User:
    return MembershipFactory.create(program=program, level=ProgramMembership.Level.HEAD).user


def _url(name: str, program: Program, **kwargs: object) -> str:
    return reverse(f"settings:{name}", kwargs={"program": program.slug, **kwargs})


def _form(**changes: object) -> dict[str, object]:
    data: dict[str, object] = {
        "code": "barangay-clearance",
        "label": "Barangay clearance",
        "help_text": "From your barangay hall.\r\nIssued this year.",
        "applies_to": "both",
        "is_required": "on",
        "accepted_types": ["application/pdf", "image/jpeg"],
        "max_mb": "5",
        "sort_order": "3",
    }
    data.update(changes)
    return data


def test_added_requirement_skips_applications_already_started() -> None:
    """An application in review keeps its list when a requirement is added."""
    program = ProgramFactory.create()
    application = approvable(program)
    rows_before = len(document_rows(application))
    RequiredDocumentFactory.create(program=program, label="New rule")
    assert len(document_rows(application)) == rows_before
    review.approve_application(
        actor=staff_of(program), program=program, application=application, tier=None
    )
    application.refresh_from_db()
    assert application.status == Application.Status.APPROVED


def test_new_draft_after_addition_needs_it() -> None:
    program = ProgramFactory.create()
    old = RequiredDocumentFactory.create(program=program)
    new = RequiredDocumentFactory.create(program=program)
    draft = ApplicationFactory.create(program=program)
    assert [row.requirement for row in document_rows(draft)] == [old, new]


def test_stopping_a_requirement_unblocks_submit(client: Any) -> None:
    program = ProgramFactory.create()
    needed = RequiredDocumentFactory.create(program=program)
    draft = ApplicationFactory.create(program=program)
    assert missing_documents(draft) == [needed]
    client.force_login(_head(program))
    client.post(_url("document-active", program, pk=needed.pk), {"active": "0"})
    assert missing_documents(draft) == []
    assert AuditEvent.objects.filter(action="document.stopped").count() == 1
    client.post(_url("document-active", program, pk=needed.pk), {"active": "1"})
    assert missing_documents(draft) == [needed]
    assert AuditEvent.objects.filter(action="document.restored").count() == 1


def test_uploaded_document_still_counts_after_submit() -> None:
    """An upload for a requirement the program added later still counts on that application."""
    program = ProgramFactory.create()
    application = approvable(program)
    late = DocumentFactory.create(application=application, status=Document.Status.PENDING)
    assert late.requirement in [row.requirement for row in document_rows(application)]


def test_add_document_from_the_page(client: Any) -> None:
    program = ProgramFactory.create()
    client.force_login(_head(program))
    response = client.post(_url("documents", program), _form())
    assert response.status_code == 302
    document = RequiredDocument.objects.get(program=program, code="barangay-clearance")
    assert document.max_bytes == 5 * MB
    assert document.accepted_types == ["application/pdf", "image/jpeg"]
    assert document.help_text == "From your barangay hall.\nIssued this year."
    event = AuditEvent.objects.get(action="document.added")
    assert "Barangay" not in str(event.data)


def test_public_program_page_lists_only_active(client: Any) -> None:
    program = ProgramFactory.create()
    RequiredDocumentFactory.create(program=program, label="Still asked")
    RequiredDocumentFactory.create(program=program, label="No longer asked", is_active=False)
    page = client.get(reverse("programs:detail", kwargs={"slug": program.slug})).content.decode()
    assert "Still asked" in page and "No longer asked" not in page


def test_edit_keeps_code(client: Any) -> None:
    program = ProgramFactory.create()
    document = RequiredDocumentFactory.create(program=program, code="grades")
    client.force_login(_head(program))
    client.post(
        _url("document-edit", program, pk=document.pk),
        _form(code="changed", label="Certificate of grades"),
    )
    document.refresh_from_db()
    assert (document.code, document.label) == ("grades", "Certificate of grades")
    assert AuditEvent.objects.filter(action="document.updated").count() == 1


def test_code_taken_refused(client: Any) -> None:
    program = ProgramFactory.create()
    RequiredDocumentFactory.create(program=program, code="barangay-clearance")
    client.force_login(_head(program))
    response = client.post(_url("documents", program), _form())
    assert "That document code is taken." in response.content.decode()


def test_document_from_another_program_404(client: Any) -> None:
    program = ProgramFactory.create()
    other = RequiredDocumentFactory.create()
    client.force_login(_head(program))
    assert client.get(_url("document-edit", program, pk=other.pk)).status_code == 404
    response = client.post(_url("document-active", program, pk=other.pk), {"active": "0"})
    assert response.status_code == 404
    other.refresh_from_db()
    assert other.is_active


@pytest.mark.parametrize("changes", [{"max_mb": "0"}, {"max_mb": "11"}, {"accepted_types": []}])
def test_max_size_and_types_validated(client: Any, changes: dict[str, object]) -> None:
    program = ProgramFactory.create()
    client.force_login(_head(program))
    response = client.post(_url("documents", program), _form(**changes))
    assert response.status_code == 200
    assert not RequiredDocument.objects.filter(program=program).exists()


def test_documents_page_query_count(client: Any, django_assert_max_num_queries: Any) -> None:
    program = ProgramFactory.create()
    RequiredDocumentFactory.create_batch(50, program=program)
    client.force_login(_head(program))
    with django_assert_max_num_queries(14):
        assert client.get(_url("documents", program)).status_code == 200
