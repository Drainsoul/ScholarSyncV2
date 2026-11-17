from datetime import datetime
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD
from apps.awards.models import Award, ScholarTerm
from apps.awards.tests.factories import AwardFactory, ScholarTermFactory
from apps.money.models import Disbursement, DistributionSchedule
from apps.money.tests.builders import head_of, payout, staff_of
from apps.money.tests.factories import ScheduleFactory
from apps.programs.tests.factories import ProgramFactory
from apps.workspace.models import EmailOutbox

pytestmark = pytest.mark.django_db

APPROVED = Disbursement.Status.APPROVED
RELEASE_DAY = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.get_default_timezone())


def _url(name: str, schedule: DistributionSchedule, **kwargs: Any) -> str:
    return reverse(
        f"money:{name}",
        kwargs={"program": schedule.program.slug, "schedule": schedule.pk, **kwargs},
    )


def _as(client: Any, user: User) -> Any:
    client.force_login(user)
    return client


def _reauthenticated(client: Any, user: User) -> Any:
    """Signed in, then past the password page, so the next five minutes need no password."""
    assert client.login(email=user.email, password=DEFAULT_PASSWORD)
    response = client.post(reverse("account_reauthenticate"), {"password": DEFAULT_PASSWORD})
    assert response.status_code == 302
    return client


def _text(client: Any, url: str) -> str:
    return str(client.get(url).content.decode())


def test_overview_lists_schedules_with_totals(client: Any) -> None:
    row = payout()
    payout(row.schedule, status=APPROVED)
    program = row.schedule.program
    html = _text(_as(client, staff_of(program)), reverse("money:overview", args=[program.slug]))
    assert _url("schedule", row.schedule) in html
    assert str(row.schedule.term) in html
    assert "₱5,000.00" in html and "Published" in html


def test_schedule_page_rows_and_flags(client: Any) -> None:
    row = payout()
    held = payout(row.schedule, award_status=Award.Status.SUSPENDED)
    merit = payout(row.schedule)
    merit.merit = True
    merit.amount = merit.scholar_term.tier.merit_amount  # type: ignore[union-attr]
    merit.save()
    html = _text(_as(client, staff_of(row.schedule.program)), _url("schedule", row.schedule))
    assert row.scholar_term.award.profile.full_name in html
    assert "Prepared" in html
    assert "Merit" in html and "₱10,000.00" in html
    assert "Not eligible: This scholar's award is suspended." in html
    assert held.scholar_term.award.profile.full_name in html
    assert "Releasing needs a program head and asks for your password again." in html


def test_schedule_filters(client: Any) -> None:
    row = payout()
    other = payout(row.schedule, status=APPROVED)
    c = _as(client, staff_of(row.schedule.program))
    html = _text(c, _url("schedule", row.schedule) + "?status=approved")
    assert other.scholar_term.award.profile.full_name in html
    assert row.scholar_term.award.profile.full_name not in html
    name = row.scholar_term.award.profile.last_name
    html = _text(c, _url("schedule", row.schedule) + f"?q={name}&status=bogus")
    assert row.scholar_term.award.profile.full_name in html


def test_staff_see_generate_but_no_decisions(client: Any) -> None:
    row = payout()
    html = _text(_as(client, staff_of(row.schedule.program)), _url("schedule", row.schedule))
    assert "Generate disbursements" in html
    assert "Approve selected" not in html and "data-bulk-item" not in html
    client.logout()
    html = _text(_as(client, head_of(row.schedule.program)), _url("schedule", row.schedule))
    assert "Approve selected" in html and "Release selected" in html
    assert "Approve all prepared (1)" in html


def test_generate_reports(client: Any) -> None:
    schedule = ScheduleFactory.create()
    for compliance in (ScholarTerm.Compliance.INCOMPLETE, ScholarTerm.Compliance.COMPLETE):
        award = AwardFactory.create(source_application__program=schedule.program)
        ScholarTermFactory.create(award=award, term=schedule.term, compliance=compliance)
    c = _as(client, staff_of(schedule.program))
    response = c.post(_url("generate", schedule))
    assert response.url == _url("schedule", schedule)
    html = _text(c, response.url)
    assert "Generated 1 disbursement." in html
    assert "1 with documents not checked" in html


def test_bulk_approve_as_head(client: Any) -> None:
    row = payout()
    second = payout(row.schedule)
    held = payout(row.schedule, award_status=Award.Status.SUSPENDED)
    c = _as(client, head_of(row.schedule.program))
    response = c.post(
        _url("bulk", row.schedule),
        {"action": "approve", "ids": [row.pk, second.pk, held.pk]},
    )
    assert response.status_code == 302
    html = _text(c, response.url)
    assert "Approved 2 payouts." in html and "Skipped 1." in html
    name = held.scholar_term.award.profile.full_name
    assert f"{name}: This scholar&#x27;s award is suspended." in html


