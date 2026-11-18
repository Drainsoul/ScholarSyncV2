"""Report services: send, resend, decide (M11c)."""

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
from apps.reports.services import decide_report, period_label, resubmit_report, submit_report
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
def test_submit_creates_report_file_audit_and_office_notifications() -> None:
    program = _program()
    staff = _staff(program)
    first, second = _office(), _office()
    UserFactory.create(role=User.Role.SUPER_ADMIN, is_active=False)
    report = _send(staff, program)
    assert report.status == Report.Status.SUBMITTED
    assert report.submitted_by == staff and report.submitted_at is not None
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
    staff = _staff(program)
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
    staff = _staff(program)
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
    staff = _staff(program)
    report = _send(staff, program)
    head = MembershipFactory.create(program=program, level="head").user
    with pytest.raises(PermissionDenied):
        decide_report(actor=head, report=report, accept=True, note="")


@pytest.mark.django_db
def test_resubmit_by_colleague_adds_version_and_moves_submitted_by() -> None:
    program = _program()
    first = _staff(program)
    colleague = _staff(program)
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
    staff = _staff(program)
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
    staff = _staff(program)
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
    staff = _staff(program)
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
    staff = _staff(program)
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
