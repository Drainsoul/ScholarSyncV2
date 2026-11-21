"""Report services: send, resend, the head's review, decide (M11c, rev 33)."""

import threading
from datetime import date
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.models import Program
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.reports import services
from apps.reports.models import Report
from apps.reports.services import (
    decide_report,
    head_approve_report,
    head_return_report,
    period_label,
    resubmit_report,
    send_report_to_office,
    submit_report,
)
from apps.reports.tests.factories import ready_report_file
from apps.workspace.models import Notification

AUG = date(2026, 8, 1)
OCT = date(2026, 10, 31)
TITLE = "Secret quarterly title"
DESCRIPTION = "Private description words"
NOTE = "Confidential office note"


def _program() -> Program:
    return ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")


def _staff(program: Program) -> User:
    return MembershipFactory.create(program=program).user


def _head(program: Program) -> User:
    return MembershipFactory.create(program=program, level="head").user


def _office() -> User:
    return UserFactory.create(role=User.Role.SUPER_ADMIN)


def _send(actor: User, program: Program, **overrides: Any) -> Report:
    kwargs: dict[str, Any] = {
        "title": TITLE,
        "period_start": AUG,
        "period_end": OCT,
        "description": DESCRIPTION,
        "file": ready_report_file(actor),
    }
    kwargs.update(overrides)
    return submit_report(actor=actor, program=program, **kwargs)


def test_period_label() -> None:
    assert period_label(AUG, OCT) == "1 August 2026 to 31 October 2026"


@pytest.mark.django_db
def test_head_submit_goes_to_the_office_with_notifications() -> None:
    program = _program()
    staff = _head(program)
    first, second = _office(), _office()
    UserFactory.create(role=User.Role.SUPER_ADMIN, is_active=False)
    report = _send(staff, program)
    assert report.status == Report.Status.SUBMITTED
    assert report.submitted_by == staff and report.submitted_at is not None
    assert (report.sent_by, report.sent_at) == (staff, report.submitted_at)
    assert report.files.count() == 1
    event = AuditEvent.objects.get(action="report.submitted")
    assert event.program == program
    assert event.data == {"report": report.pk}
    rows = Notification.objects.filter(kind="report_submitted").order_by("recipient_id")
    assert [row.recipient for row in rows] == [first, second]
    assert {row.title for row in rows} == {"TCU CEAA sent a report for review"}
    assert {row.body for row in rows} == {"1 August 2026 to 31 October 2026."}
    assert {row.url for row in rows} == {f"/office/reports/{report.pk}/"}


@pytest.mark.django_db
def test_period_end_before_start_refused() -> None:
    program = _program()
    with pytest.raises(ValidationError) as caught:
        _send(_staff(program), program, period_start=OCT, period_end=AUG)
    assert caught.value.messages == ["The period must end on or after its start."]
    assert not Report.objects.exists()


@pytest.mark.django_db
def test_staff_of_other_program_cannot_submit() -> None:
    program = _program()
    other = ProgramFactory.create(slug="lani")
    with pytest.raises(PermissionDenied):
        _send(_staff(other), program)


@pytest.mark.django_db
def test_wrong_purpose_file_refused() -> None:
    from apps.files.tests.factories import StoredFileFactory

    program = _program()
    staff = _staff(program)
    document = StoredFileFactory.create(
        uploaded_by=staff, status="ready", sha256="0" * 64, sniffed_type="application/pdf"
    )
    with pytest.raises(ValidationError) as caught:
        _send(staff, program, file=document)
    assert caught.value.messages == ["Upload the report as a PDF."]


@pytest.mark.django_db
def test_accept_notifies_submitter_without_note_text() -> None:
    program = _program()
    staff = _head(program)
    report = _send(staff, program)
    office = _office()
    decide_report(actor=office, report=report, accept=True, note=NOTE)
    report.refresh_from_db()
    assert report.status == Report.Status.ACCEPTED
    assert report.reviewed_by == office and report.reviewed_at is not None
    assert report.review_note == NOTE
    row = Notification.objects.get(kind="report_accepted")
    assert row.recipient == staff
    assert row.title == "The office accepted your TCU CEAA report"
    assert row.body == ""
    assert row.url == f"/staff/tcu-ceaa/reports/{report.pk}/"
    assert AuditEvent.objects.filter(action="report.accepted", program=program).count() == 1


