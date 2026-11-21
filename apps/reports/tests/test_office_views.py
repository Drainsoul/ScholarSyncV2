"""Office report review (M11c)."""

from datetime import timedelta
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.reports import services
from apps.reports.models import Report
from apps.reports.tests.factories import ReportFactory, ReportFileFactory
from apps.workspace.models import Notification

pytestmark = pytest.mark.django_db

LIST = "/office/reports/"


def _office(client: Any) -> User:
    user = UserFactory.create(role=User.Role.SUPER_ADMIN)
    client.force_login(user)
    return user


def _sent(days: int, **kwargs: Any) -> Report:
    return ReportFactory.create(submitted_at=timezone.now() - timedelta(days=days), **kwargs)


def test_office_list_defaults_to_review_oldest_first(client: Any) -> None:
    _office(client)
    _sent(1, title="Newer one")
    _sent(5, title="Older one")
    _sent(9, title="Done one", status="accepted")
    html = client.get(reverse("office:reports")).content.decode()
    assert html.index("Older one") < html.index("Newer one")
    assert "Done one" not in html
    everything = client.get(LIST + "?tab=all").content.decode()
    assert (
        everything.index("Newer one") < everything.index("Older one") < everything.index("Done one")
    )


def test_program_filter_and_bad_values_fall_back(client: Any) -> None:
    _office(client)
    tcu = ProgramFactory.create(name="TCU CEAA")
    lani = ProgramFactory.create(name="LANI")
    _sent(1, program=tcu, title="TCU report")
    _sent(1, program=lani, title="LANI report")
    html = client.get(LIST + f"?program={tcu.pk}").content.decode()
    assert "TCU report" in html and "LANI report" not in html
    html = client.get(LIST + "?program=abc&tab=nope&page=zz").content.decode()
    assert "TCU report" in html and "LANI report" in html


def test_list_query_count(client: Any, django_assert_max_num_queries: Any) -> None:
    _office(client)
    tcu, lani = ProgramFactory.create_batch(2)
    for n in range(50):
        _sent(n, program=tcu if n % 2 else lani)
    with django_assert_max_num_queries(16):
        assert client.get(reverse("office:reports")).status_code == 200


def test_accept_and_return_flash_and_notify(client: Any) -> None:
    _office(client)
    program = ProgramFactory.create(name="LANI")
    first = _sent(2, program=program)
    second = _sent(2, program=program)
    ReportFileFactory.create(report=first)
    detail = client.get(reverse("office:report-detail", args=[first.pk])).content.decode()
    assert "Save decision" in detail
    assert reverse("files:download", args=[first.files.get().file_id]) in detail
    response = client.post(
        reverse("office:report-decide", args=[first.pk]),
        {"decision": "accept", "note": ""},
        follow=True,
    )
    assert "Report accepted." in response.content.decode()
    response = client.post(
        reverse("office:report-decide", args=[second.pk]),
        {"decision": "return", "note": "Add the totals"},
        follow=True,
    )
    assert "Report returned to LANI." in response.content.decode()
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.status, second.status) == ("accepted", "returned")
    assert Notification.objects.filter(kind__in=["report_accepted", "report_returned"]).count() == 2


def test_return_without_note_is_a_form_error(client: Any) -> None:
    _office(client)
    report = _sent(1)
    response = client.post(
        reverse("office:report-decide", args=[report.pk]), {"decision": "return", "note": " "}
    )
    assert response.status_code == 200
    assert "Say what the program should change." in response.content.decode()
    report.refresh_from_db()
    assert report.status == "submitted"


def test_decide_on_accepted_shows_already_message(client: Any) -> None:
    _office(client)
    report = _sent(1, status="accepted")
    response = client.post(
        reverse("office:report-decide", args=[report.pk]),
        {"decision": "return", "note": "Late"},
        follow=True,
    )
    assert "This report was already accepted." in response.content.decode()
    detail = client.get(reverse("office:report-detail", args=[report.pk])).content.decode()
    assert "Save decision" not in detail


def test_staff_cannot_open_office_reports(client: Any) -> None:
    report = _sent(1)
    staff = MembershipFactory.create(program=report.program).user
    client.force_login(staff)
    assert client.get(reverse("office:report-detail", args=[report.pk])).status_code == 403


