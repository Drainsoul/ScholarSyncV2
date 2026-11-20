"""The office's own tasks and its overview calendar (spec §12 rev 27)."""

from datetime import date, datetime
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.money.tests.factories import ScheduleFactory
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.workspace.calendar import office_calendar
from apps.workspace.models import Task
from apps.workspace.tests.factories import TaskFactory

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=TZ)
TODAY = NOW.date()
NOVEMBER = date(2026, 11, 1)


@pytest.fixture(autouse=True)
def _frozen(time_machine: Any) -> None:
    time_machine.move_to(NOW)


def _office() -> User:
    return UserFactory.create(role=User.Role.SUPER_ADMIN, full_name="Jessica Cruz")


def test_office_task_round_trip(client: Any) -> None:
    office = _office()
    client.force_login(office)
    new = reverse("office:task-new")
    saved = client.post(new, {"title": "Sign the budget memo", "due_on": "2026-11-20"})
    assert saved.status_code == 302 and saved["Location"] == reverse("office:tasks")
    task = Task.objects.get()
    assert (task.owner, task.program) == (office, None)
    assert AuditEvent.objects.get(action="task.created").program is None
    page = client.get(reverse("office:tasks")).content.decode()
    assert "Sign the budget memo" in page and "Your own to-dos for the scholarship office." in page
    edit = reverse("office:task-edit", kwargs={"pk": task.pk})
    assert f'href="{edit}"' in page
    client.post(reverse("office:task-done", kwargs={"pk": task.pk}), {"done": "1"})
    task.refresh_from_db()
    assert task.done_at is not None
    client.post(reverse("office:task-delete", kwargs={"pk": task.pk}))
    assert not Task.objects.exists()


def test_office_and_staff_tasks_stay_apart(client: Any) -> None:
    office = _office()
    program = ProgramFactory.create(slug="tcu-ceaa")
    TaskFactory.create(owner=office, program=program, title="A program task")
    other_office = TaskFactory.create(owner=_office(), program=None, title="Someone else's")
    client.force_login(office)
    page = client.get(reverse("office:tasks")).content.decode()
    assert "A program task" not in page and "Someone else's" not in page
    url = reverse("office:task-edit", kwargs={"pk": other_office.pk})
    assert client.get(url).status_code == 404
    staff = MembershipFactory.create(program=program).user
    mine = TaskFactory.create(owner=staff, program=None, title="Office-less")
    client.force_login(staff)
    url = reverse("workspace:task-edit", kwargs={"program": "tcu-ceaa", "pk": mine.pk})
    assert client.get(url).status_code == 404


def test_office_nav_counts_due_tasks(client: Any) -> None:
    office = _office()
    TaskFactory.create(owner=office, program=None, due_on=TODAY)
    TaskFactory.create(owner=office, program=None, due_on=date(2026, 12, 1))
    client.force_login(office)
    nav = client.get(reverse("office:home")).context["nav_items"]
    assert next(item for item in nav if item["label"] == "Tasks")["count"] == 1


def test_office_calendar_names_each_program() -> None:
    office = _office()
    lani = ProgramFactory.create(name="LANI", applications_close_on=date(2026, 11, 28))
    ceaa = ProgramFactory.create(name="TCU CEAA")
    ProgramFactory.create(name="Closed", is_active=False, applications_open_on=date(2026, 11, 5))
    ScheduleFactory.create(program=ceaa, distribution_date=date(2026, 11, 10), is_published=False)
    task = TaskFactory.create(owner=office, program=None, title="Memo", due_on=date(2026, 11, 20))
    TaskFactory.create(owner=office, program=lani, title="Program task", due_on=date(2026, 11, 21))
    shown = office_calendar(office, today=TODAY, month=NOVEMBER)
    events = {
        cell.day.day: [(e.kind, e.title) for e in cell.events]
        for week in shown.weeks
        for cell in week
        if cell.events and cell.in_month
    }
    assert events == {
        10: [("release", "TCU CEAA allowance release (draft)")],
        20: [("task", "Memo")],
        28: [("closes", "LANI applications close")],
    }
    memo = next(e for week in shown.weeks for c in week for e in c.events if e.kind == "task")
    assert memo.url == reverse("office:task-edit", kwargs={"pk": task.pk})


def test_overview_calendar_swap_and_overdue_row(client: Any) -> None:
    office = _office()
    TaskFactory.create(owner=office, program=None, title="Late memo", due_on=date(2026, 11, 3))
    client.force_login(office)
    url = reverse("office:home")
    html = client.get(url).content.decode()
    assert "1 of your tasks is overdue" in html
    new = reverse("office:task-new")
    assert f'href="{new}?due=2026-11-17&amp;from=dashboard"' in html
    swap = client.get(
        url + "?month=2026-12", headers={"HX-Request": "true", "HX-Target": "office-calendar"}
    )
    body = swap.content.decode()
    assert "<html" not in body and "December 2026" in body and "Needs attention" not in body
    assert "HX-Target" in swap["Vary"]
    cancel = client.post(new + "?from=dashboard", {"title": "Call TCU"})
    assert cancel["Location"] == url