@pytest.mark.django_db
def test_return_requires_note_and_notifies() -> None:
    program = _program()
    staff = _head(program)
    report = _send(staff, program)
    office = _office()
    with pytest.raises(ValidationError) as caught:
        decide_report(actor=office, report=report, accept=False, note="  \r\n ")
    assert caught.value.messages == ["Say what the program should change."]
    decide_report(actor=office, report=report, accept=False, note="Fix\r\nthe totals")
    report.refresh_from_db()
    assert report.status == Report.Status.RETURNED
    assert report.review_note == "Fix\nthe totals"
    row = Notification.objects.get(kind="report_returned")
    assert row.recipient == staff
    assert row.title == "The office returned your TCU CEAA report"
    assert row.body == "Open it to see what to change."


@pytest.mark.django_db
def test_only_office_decides() -> None:
    program = _program()
    staff = _head(program)
    report = _send(staff, program)
    with pytest.raises(PermissionDenied):
        decide_report(actor=_head(program), report=report, accept=True, note="")


@pytest.mark.django_db
def test_resubmit_by_colleague_adds_version_and_moves_submitted_by() -> None:
    program = _program()
    first = _head(program)
    colleague = _head(program)
    office = _office()
    report = _send(first, program)
    decide_report(actor=office, report=report, accept=False, note="Add September")
    resubmit_report(
        actor=colleague,
        report=report,
        title="New title",
        period_start=AUG,
        period_end=OCT,
        description="",
        file=ready_report_file(colleague),
    )
    report.refresh_from_db()
    assert report.status == Report.Status.SUBMITTED
    assert report.submitted_by == colleague
    assert report.title == "New title"
    assert report.files.count() == 2
    assert AuditEvent.objects.filter(action="report.resubmitted").count() == 1
    titles = set(
        Notification.objects.filter(kind="report_submitted").values_list("title", flat=True)
    )
    assert titles == {"TCU CEAA sent a report for review", "TCU CEAA sent a returned report back"}


@pytest.mark.django_db
def test_resubmit_without_file_keeps_versions() -> None:
    program = _program()
    staff = _head(program)
    report = _send(staff, program)
    decide_report(actor=_office(), report=report, accept=False, note="Fix it")
    resubmit_report(
        actor=staff,
        report=report,
        title=TITLE,
        period_start=AUG,
        period_end=OCT,
        description="Fixed",
        file=None,
    )
    report.refresh_from_db()
    assert report.files.count() == 1
    assert report.description == "Fixed"


@pytest.mark.django_db
def test_accepted_is_final() -> None:
    program = _program()
    staff = _head(program)
    report = _send(staff, program)
    office = _office()
    decide_report(actor=office, report=report, accept=True, note="")
    with pytest.raises(ValidationError) as caught:
        decide_report(actor=office, report=report, accept=False, note="Late")
    assert caught.value.messages == ["This report was already accepted."]
    with pytest.raises(ValidationError) as caught:
        resubmit_report(
            actor=staff,
            report=report,
            title=TITLE,
            period_start=AUG,
            period_end=OCT,
            description="",
            file=None,
        )
    assert caught.value.messages == ["This report is no longer returned."]


@pytest.mark.django_db
def test_file_reused_by_second_report_refused() -> None:
    program = _program()
    staff = _staff(program)
    file = ready_report_file(staff)
    _send(staff, program, file=file)
    with pytest.raises(ValidationError) as caught:
        _send(staff, program, file=file)
    assert caught.value.messages == ["Upload the file again."]
    assert Report.objects.count() == 1


@pytest.mark.django_db
def test_audit_data_has_no_free_text() -> None:
    program = _program()
    staff = _head(program)
    report = _send(staff, program)
    office = _office()
    decide_report(actor=office, report=report, accept=False, note=NOTE)
    resubmit_report(
        actor=staff,
        report=report,
        title=TITLE,
        period_start=AUG,
        period_end=OCT,
        description=DESCRIPTION,
        file=None,
    )
    decide_report(actor=office, report=report, accept=True, note=NOTE)
    stored = [str(event.data) for event in AuditEvent.objects.all()]
    stored += [f"{row.title} {row.body} {row.url}" for row in Notification.objects.all()]
    for text in stored:
        for secret in (TITLE, DESCRIPTION, NOTE):
            assert secret not in text


