from datetime import date
from typing import Any

import pytest
from django.urls import reverse

from apps.core.models import AuditEvent
from apps.money.models import Disbursement, DistributionSchedule
from apps.money.tests.builders import payout, staff_of
from apps.money.tests.factories import ScheduleFactory
from apps.programs.models import Program
from apps.programs.tests.factories import AcademicTermFactory, ProgramFactory

pytestmark = pytest.mark.django_db


def _url(name: str, program: Program, **kwargs: Any) -> str:
    return reverse(f"money:{name}", kwargs={"program": program.slug, **kwargs})


def _signed_in(client: Any, program: Program) -> Any:
    client.force_login(staff_of(program))
    return client


def _form(term_pk: int, **overrides: str) -> dict[str, Any]:
    data = {
        "term": str(term_pk),
        "distribution_date": "2026-09-15",
        "claim_location": "TCU Gymnasium",
        "frequency_label": "Once a semester",
        "notes": "Bring a valid ID.",
    }
    data.update(overrides)
    return data


@pytest.fixture
def current() -> Any:
    return AcademicTermFactory.create(is_current=True)


def test_list_shows_schedules_with_counts(client: Any) -> None:
    row = payout(claim_location="TCU Gymnasium")
    payout(row.schedule, status=Disbursement.Status.RELEASED)
    ScheduleFactory.create(program=row.schedule.program, is_published=False)
    response = _signed_in(client, row.schedule.program).get(_url("schedules", row.schedule.program))
    html = response.content.decode()
    assert response.status_code == 200
    assert "TCU Gymnasium" in html
    assert str(row.schedule.term) in html
    assert "Published" in html and "Draft" in html
    assert "1 prepared" in html and "1 released" in html


def test_create_schedule(client: Any, current: Any) -> None:
    program = ProgramFactory.create(claim_location_default="City Hall")
    c = _signed_in(client, program)
    page = c.get(_url("schedule-new", program))
    assert 'value="City Hall"' in page.content.decode()
    response = c.post(_url("schedule-new", program), _form(current.pk))
    assert response.status_code == 302
    assert response.url == _url("schedules", program)
    schedule = DistributionSchedule.objects.get()
    assert (schedule.program, schedule.term, schedule.is_published) == (program, current, False)
    assert schedule.distribution_date == date(2026, 9, 15)
    assert AuditEvent.objects.filter(action="schedule.created").exists()
    assert "Schedule saved." in c.get(response.url).content.decode()


def test_edit_keeps_the_fields(client: Any, current: Any) -> None:
    schedule = ScheduleFactory.create(
        term=current,
        notes="Old note",
        claim_location="TCU Gymnasium",
        frequency_label="Once a semester",
    )
    c = _signed_in(client, schedule.program)
    assert (
        "Old note"
        in c.get(_url("schedule-edit", schedule.program, pk=schedule.pk)).content.decode()
    )
    c.post(
        _url("schedule-edit", schedule.program, pk=schedule.pk),
        _form(current.pk, notes="New note"),
    )
    schedule.refresh_from_db()
    assert schedule.notes == "New note"
    event = AuditEvent.objects.get(action="schedule.updated")
    assert event.data == {"fields": ["notes"]}


def test_frozen_schedule_refuses_date_and_term_change(client: Any) -> None:
    row = payout(status=Disbursement.Status.APPROVED)
    schedule = row.schedule
    c = _signed_in(client, schedule.program)
    url = _url("schedule-edit", schedule.program, pk=schedule.pk)
    response = c.post(url, _form(schedule.term_id, distribution_date="2026-10-01"))
    assert response.status_code == 400
    assert "This schedule has approved payouts, so its term and date are fixed." in (
        response.content.decode()
    )
    response = c.post(
        url, _form(schedule.term_id, distribution_date="2026-09-15", claim_location="New hall")
    )
    assert response.status_code == 302
    schedule.refresh_from_db()
    assert (schedule.claim_location, schedule.distribution_date) == ("New hall", date(2026, 9, 15))


def test_term_fixed_once_rows_exist(client: Any) -> None:
    row = payout()
    schedule = row.schedule
    other = AcademicTermFactory.create()
    response = _signed_in(client, schedule.program).post(
        _url("schedule-edit", schedule.program, pk=schedule.pk), _form(other.pk)
    )
    assert response.status_code == 400
    assert "This schedule has payouts, so its term is fixed." in response.content.decode()


def test_unpublish_with_approved_rows_is_refused(client: Any) -> None:
    row = payout(status=Disbursement.Status.APPROVED)
    schedule = row.schedule
    c = _signed_in(client, schedule.program)
    response = c.post(_url("schedule-publish", schedule.program, pk=schedule.pk), {"publish": "0"})
    assert response.status_code == 302
    schedule.refresh_from_db()
    assert schedule.is_published
    assert "This schedule has approved payouts, so it stays published." in (
        c.get(response.url).content.decode()
    )


def test_publish_and_unpublish(client: Any) -> None:
    schedule = ScheduleFactory.create(is_published=False)
    c = _signed_in(client, schedule.program)
    url = _url("schedule-publish", schedule.program, pk=schedule.pk)
    response = c.post(url, {"publish": "1"})
    schedule.refresh_from_db()
    assert schedule.is_published
    assert "Published. Scholars can see this schedule." in c.get(response.url).content.decode()
    c.post(url, {"publish": "0"})
    assert not DistributionSchedule.objects.get(pk=schedule.pk).is_published
    actions = list(
        AuditEvent.objects.filter(action__startswith="schedule.")
        .order_by("pk")
        .values_list("action", flat=True)
    )
    assert actions == ["schedule.published", "schedule.unpublished"]


def test_other_program_schedule_is_404(client: Any) -> None:
    schedule = ScheduleFactory.create()
    program = ProgramFactory.create()
    c = _signed_in(client, program)
    assert c.get(_url("schedule-edit", program, pk=schedule.pk)).status_code == 404
    assert (
        c.post(_url("schedule-publish", program, pk=schedule.pk), {"publish": "1"}).status_code
        == 404
    )


def test_nav_has_disbursements_after_scholars(client: Any) -> None:
    program = ProgramFactory.create()
    html = _signed_in(client, program).get(_url("schedules", program)).content.decode()
    scholars = html.index(">Scholars<")
    money = html.index(">Disbursements<")
    assert scholars < money < html.index(">Students<")
    assert 'aria-current="page"' in html[money - 400 : money]
    assert "Money sections" in html


def test_schedules_query_count(client: Any, django_assert_max_num_queries: Any) -> None:
    program = ProgramFactory.create()
    term = AcademicTermFactory.create()
    for _ in range(50):
        ScheduleFactory.create(program=program, term=term)
    c = _signed_in(client, program)
    with django_assert_max_num_queries(15):
        assert c.get(_url("schedules", program)).status_code == 200
