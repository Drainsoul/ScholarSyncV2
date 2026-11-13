from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.applications import review
from apps.applications.models import Application, Document
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.core.models import AuditEvent
from apps.core.transitions import InvalidTransition
from apps.programs.models import Program
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.students.models import StudentProfile

pytestmark = pytest.mark.django_db

S = Application.Status
D = Document.Status
ALREADY_STARTED = "Someone has already started reviewing this application."
START_FIRST = "Start the review before you check documents."
NEED_REASON = "Say why you're declining this document."
REASON_TOO_LONG = "Keep the reason under 500 characters."


def staff_of(program: Program) -> User:
    return MembershipFactory.create(program=program).user


def submitted(program: Program, status: str = S.SUBMITTED, **kwargs: object) -> Application:
    now = timezone.now()
    kwargs.setdefault("submitted_at", now)
    kwargs.setdefault("first_submitted_at", kwargs["submitted_at"])
    return ApplicationFactory.create(program=program, status=status, **kwargs)


def document_with_file(application: Application, status: str = D.PENDING) -> Document:
    document = DocumentFactory.create(application=application, status=status)
    DocumentFileFactory.create(document=document)
    return document


def audit_count() -> int:
    return AuditEvent.objects.count()


# start_review


def test_start_review_moves_to_under_review_and_audits() -> None:
    program = ProgramFactory.create()
    actor = staff_of(program)
    application = submitted(program)
    result = review.start_review(actor=actor, program=program, application=application)
    assert result.status == S.UNDER_REVIEW
    application.refresh_from_db()
    assert application.status == S.UNDER_REVIEW
    event = AuditEvent.objects.get(action="application.review_started")
    assert event.actor == actor
    assert event.program == program
    assert event.target_type == "applications.application"
    assert event.target_id == str(application.pk)
    assert event.data == {}


def test_second_start_review_is_refused_with_sentence() -> None:
    program = ProgramFactory.create()
    actor = staff_of(program)
    other = staff_of(program)
    application = submitted(program)
    review.start_review(actor=actor, program=program, application=application)
    # The second click still holds the stale in-memory row that says "submitted".
    stale = Application.objects.get(pk=application.pk)
    stale.status = S.SUBMITTED
    with pytest.raises(ValidationError) as exc:
        review.start_review(actor=other, program=program, application=stale)
    assert not isinstance(exc.value, InvalidTransition)
    assert exc.value.messages == [ALREADY_STARTED]
    assert AuditEvent.objects.filter(action="application.review_started").count() == 1


@pytest.mark.parametrize("status", [S.RETURNED, S.WITHDRAWN, S.APPROVED, S.REJECTED])
def test_start_review_refused_for_draft_returned_and_withdrawn(status: str) -> None:
    program = ProgramFactory.create()
    actor = staff_of(program)
    application = submitted(program, status)
    before = audit_count()
    with pytest.raises(InvalidTransition):
        review.start_review(actor=actor, program=program, application=application)
    application.refresh_from_db()
    assert application.status == status
    assert audit_count() == before


def test_start_review_on_a_never_submitted_draft_is_404() -> None:
    program = ProgramFactory.create()
    actor = staff_of(program)
    for application in (
        ApplicationFactory.create(program=program, status=S.DRAFT),
        ApplicationFactory.create(program=program, status=S.WITHDRAWN),
    ):
        with pytest.raises(Http404):
            review.start_review(actor=actor, program=program, application=application)
        status = application.status
        application.refresh_from_db()
        assert application.status == status
    assert audit_count() == 0


def test_other_program_staff_cannot_start_review() -> None:
    tcu = ProgramFactory.create()
    lani = ProgramFactory.create()
    application = submitted(tcu)
    with pytest.raises(PermissionDenied):
        review.start_review(actor=staff_of(lani), program=tcu, application=application)
    with pytest.raises(PermissionDenied):
        review.start_review(
            actor=UserFactory.create(), program=tcu, application=application
        )  # a student
    application.refresh_from_db()
    assert application.status == S.SUBMITTED
    assert audit_count() == 0