def _race(monkeypatch: pytest.MonkeyPatch, calls: list[Any]) -> list[str]:
    """Run `calls` in two threads that pause at a barrier inside their transaction (in `record`),
    so without a row lock both would read "submitted" before either writes."""
    from django.db import connection

    barrier = threading.Barrier(2, timeout=1)
    real_record = services.record  # type: ignore[attr-defined]

    def paused_record(**kwargs: Any) -> Any:
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        return real_record(**kwargs)

    monkeypatch.setattr(services, "record", paused_record)
    outcomes: list[str] = []

    def run(call: Any) -> None:
        try:
            call()
            outcomes.append("done")
        except ValidationError as error:
            outcomes.append(" ".join(error.messages))
        except Exception as error:  # noqa: BLE001 - any other error is the bug
            outcomes.append(type(error).__name__)
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(outcomes)


@pytest.mark.django_db(transaction=True)
def test_concurrent_decisions_one_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    program = _program()
    staff = _head(program)
    report = _send(staff, program)
    first, second = _office(), _office()
    outcomes = _race(
        monkeypatch,
        [
            lambda: decide_report(
                actor=first, report=Report.objects.get(pk=report.pk), accept=True, note=""
            ),
            lambda: decide_report(
                actor=second, report=Report.objects.get(pk=report.pk), accept=False, note="No"
            ),
        ],
    )
    assert outcomes.count("done") == 1
    loser = next(outcome for outcome in outcomes if outcome != "done")
    assert loser in {"This report was already accepted.", "This report was already returned."}
    decisions = AuditEvent.objects.filter(action__in=["report.accepted", "report.returned"])
    assert decisions.count() == 1
    assert Notification.objects.filter(kind__in=["report_accepted", "report_returned"]).count() == 1


