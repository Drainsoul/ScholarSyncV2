import pytest
from django.http import Http404

from apps.accounts.models import User
from apps.applications.models import Application, Document
from apps.applications.selectors import (
    applications_for_student,
    document_rows,
    missing_documents,
    open_application,
    own_application,
)
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.programs.models import RequiredDocument
from apps.programs.tests.factories import AcademicTermFactory, RequiredDocumentFactory
from apps.students.models import StudentProfile

pytestmark = pytest.mark.django_db


def user_of(profile: StudentProfile) -> User:
    assert profile.user is not None
    return profile.user


def test_document_rows_cover_required_documents_for_kind() -> None:
    application = ApplicationFactory.create()
    program = application.program
    both = RequiredDocumentFactory.create(program=program, code="both", sort_order=1)
    new = RequiredDocumentFactory.create(
        program=program, code="new", applies_to=RequiredDocument.AppliesTo.NEW, sort_order=2
    )
    RequiredDocumentFactory.create(
        program=program, code="renewal", applies_to=RequiredDocument.AppliesTo.RENEWAL
    )
    RequiredDocumentFactory.create(code="other-program")
    document = DocumentFactory.create(application=application, requirement=both)
    DocumentFileFactory.create(document=document, version=1, is_current=False)
    current = DocumentFileFactory.create(document=document, version=2)

    rows = document_rows(application)

    assert [row.requirement.code for row in rows] == ["both", "new"]
    assert rows[0].document == document
    assert rows[0].current == current.file
    assert rows[1].requirement == new
    assert rows[1].document is None
    assert rows[1].current is None


def test_document_rows_query_budget(django_assert_max_num_queries) -> None:
    application = ApplicationFactory.create()
    for index in range(3):
        requirement = RequiredDocumentFactory.create(program=application.program)
        document = DocumentFactory.create(application=application, requirement=requirement)
        DocumentFileFactory.create(document=document, version=1, is_current=index != 0)
    with django_assert_max_num_queries(3):
        rows = document_rows(application)
        assert [row.current is not None for row in rows] == [False, True, True]


def test_missing_documents_required_without_file_or_declined() -> None:
    application = ApplicationFactory.create()
    program = application.program
    no_file = RequiredDocumentFactory.create(program=program, code="no-file", sort_order=1)
    RequiredDocumentFactory.create(program=program, code="optional", is_required=False)
    declined = RequiredDocumentFactory.create(program=program, code="declined", sort_order=2)
    fine = RequiredDocumentFactory.create(program=program, code="fine", sort_order=3)
    bad = DocumentFactory.create(
        application=application, requirement=declined, status=Document.Status.DECLINED
    )
    DocumentFileFactory.create(document=bad)
    DocumentFileFactory.create(
        document=DocumentFactory.create(application=application, requirement=fine)
    )

    assert missing_documents(application) == [no_file, declined]


def test_own_application_404_for_other_student() -> None:
    mine = ApplicationFactory.create()
    theirs = ApplicationFactory.create()
    user = user_of(mine.profile)
    assert own_application(user, mine.pk) == mine
    with pytest.raises(Http404):
        own_application(user, theirs.pk)


def test_applications_for_student_newest_first_and_own_only() -> None:
    first = ApplicationFactory.create()
    second = ApplicationFactory.create(profile=first.profile)
    ApplicationFactory.create()
    assert list(applications_for_student(user_of(first.profile))) == [second, first]


def test_open_application_ignores_closed() -> None:
    term = AcademicTermFactory.create()
    closed = ApplicationFactory.create(term=term, status=Application.Status.WITHDRAWN)
    assert open_application(closed.profile, closed.program, term) is None
    draft = ApplicationFactory.create(profile=closed.profile, program=closed.program, term=term)
    assert open_application(closed.profile, closed.program, term) == draft