def test_unknown_or_other_program_id_404() -> None:
    tcu = ProgramFactory.create()
    lani = ProgramFactory.create()
    tcu_application = submitted(tcu)
    lani_staff = staff_of(lani)
    with pytest.raises(Http404):
        review.start_review(actor=lani_staff, program=lani, application=tcu_application)
    ghost = Application(pk=tcu_application.pk + 1000)
    with pytest.raises(Http404):
        review.start_review(actor=lani_staff, program=lani, application=ghost)
    tcu_application.refresh_from_db()
    assert tcu_application.status == S.SUBMITTED
    assert audit_count() == 0


def test_office_can_start_review() -> None:
    program = ProgramFactory.create()
    office = UserFactory.create(role=User.Role.SUPER_ADMIN)
    application = submitted(program)
    assert (
        review.start_review(actor=office, program=program, application=application).status
        == S.UNDER_REVIEW
    )


@pytest.mark.django_db(transaction=True)
def test_start_review_runs_in_its_own_transaction() -> None:
    # Without @transaction.atomic, select_for_update outside a transaction raises.
    program = ProgramFactory.create()
    application = submitted(program)
    review.start_review(actor=staff_of(program), program=program, application=application)
    application.refresh_from_db()
    assert application.status == S.UNDER_REVIEW


# document decisions


def test_approve_and_decline_document_set_reviewer_and_audit() -> None:
    program = ProgramFactory.create()
    actor = staff_of(program)
    application = submitted(program, S.UNDER_REVIEW)
    first = document_with_file(application)
    second = document_with_file(application)

    approved = review.approve_document(
        actor=actor, program=program, application=application, document_id=first.pk
    )
    assert approved.status == D.APPROVED
    first.refresh_from_db()
    assert first.status == D.APPROVED
    assert first.reviewed_by == actor
    assert first.reviewed_at is not None
    assert first.decline_reason == ""

    declined = review.decline_document(
        actor=actor,
        program=program,
        application=application,
        document_id=second.pk,
        reason="  The photo is blurry.  ",
    )
    assert declined.status == D.DECLINED
    second.refresh_from_db()
    assert second.status == D.DECLINED
    assert second.reviewed_by == actor
    assert second.reviewed_at is not None
    assert second.decline_reason == "The photo is blurry."

    approve_event = AuditEvent.objects.get(action="document.approved")
    assert approve_event.target_type == "applications.document"
    assert approve_event.target_id == str(first.pk)
    assert approve_event.program == program
    assert approve_event.data == {"requirement": first.requirement.code}
    decline_event = AuditEvent.objects.get(action="document.declined")
    assert decline_event.target_id == str(second.pk)
    assert decline_event.data == {"requirement": second.requirement.code}
    assert "blurry" not in str(decline_event.data)
    application.refresh_from_db()
    assert application.status == S.UNDER_REVIEW


@pytest.mark.parametrize("status", [S.SUBMITTED, S.RETURNED, S.APPROVED])
def test_document_decision_needs_under_review(status: str) -> None:
    program = ProgramFactory.create()
    actor = staff_of(program)
    application = submitted(program, status)
    document = document_with_file(application)
    with pytest.raises(ValidationError) as exc:
        review.approve_document(
            actor=actor, program=program, application=application, document_id=document.pk
        )
    assert exc.value.messages == [START_FIRST]
    with pytest.raises(ValidationError) as exc:
        review.decline_document(
            actor=actor,
            program=program,
            application=application,
            document_id=document.pk,
            reason="Blurry.",
        )
    assert exc.value.messages == [START_FIRST]
    document.refresh_from_db()
    assert document.status == D.PENDING
    assert audit_count() == 0


@pytest.mark.parametrize(
    ("reason", "message"),
    [("", NEED_REASON), ("   \n\t ", NEED_REASON), ("x" * 501, REASON_TOO_LONG)],
)
def test_decline_needs_a_reason_under_500_chars(reason: str, message: str) -> None:
    program = ProgramFactory.create()
    actor = staff_of(program)
    application = submitted(program, S.UNDER_REVIEW)
    document = document_with_file(application)
    with pytest.raises(ValidationError) as exc:
        review.decline_document(
            actor=actor,
            program=program,
            application=application,
            document_id=document.pk,
            reason=reason,
        )
    assert exc.value.messages == [message]
    document.refresh_from_db()
    assert document.status == D.PENDING
    assert document.reviewed_by is None
    assert audit_count() == 0