@pytest.mark.django_db
def test_double_submit_of_one_file_is_refused_not_a_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two posts racing past the "already used" check hit the unique file column."""
    program = _program()
    staff = _staff(program)
    file = ready_report_file(staff)
    _send(staff, program, file=file)
    monkeypatch.setattr(services, "_already_attached", lambda file: False)
    with pytest.raises(ValidationError) as caught:
        _send(staff, program, file=file)
    assert caught.value.messages == ["Upload the file again."]
    assert Report.objects.count() == 1


@pytest.mark.django_db
def test_office_cannot_send_reports() -> None:
    from django.core.exceptions import PermissionDenied

    program = ProgramFactory.create()
    office = _office()
    with pytest.raises(PermissionDenied):
        _send(office, program)
    assert not Report.objects.exists()


# The head reviews a staff member's report first (rev 33).


def _with_head(program: Program) -> tuple[User, User, Report]:
    staff, head = _staff(program), _head(program)
    return staff, head, _send(staff, program)


def _resubmit(actor: User, report: Report, description: str = "") -> None:
    resubmit_report(
        actor=actor,
        report=report,
        title=TITLE,
        period_start=AUG,
        period_end=OCT,
        description=description,
        file=None,
    )


@pytest.mark.django_db
def test_staff_submit_waits_for_the_head_and_tells_every_active_head() -> None:
    program = _program()
    staff = _staff(program)
    first, second = _head(program), _head(program)
    MembershipFactory.create(program=program, level="head", user__is_active=False)
    _head(ProgramFactory.create(slug="lani"))
    _office()
    report = _send(staff, program)
    assert report.status == Report.Status.WITH_HEAD
    assert report.sent_by is None and report.sent_at is None
    assert not Notification.objects.filter(kind="report_submitted").exists()
    rows = Notification.objects.filter(kind="report_for_head").order_by("recipient_id")
    assert [row.recipient for row in rows] == [first, second]
    assert {row.title for row in rows} == {"A TCU CEAA report is waiting for your review"}
    assert {row.body for row in rows} == {"1 August 2026 to 31 October 2026."}
    assert {row.url for row in rows} == {f"/staff/tcu-ceaa/reports/{report.pk}/"}
    event = AuditEvent.objects.get(action="report.submitted")
    assert event.data == {"report": report.pk}


@pytest.mark.django_db
def test_staff_submit_without_a_head_still_waits() -> None:
    program = _program()
    report = _send(_staff(program), program)
    assert report.status == Report.Status.WITH_HEAD
    assert not Notification.objects.exists()


@pytest.mark.django_db
def test_head_approves_with_optional_note_then_sends() -> None:
    program = _program()
    staff, head, report = _with_head(program)
    office = _office()
    head_approve_report(actor=head, report=report, note="Looks\r\ngood")
    report.refresh_from_db()
    assert report.status == Report.Status.APPROVED
    assert (report.head_reviewed_by, report.reviewed_by) == (head, head)
    assert report.head_reviewed_at is not None and report.review_note == "Looks\ngood"
    assert report.sent_at is None
    row = Notification.objects.get(kind="report_head_approved")
    assert (row.recipient, row.title, row.body) == (
        staff,
        "The head approved your TCU CEAA report",
        "",
    )
    assert row.url == f"/staff/tcu-ceaa/reports/{report.pk}/"
    assert not Notification.objects.filter(recipient=office).exists()
    send_report_to_office(actor=head, report=report)
    report = Report.objects.get(pk=report.pk)
    assert report.status == Report.Status.SUBMITTED
    assert report.sent_by == head and report.sent_at is not None
    assert report.submitted_by == staff
    sent = Notification.objects.get(kind="report_submitted")
    assert (sent.recipient, sent.title) == (office, "TCU CEAA sent a report for review")
    assert sent.url == f"/office/reports/{report.pk}/"
    for action in ("report.head_approved", "report.sent"):
        event = AuditEvent.objects.get(action=action)
        assert (event.actor, event.program, event.data) == (head, program, {"report": report.pk})


@pytest.mark.django_db
def test_head_approve_without_note() -> None:
    program = _program()
    _writer, head, report = _with_head(program)
    head_approve_report(actor=head, report=report, note="  ")
    report.refresh_from_db()
    assert report.status == Report.Status.APPROVED and report.review_note == ""
    assert report.head_reviewed_by == head and report.reviewed_by is None


@pytest.mark.django_db
def test_head_approve_without_note_keeps_the_office_note() -> None:
    """The office returned it, staff fixed it: the office still sees what it asked for."""
    program = _program()
    staff, head, report = _with_head(program)
    office = _office()
    head_approve_report(actor=head, report=report, note="")
    send_report_to_office(actor=head, report=report)
    decide_report(actor=office, report=report, accept=False, note="Add September")
    _resubmit(staff, report)
    head_approve_report(actor=head, report=report, note="")
    report.refresh_from_db()
    assert (report.reviewed_by, report.review_note) == (office, "Add September")


@pytest.mark.django_db
def test_head_return_needs_a_note_and_tells_the_writer() -> None:
    program = _program()
    staff, head, report = _with_head(program)
    with pytest.raises(ValidationError) as caught:
        head_return_report(actor=head, report=report, note=" \r\n")
    assert caught.value.messages == ["Say what the program should change."]
    head_return_report(actor=head, report=report, note=NOTE)
    report.refresh_from_db()
    assert report.status == Report.Status.RETURNED
    assert report.head_reviewed_by == head and report.review_note == NOTE
    assert report.sent_at is None
    row = Notification.objects.get(kind="report_head_returned")
    assert (row.recipient, row.title, row.body) == (
        staff,
        "The head returned your TCU CEAA report",
        "Open it to see what to change.",
    )
    event = AuditEvent.objects.get(action="report.head_returned")
    assert event.data == {"report": report.pk}


@pytest.mark.django_db
def test_staff_resubmit_goes_back_to_the_head() -> None:
    program = _program()
    staff, head, report = _with_head(program)
    head_return_report(actor=head, report=report, note="Add totals")
    _resubmit(staff, report)
    report.refresh_from_db()
    assert report.status == Report.Status.WITH_HEAD
    assert Notification.objects.filter(kind="report_for_head", recipient=head).count() == 2
    assert not Notification.objects.filter(kind="report_submitted").exists()


@pytest.mark.django_db
def test_head_resubmit_goes_to_the_office() -> None:
    program = _program()
    _writer, head, report = _with_head(program)
    office = _office()
    head_return_report(actor=head, report=report, note="Fix it myself")
    _resubmit(head, report)
    report.refresh_from_db()
    assert report.status == Report.Status.SUBMITTED
    assert (report.submitted_by, report.sent_by) == (head, head)
    # The office never saw it before: a plain "sent a report".
    row = Notification.objects.get(kind="report_submitted", recipient=office)
    assert row.title == "TCU CEAA sent a report for review"


@pytest.mark.django_db
def test_office_return_then_staff_fix_then_head_send_reads_as_sent_back() -> None:
    program = _program()
    staff, head, report = _with_head(program)
    office = _office()
    head_approve_report(actor=head, report=report, note="")
    send_report_to_office(actor=head, report=report)
    decide_report(actor=office, report=report, accept=False, note="Add September")
    returned = Notification.objects.filter(kind="report_returned").order_by("recipient_id")
    assert [row.recipient for row in returned] == [staff, head]
    _resubmit(staff, report)
    report.refresh_from_db()
    assert report.status == Report.Status.WITH_HEAD
    head_approve_report(actor=head, report=report, note="")
    send_report_to_office(actor=head, report=report)
    titles = list(
        Notification.objects.filter(kind="report_submitted")
        .order_by("pk")
        .values_list("title", flat=True)
    )
    assert titles == ["TCU CEAA sent a report for review", "TCU CEAA sent a returned report back"]


@pytest.mark.django_db
def test_office_decision_tells_the_writer_once_when_they_sent_it() -> None:
    program = _program()
    head = _head(program)
    report = _send(head, program)
    decide_report(actor=_office(), report=report, accept=True, note="")
    assert Notification.objects.filter(kind="report_accepted").count() == 1


@pytest.mark.django_db
def test_only_a_head_of_the_program_reviews_and_sends() -> None:
    program = _program()
    staff, head, report = _with_head(program)
    other_head = _head(ProgramFactory.create(slug="lani"))
    office = _office()
    for actor in (staff, other_head, office):
        with pytest.raises(PermissionDenied):
            head_approve_report(actor=actor, report=report, note="")
        with pytest.raises(PermissionDenied):
            head_return_report(actor=actor, report=report, note="No")
    head_approve_report(actor=head, report=report, note="")
    for actor in (staff, other_head, office):
        with pytest.raises(PermissionDenied):
            send_report_to_office(actor=actor, report=report)
    report.refresh_from_db()
    assert report.status == Report.Status.APPROVED


@pytest.mark.django_db
def test_stale_head_transitions_are_refused() -> None:
    program = _program()
    _writer, head, report = _with_head(program)
    with pytest.raises(ValidationError) as caught:
        send_report_to_office(actor=head, report=report)
    assert caught.value.messages == ["This report was already waiting for the head."]
    head_approve_report(actor=head, report=report, note="")
    with pytest.raises(ValidationError) as caught:
        head_approve_report(actor=head, report=report, note="")
    assert caught.value.messages == ["This report was already approved, not sent yet."]
    with pytest.raises(ValidationError) as caught:
        head_return_report(actor=head, report=report, note="Late")
    assert caught.value.messages == ["This report was already approved, not sent yet."]
    with pytest.raises(ValidationError) as caught:
        decide_report(actor=_office(), report=report, accept=True, note="")
    assert caught.value.messages == ["This report was already approved, not sent yet."]
    send_report_to_office(actor=head, report=report)
    with pytest.raises(ValidationError) as caught:
        head_approve_report(actor=head, report=report, note="")
    assert caught.value.messages == ["This report was already waiting for the office."]


@pytest.mark.django_db
def test_head_flow_keeps_free_text_out_of_audit_and_notifications() -> None:
    program = _program()
    staff, head, report = _with_head(program)
    _office()
    head_return_report(actor=head, report=report, note=NOTE)
    _resubmit(staff, report, DESCRIPTION)
    head_approve_report(actor=head, report=report, note=NOTE)
    send_report_to_office(actor=head, report=report)
    stored = [str(event.data) for event in AuditEvent.objects.all()]
    stored += [f"{row.title} {row.body} {row.url}" for row in Notification.objects.all()]
    assert len(stored) > 5
    for text in stored:
        for secret in (TITLE, DESCRIPTION, NOTE):
            assert secret not in text


@pytest.mark.django_db(transaction=True)
def test_concurrent_head_reviews_one_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    program = _program()
    _writer, head, report = _with_head(program)
    second = _head(program)
    outcomes = _race(
        monkeypatch,
        [
            lambda: head_approve_report(
                actor=head, report=Report.objects.get(pk=report.pk), note=""
            ),
            lambda: head_return_report(
                actor=second, report=Report.objects.get(pk=report.pk), note="No"
            ),
        ],
    )
    assert outcomes.count("done") == 1
    loser = next(outcome for outcome in outcomes if outcome != "done")
    assert loser in {
        "This report was already approved, not sent yet.",
        "This report was already returned.",
    }
    reviews = AuditEvent.objects.filter(action__in=["report.head_approved", "report.head_returned"])
    assert reviews.count() == 1