def test_office_nav_order(client: Any) -> None:
    _office(client)
    _sent(1)
    _sent(2)
    response = client.get(reverse("office:home"))
    nav = response.context["nav_items"]
    labels = [item["label"] for item in nav]
    assert labels[labels.index("Terms") + 1 : labels.index("Terms") + 2] == ["Reports"]
    assert labels[-1] == "Support"
    reports = nav[labels.index("Reports")]
    assert reports["count"] == 2
    assert reports["icon"] == "file-text"


def test_office_url_matches_route() -> None:
    report = ReportFactory.create()
    assert services.office_url(report) == reverse("office:report-detail", args=[report.pk])


def test_office_report_list_says_to_review(client: Any) -> None:
    _office(client)
    report = _sent(2, title="Quarterly")
    html = client.get(reverse("office:reports")).content.decode()
    assert "To review" in html and "Waiting for the office" not in html
    detail = client.get(reverse("office:report-detail", args=[report.pk])).content.decode()
    assert "To review" in detail
    staff_html = client.get(reverse("reports:list", kwargs={"program": report.program.slug}))
    assert "Send a report" not in staff_html.content.decode()


def test_report_tab_counts_come_from_a_selector(client: Any) -> None:
    from apps.reports.selectors import status_counts

    first = _sent(1)
    _sent(2, program=first.program, status="accepted")
    _sent(3)
    assert status_counts(first.program) == {"submitted": 1, "accepted": 1, "all": 2}
    assert status_counts(None)["all"] == 3
    _office(client)
    html = client.get(reverse("office:reports") + f"?program={first.program.pk}&tab=all")
    assert html.status_code == 200


def test_office_never_gets_a_send_form(client: Any) -> None:
    _office(client)
    report = _sent(3, status="returned", review_note="Fix it")
    slug = report.program.slug
    new = client.get(reverse("reports:new", kwargs={"program": slug}))
    assert new.status_code == 302 and new["Location"] == reverse(
        "reports:list", kwargs={"program": slug}
    )
    detail = client.get(reverse("reports:detail", kwargs={"program": slug, "pk": report.pk}))
    assert "Fix and send again" not in detail.content.decode()
    assert f"/reports/{report.pk}/resubmit/" not in detail.content.decode()


def test_office_sees_only_sent_reports(client: Any) -> None:
    """A staff report still with the head (or approved, not sent) never reaches the office."""
    office = _office(client)
    program = ProgramFactory.create(name="LANI")
    hidden = ReportFactory.create(program=program, title="With head", status="with_head")
    approved = ReportFactory.create(program=program, title="Approved one", status="approved")
    ReportFileFactory.create(report=hidden)
    _sent(1, program=program, title="Sent one")
    html = client.get(LIST + "?tab=all").content.decode()
    assert "Sent one" in html and "With head" not in html and "Approved one" not in html
    for report in (hidden, approved):
        assert client.get(reverse("office:report-detail", args=[report.pk])).status_code == 404
        decide = client.post(
            reverse("office:report-decide", args=[report.pk]), {"decision": "accept"}
        )
        assert decide.status_code == 404
    from apps.reports.selectors import staff_can_download_report, status_counts

    assert status_counts(None, office=True) == {"submitted": 1, "all": 1}
    assert status_counts(program)["all"] == 3
    assert not staff_can_download_report(office, hidden.files.get().file)
    nav = client.get(reverse("office:home")).context["nav_items"]
    assert next(item for item in nav if item["label"] == "Reports")["count"] == 1


def test_office_detail_names_writer_and_sender(client: Any) -> None:
    _office(client)
    writer = UserFactory.create(role=User.Role.STAFF, full_name="Ana Cruz")
    head = UserFactory.create(role=User.Role.STAFF, full_name="Ben Reyes")
    report = ReportFactory.create(
        submitted_by=writer, sent_by=head, review_note="All checked", reviewed_by=head
    )
    html = client.get(reverse("office:report-detail", args=[report.pk])).content.decode()
    assert "Written by" in html and "Ana Cruz" in html and "Ben Reyes" in html
    assert "Note from the head: All checked" in html
    assert "Returned earlier" not in html