def test_decline_accepts_exactly_500_chars() -> None:
    program = ProgramFactory.create()
    application = submitted(program, S.UNDER_REVIEW)
    document = document_with_file(application)
    review.decline_document(
        actor=staff_of(program),
        program=program,
        application=application,
        document_id=document.pk,
        reason=" " + "x" * 500 + " ",
    )
    document.refresh_from_db()
    assert document.decline_reason == "x" * 500


def test_document_from_another_application_404() -> None:
    tcu = ProgramFactory.create()
    lani = ProgramFactory.create()
    actor = staff_of(tcu)
    mine = submitted(tcu, S.UNDER_REVIEW)
    sibling = document_with_file(submitted(tcu, S.UNDER_REVIEW))
    elsewhere = document_with_file(submitted(lani, S.UNDER_REVIEW))
    for document_id in (sibling.pk, elsewhere.pk, elsewhere.pk + 1000):
        with pytest.raises(Http404):
            review.approve_document(
                actor=actor, program=tcu, application=mine, document_id=document_id
            )
        with pytest.raises(Http404):
            review.decline_document(
                actor=actor, program=tcu, application=mine, document_id=document_id, reason="No."
            )
    # And another program's application through this program's URL.
    with pytest.raises(Http404):
        review.approve_document(
            actor=actor,
            program=tcu,
            application=elsewhere.application,
            document_id=elsewhere.pk,
        )
    for document in (sibling, elsewhere):
        document.refresh_from_db()
        assert document.status == D.PENDING
    assert audit_count() == 0


def test_document_without_a_current_file_is_refused() -> None:
    program = ProgramFactory.create()
    application = submitted(program, S.UNDER_REVIEW)
    document = DocumentFactory.create(application=application)
    DocumentFileFactory.create(document=document, is_current=False)
    with pytest.raises(ValidationError) as exc:
        review.approve_document(
            actor=staff_of(program),
            program=program,
            application=application,
            document_id=document.pk,
        )
    assert exc.value.messages == [review.NO_CURRENT_FILE]
    document.refresh_from_db()
    assert document.status == D.PENDING
    assert audit_count() == 0


def test_approved_document_cannot_be_declined() -> None:
    program = ProgramFactory.create()
    actor = staff_of(program)
    application = submitted(program, S.UNDER_REVIEW)
    document = document_with_file(application)
    review.approve_document(
        actor=actor, program=program, application=application, document_id=document.pk
    )
    with pytest.raises(InvalidTransition):
        review.decline_document(
            actor=actor,
            program=program,
            application=application,
            document_id=document.pk,
            reason="Changed my mind.",
        )
    with pytest.raises(InvalidTransition):  # a double click on approve
        review.approve_document(
            actor=actor, program=program, application=application, document_id=document.pk
        )
    document.refresh_from_db()
    assert document.status == D.APPROVED
    assert document.decline_reason == ""
    assert AuditEvent.objects.filter(target_type="applications.document").count() == 1


def test_other_program_staff_cannot_decide_documents() -> None:
    tcu = ProgramFactory.create()
    application = submitted(tcu, S.UNDER_REVIEW)
    document = document_with_file(application)
    with pytest.raises(PermissionDenied):
        review.approve_document(
            actor=staff_of(ProgramFactory.create()),
            program=tcu,
            application=application,
            document_id=document.pk,
        )
    assert audit_count() == 0


# locking


def test_staff_service_locks_profile_before_application() -> None:
    program = ProgramFactory.create()
    actor = staff_of(program)
    application = submitted(program)
    calls = Mock()
    with (
        patch.object(
            StudentProfile.objects,
            "select_for_update",
            wraps=StudentProfile.objects.select_for_update,
        ) as profile_lock,
        patch.object(
            Application.objects,
            "select_for_update",
            wraps=Application.objects.select_for_update,
        ) as application_lock,
    ):
        calls.attach_mock(profile_lock, "profile")
        calls.attach_mock(application_lock, "application")
        review.start_review(actor=actor, program=program, application=application)
    assert [call[0] for call in calls.mock_calls] == ["profile", "application"]
    application_lock.assert_called_once_with(of=("self",))


def test_lock_for_staff_returns_the_profile_and_the_locked_application() -> None:
    program = ProgramFactory.create()
    application = submitted(program)
    profile, locked = review._lock_for_staff(staff_of(program), program, application.pk)
    assert profile.pk == application.profile_id
    assert locked.pk == application.pk
    assert locked is not application