def test_bulk_as_staff_is_403(client: Any) -> None:
    row = payout()
    response = _as(client, staff_of(row.schedule.program)).post(
        _url("bulk", row.schedule), {"action": "approve", "ids": [row.pk]}
    )
    assert response.status_code == 403


def test_bulk_approve_needs_no_password(client: Any) -> None:
    row = payout()
    head = head_of(row.schedule.program)
    assert client.login(email=head.email, password=DEFAULT_PASSWORD)
    response = client.post(_url("bulk", row.schedule), {"action": "approve", "ids": [row.pk]})
    assert response.url == _url("schedule", row.schedule)
    row.refresh_from_db()
    assert row.status == APPROVED


def test_bulk_release_replays_after_password(client: Any, time_machine: Any) -> None:
    time_machine.move_to(RELEASE_DAY, tick=False)
    first = payout(status=APPROVED)
    rows = [first, payout(first.schedule, status=APPROVED), payout(first.schedule, status=APPROVED)]
    head = head_of(first.schedule.program)
    assert client.login(email=head.email, password=DEFAULT_PASSWORD)
    response = client.post(
        _url("bulk", first.schedule), {"action": "release", "ids": [row.pk for row in rows]}
    )
    assert response.status_code == 302
    assert response.url.startswith(reverse("account_reauthenticate"))
    response = client.post(response.url, {"password": DEFAULT_PASSWORD})
    assert response.status_code == 302
    assert response.url == _url("schedule", first.schedule)
    assert set(Disbursement.objects.values_list("status", flat=True)) == {"released"}
    assert EmailOutbox.objects.filter(kind="allowance_released").count() == 3


def test_all_buttons(client: Any) -> None:
    row = payout()
    payout(row.schedule)
    c = _as(client, head_of(row.schedule.program))
    c.post(_url("bulk", row.schedule), {"action": "approve_all"})
    assert Disbursement.objects.filter(status=APPROVED).count() == 2


def test_reject_page_and_post(client: Any) -> None:
    row = payout()
    c = _as(client, head_of(row.schedule.program))
    url = _url("reject", row.schedule, pk=row.pk)
    assert "Why isn&#x27;t this paid?" in _text(c, url)
    response = c.post(url, {"reason": ""})
    assert response.status_code == 400
    assert "Give a reason." in response.content.decode()
    response = c.post(url, {"reason": "Did not show up."})
    assert response.url == _url("schedule", row.schedule)
    name = row.scholar_term.award.profile.full_name
    assert f"Rejected the payout for {name}." in _text(c, response.url)
    row.refresh_from_db()
    assert row.status == Disbursement.Status.REJECTED


def test_revert_after_password(client: Any) -> None:
    row = payout(status=APPROVED)
    c = _reauthenticated(client, head_of(row.schedule.program))
    response = c.post(_url("revert", row.schedule, pk=row.pk))
    assert response.url == _url("schedule", row.schedule)
    assert "Moved back to Prepared." in _text(c, response.url)
    row.refresh_from_db()
    assert row.status == Disbursement.Status.PENDING


def test_revert_released_shows_the_error(client: Any) -> None:
    row = payout(status=Disbursement.Status.RELEASED)
    c = _reauthenticated(client, head_of(row.schedule.program))
    response = c.post(_url("revert", row.schedule, pk=row.pk))
    assert "Can&#x27;t change from Released to Prepared." in _text(c, response.url)


def test_revert_without_password_goes_to_the_password_page(client: Any) -> None:
    row = payout(status=APPROVED)
    head = head_of(row.schedule.program)
    assert client.login(email=head.email, password=DEFAULT_PASSWORD)
    response = client.post(_url("revert", row.schedule, pk=row.pk))
    assert response.url.startswith(reverse("account_reauthenticate"))


def test_other_schedule_row_is_404(client: Any) -> None:
    row = payout()
    other = ScheduleFactory.create(program=row.schedule.program)
    c = _reauthenticated(client, head_of(row.schedule.program))
    assert c.get(_url("reject", other, pk=row.pk)).status_code == 404
    assert c.post(_url("revert", other, pk=row.pk)).status_code == 404


def test_schedule_of_another_program_is_404(client: Any) -> None:
    row = payout()
    program = ProgramFactory.create()
    c = _as(client, staff_of(program))
    url = reverse("money:schedule", kwargs={"program": program.slug, "schedule": row.schedule_id})
    assert c.get(url).status_code == 404


def test_schedule_page_query_count(client: Any, django_assert_max_num_queries: Any) -> None:
    first = payout()
    for _ in range(49):
        payout(first.schedule)
    c = _as(client, head_of(first.schedule.program))
    with django_assert_max_num_queries(20):
        assert c.get(_url("schedule", first.schedule)).status_code == 200
