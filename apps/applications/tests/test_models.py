import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.applications.models import Application, Document
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.programs.tests.factories import SchoolFactory

pytestmark = pytest.mark.django_db


def test_one_open_application_per_profile_program_term() -> None:
    first = ApplicationFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        ApplicationFactory.create(profile=first.profile, program=first.program, term=first.term)
    for closed in (Application.Status.WITHDRAWN, Application.Status.REJECTED):
        Application.objects.filter(profile=first.profile, status=Application.Status.DRAFT).update(
            status=closed, school_name="Somewhere"
        )
        ApplicationFactory.create(profile=first.profile, program=first.program, term=first.term)


def test_status_and_kind_check_constraints() -> None:
    app = ApplicationFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        Application.objects.filter(pk=app.pk).update(status="nope")
    with pytest.raises(IntegrityError), transaction.atomic():
        Application.objects.filter(pk=app.pk).update(kind="nope")


def test_school_and_school_name_not_both() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        ApplicationFactory.create(school=SchoolFactory(), school_name="Somewhere")


def test_submitted_application_has_a_school() -> None:
    """Exactly one school source once submitted; drafts and never-submitted withdrawals have none."""
    app = ApplicationFactory.create()
    for status in ("submitted", "under_review", "returned", "approved", "rejected"):
        with pytest.raises(IntegrityError), transaction.atomic():
            Application.objects.filter(pk=app.pk).update(status=status)
    with pytest.raises(IntegrityError), transaction.atomic():
        Application.objects.filter(pk=app.pk).update(
            status="withdrawn", submitted_at=timezone.now()
        )
    Application.objects.filter(pk=app.pk).update(status="withdrawn")
    Application.objects.filter(pk=app.pk).update(status="submitted", school_name="Somewhere")
    Application.objects.filter(pk=app.pk).update(school=SchoolFactory.create(), school_name="")


def test_one_document_per_requirement_per_application() -> None:
    doc = DocumentFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentFactory.create(application=doc.application, requirement=doc.requirement)


def test_one_current_file_per_document() -> None:
    df = DocumentFileFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentFileFactory.create(document=df.document, version=2, is_current=True)
    DocumentFileFactory.create(document=df.document, version=2, is_current=False)


def test_versions_unique_per_document() -> None:
    df = DocumentFileFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentFileFactory.create(document=df.document, version=1, is_current=False)


def test_a_stored_file_backs_one_document_file() -> None:
    df = DocumentFileFactory.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentFileFactory.create(file=df.file)


def test_transitions_table_matches_spec() -> None:
    s = Application.Status
    assert Application.TRANSITIONS == {
        s.DRAFT: {s.SUBMITTED, s.WITHDRAWN},
        s.SUBMITTED: {s.UNDER_REVIEW, s.WITHDRAWN},
        s.UNDER_REVIEW: {s.RETURNED, s.APPROVED, s.REJECTED},
        s.RETURNED: {s.SUBMITTED, s.WITHDRAWN},
    }
    d = Document.Status
    assert Document.TRANSITIONS == {d.PENDING: {d.APPROVED, d.DECLINED}, d.DECLINED: {d.PENDING}}
    assert Application.OPEN_STATUSES == {s.DRAFT, s.SUBMITTED, s.UNDER_REVIEW, s.RETURNED}


def test_is_editable() -> None:
    assert ApplicationFactory.build(status="draft").is_editable
    assert ApplicationFactory.build(status="returned").is_editable
    assert not ApplicationFactory.build(status="submitted").is_editable


def test_cleanup_runs_with_document_files() -> None:
    DocumentFileFactory.create()
    call_command("cleanup")
