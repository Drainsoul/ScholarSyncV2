"""Staff report screens (M11c)."""

from datetime import date
from typing import Any

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.files.tests.factories import StoredFileFactory
from apps.programs.models import Program
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.reports import services
from apps.reports.models import Report
from apps.reports.services import decide_report
from apps.reports.tests.factories import ReportFactory, ReportFileFactory, ready_report_file

pytestmark = pytest.mark.django_db


def _setup(client: Any, level: str = "staff") -> tuple[User, Program]:
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    user = MembershipFactory.create(program=program, level=level).user
    client.force_login(user)
    return user, program


def _url(name: str, program: Program, pk: int | None = None) -> str:
    kwargs: dict[str, object] = {"program": program.slug}
    if pk is not None:
        kwargs["pk"] = pk
    return reverse(f"reports:{name}", kwargs=kwargs)


def _form(file_id: object, **overrides: str) -> dict[str, object]:
    data: dict[str, object] = {
        "title": "Quarterly update",
        "period_start": "2026-08-01",
        "period_end": "2026-10-31",
        "description": "All on track.",
        "file": str(file_id),
    }
    data.update(overrides)
    return data


def test_send_report_round_trip(client: Any) -> None:
    user, program = _setup(client)
    MembershipFactory.create(program=program, level="head")
    assert client.get(_url("new", program)).status_code == 200
    file = ready_report_file(user)
    response = client.post(_url("new", program), _form(file.pk), follow=True)
    report = Report.objects.get()
    assert response.redirect_chain[-1][0] == _url("detail", program, report.pk)
    html = response.content.decode()
    assert "Report sent to the program head for review." in html
    assert "Waiting for the head" in html
    assert "This program has no head yet." not in html
    assert "Your review" not in html  # staff don't review
    assert report.files.get().file == file


def test_head_sends_report_straight_to_the_office(client: Any) -> None:
    user, program = _setup(client, level="head")
    response = client.post(_url("new", program), _form(ready_report_file(user).pk), follow=True)
    html = response.content.decode()
    assert "Report sent to the scholarship office." in html
    assert "Waiting for the office" in html
    assert Report.objects.get().status == Report.Status.SUBMITTED


def test_send_report_errors(client: Any) -> None:
    user, program = _setup(client)
    response = client.post(_url("new", program), _form("", period_end="2026-07-01"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Upload the report as a PDF." in html
    assert "The period must end on or after its start." in html
    assert not Report.objects.exists()


def test_document_file_cannot_be_used_as_report(client: Any) -> None:
    user, program = _setup(client)
    document = StoredFileFactory.create(
        uploaded_by=user, status="ready", sha256="0" * 64, sniffed_type="application/pdf"
    )
    response = client.post(_url("new", program), _form(document.pk))
    assert "Upload the report as a PDF." in response.content.decode()
    assert not Report.objects.exists()


def test_list_tabs_counts_and_query_count(client: Any, django_assert_max_num_queries: Any) -> None:
    user, program = _setup(client)
    ReportFactory.create_batch(30, program=program, submitted_by=user)
    ReportFactory.create_batch(15, program=program, submitted_by=user, status="returned")
    ReportFactory.create_batch(5, program=program, submitted_by=user, status="accepted")
    ReportFactory.create(title="Other program's", submitted_by=user)
    with django_assert_max_num_queries(16):
        response = client.get(_url("list", program))
    html = response.content.decode()
    assert "Other program" not in html
    assert html.count('href="/staff/tcu-ceaa/reports/') >= 25
    returned = client.get(_url("list", program) + "?tab=returned").content.decode()
    assert returned.count("Returned</") >= 15
    fallback = client.get(_url("list", program) + "?tab=nope&page=x")
    assert fallback.status_code == 200


def test_returned_detail_shows_note_and_resend_form(client: Any) -> None:
    user, program = _setup(client)
    report = ReportFactory.create(
        program=program,
        submitted_by=user,
        status="returned",
        review_note="Add the September <totals>",
        reviewed_by=UserFactory.create(role=User.Role.SUPER_ADMIN),
    )
    ReportFileFactory.create(report=report)
    html = client.get(_url("detail", program, report.pk)).content.decode()
    assert "Office note" in html
    assert "Add the September &lt;totals&gt;" in html
    assert "Fix and send again" in html
    assert "Leave empty to keep the current file." in html
    assert reverse("files:download", args=[report.files.get().file_id]) in html


def test_resubmit_post_flashes_and_rejects_when_not_returned(client: Any) -> None:
    user, program = _setup(client, level="head")
    office = UserFactory.create(role=User.Role.SUPER_ADMIN)
    report = services.submit_report(
        actor=user,
        program=program,
        title="Q3",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 10, 31),
        description="",
        file=ready_report_file(user),
    )
    response = client.post(_url("resubmit", program, report.pk), _form(""), follow=True)
    assert "This report is no longer returned." in response.content.decode()
    decide_report(actor=office, report=report, accept=False, note="Fix it")
    response = client.post(_url("resubmit", program, report.pk), _form(""), follow=True)
    assert "Report sent again." in response.content.decode()
    report.refresh_from_db()
    assert report.status == Report.Status.SUBMITTED


def test_other_programs_report_404(client: Any) -> None:
    _user, program = _setup(client)
    other = ReportFactory.create()
    assert client.get(_url("detail", program, other.pk)).status_code == 404
    assert client.post(_url("resubmit", program, other.pk), _form("")).status_code == 404


def test_staff_nav_counts_returned_reports(client: Any) -> None:
    user, program = _setup(client)
    ReportFactory.create_batch(2, program=program, submitted_by=user, status="returned")
    ReportFactory.create(program=program, submitted_by=user)
    html = client.get(reverse("workspace:dashboard", kwargs={"program": program.slug})).content
    text = html.decode()
    start = text.index(f'href="{_url("list", program)}"')
    assert '<span class="count count--accent">2</span>' in text[start : start + 400]


def test_notification_urls_match_routes() -> None:
    report = ReportFactory.create()
    assert services.staff_url(report) == reverse(
        "reports:detail", kwargs={"program": report.program.slug, "pk": report.pk}
    )


def test_crlf_text_that_fits_the_box_is_accepted(client: Any) -> None:
    user, program = _setup(client)
    file = ready_report_file(user)
    text = ("a" * 99 + "\r\n") * 20  # 2,000 characters in the box; 2,020 with CRLF
    response = client.post(_url("new", program), _form(file.pk, description=text))
    assert response.status_code == 302
    assert Report.objects.get().description == text.replace("\r\n", "\n").strip()
    too_long = client.post(
        _url("new", program), _form(ready_report_file(user).pk, description="b" * 2001)
    )
    assert "at most 2,000 characters" in too_long.content.decode()


def test_office_note_crlf_fits(client: Any) -> None:
    office = UserFactory.create(role=User.Role.SUPER_ADMIN)
    client.force_login(office)
    report = ReportFactory.create()
    note = ("n" * 99 + "\r\n") * 10  # 1,000 in the box; 1,010 with CRLF
    response = client.post(
        reverse("office:report-decide", args=[report.pk]), {"decision": "return", "note": note}
    )
    assert response.status_code == 302
    report.refresh_from_db()
    assert report.status == "returned"


# The head reviews a staff member's report first (rev 33).


def _waiting(program: Program, writer: User | None = None) -> Report:
    report = ReportFactory.create(
        program=program,
        status=Report.Status.WITH_HEAD,
        **({"submitted_by": writer} if writer is not None else {}),
    )
    ReportFileFactory.create(report=report)
    return report


def test_head_sees_review_form_and_approves_then_sends(client: Any) -> None:
    head, program = _setup(client, level="head")
    writer = MembershipFactory.create(program=program, user__full_name="Ana Cruz").user
    report = _waiting(program, writer)
    html = client.get(_url("detail", program, report.pk)).content.decode()
    assert "Your review" in html and "Waiting for the head" in html
    assert _url("approve", program, report.pk) in html
    assert _url("return", program, report.pk) in html
    assert "This program has no head yet." not in html
    response = client.post(_url("approve", program, report.pk), {"note": ""}, follow=True)
    html = response.content.decode()
    assert "Report approved. Send it to the scholarship office next." in html
    assert "Approved, not sent yet" in html
    assert "Your review" not in html
    assert "Send to the scholarship office" in html
    response = client.post(_url("send", program, report.pk), follow=True)
    html = response.content.decode()
    assert "Report sent to the scholarship office." in html
    assert "Waiting for the office" in html
    report.refresh_from_db()
    assert (report.status, report.sent_by) == (Report.Status.SUBMITTED, head)


def test_head_return_needs_a_note(client: Any) -> None:
    _head, program = _setup(client, level="head")
    writer = MembershipFactory.create(program=program, user__full_name="Ana Cruz").user
    report = _waiting(program, writer)
    response = client.post(_url("return", program, report.pk), {"note": "  "})
    assert response.status_code == 200
    assert "Say what the program should change." in response.content.decode()
    report.refresh_from_db()
    assert report.status == Report.Status.WITH_HEAD
    response = client.post(
        _url("return", program, report.pk), {"note": "Add <totals>"}, follow=True
    )
    html = response.content.decode()
    assert "Report returned to Ana Cruz." in html
    assert "Note from the head" in html and "Add &lt;totals&gt;" in html
    # The head can fix it too: the resend form shows on a returned report.
    assert "Fix and send again" in html


def test_writer_sees_head_note_and_resends_to_the_head(client: Any) -> None:
    writer, program = _setup(client)
    head = MembershipFactory.create(program=program, level="head").user
    report = _waiting(program, writer)
    services.head_return_report(actor=head, report=report, note="Add totals")
    html = client.get(_url("detail", program, report.pk)).content.decode()
    assert "Note from the head" in html and "Office note" not in html
    response = client.post(_url("resubmit", program, report.pk), _form(""), follow=True)
    assert "Report sent again." in response.content.decode()
    report.refresh_from_db()
    assert report.status == Report.Status.WITH_HEAD


def test_stale_head_action_flashes_already(client: Any) -> None:
    _head, program = _setup(client, level="head")
    report = _waiting(program)
    client.post(_url("approve", program, report.pk), {"note": ""})
    response = client.post(_url("approve", program, report.pk), {"note": ""}, follow=True)
    assert "This report was already approved, not sent yet." in response.content.decode()
    response = client.post(_url("return", program, report.pk), {"note": "x"}, follow=True)
    assert "This report was already approved, not sent yet." in response.content.decode()
    submitted = ReportFactory.create(program=program)
    response = client.post(_url("send", program, submitted.pk), follow=True)
    assert "This report was already waiting for the office." in response.content.decode()


def test_staff_cannot_review_or_send(client: Any) -> None:
    _staff, program = _setup(client)
    MembershipFactory.create(program=program, level="head")
    report = _waiting(program)
    html = client.get(_url("detail", program, report.pk)).content.decode()
    assert "Your review" not in html and "/approve/" not in html
    for name in ("approve", "return", "send"):
        assert client.post(_url(name, program, report.pk), {"note": "x"}).status_code == 403
    report.refresh_from_db()
    assert report.status == Report.Status.WITH_HEAD


def test_office_cannot_review_or_send(client: Any) -> None:
    program = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    client.force_login(UserFactory.create(role=User.Role.SUPER_ADMIN))
    report = _waiting(program)
    html = client.get(_url("detail", program, report.pk)).content.decode()
    assert "Your review" not in html
    for name in ("approve", "return"):
        assert client.post(_url(name, program, report.pk), {"note": "x"}).status_code == 403
    approved = ReportFactory.create(program=program, status=Report.Status.APPROVED)
    html = client.get(_url("detail", program, approved.pk)).content.decode()
    assert "Send to the scholarship office" not in html
    assert client.post(_url("send", program, approved.pk)).status_code == 403
    report.refresh_from_db()
    approved.refresh_from_db()
    assert (report.status, approved.status) == ("with_head", "approved")


def test_other_programs_head_gets_404_on_this_programs_report(client: Any) -> None:
    _head, program = _setup(client, level="head")
    other = _waiting(ProgramFactory.create(slug="lani"))
    for name in ("approve", "return", "send"):
        assert client.post(_url(name, program, other.pk), {"note": "x"}).status_code == 404
    other.refresh_from_db()
    assert other.status == Report.Status.WITH_HEAD


def test_no_head_note_on_a_waiting_report(client: Any) -> None:
    writer, program = _setup(client)
    report = _waiting(program, writer)
    html = client.get(_url("detail", program, report.pk)).content.decode()
    assert "This program has no head yet. Ask the scholarship office to add one." in html


def test_head_nav_counts_reports_waiting_for_them(client: Any) -> None:
    _head, program = _setup(client, level="head")
    _waiting(program)
    ReportFactory.create(program=program, status=Report.Status.APPROVED)
    ReportFactory.create(program=program, status=Report.Status.RETURNED)
    ReportFactory.create(program=program)
    text = client.get(reverse("workspace:dashboard", kwargs={"program": program.slug}))
    html = text.content.decode()
    start = html.index(f'href="{_url("list", program)}"')
    assert '<span class="count count--accent">3</span>' in html[start : start + 400]


def test_list_has_head_tabs(client: Any) -> None:
    _head, program = _setup(client, level="head")
    _waiting(program)
    ReportFactory.create(program=program, title="Approved one", status=Report.Status.APPROVED)
    html = client.get(_url("list", program) + "?tab=with_head").content.decode()
    assert "With the head" in html and "Approved one" not in html
    html = client.get(_url("list", program) + "?tab=approved").content.decode()
    assert "Approved one" in html and "Approved, not sent yet" in html


def test_head_detail_query_count(client: Any, django_assert_max_num_queries: Any) -> None:
    _head, program = _setup(client, level="head")
    report = _waiting(program)
    with django_assert_max_num_queries(16):
        assert client.get(_url("detail", program, report.pk)).status_code == 200
