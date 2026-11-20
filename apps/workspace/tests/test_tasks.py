from datetime import date, datetime, timedelta
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.models import Program, ProgramMembership
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.workspace import tasks
from apps.workspace.models import Task
from apps.workspace.tests.factories import TaskFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 17)
NOON = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.get_default_timezone())


@pytest.fixture
def now(time_machine: Any) -> datetime:
    time_machine.move_to(NOON)
    return NOON


def _staff(program: Program, level: str = ProgramMembership.Level.STAFF) -> User:
    return MembershipFactory.create(program=program, level=level).user


def _url(name: str, program: Program, task: Task | None = None) -> str:
    kwargs: dict[str, object] = {"program": program.slug}
    if task is not None:
        kwargs["pk"] = task.pk
    return reverse(f"workspace:{name}", kwargs=kwargs)


def _titles(html: str, *titles: str) -> list[int]:
    return [html.index(title) for title in titles]


def test_open_tab_orders_overdue_then_due_then_undated(client: Any, now: datetime) -> None:
    program = ProgramFactory.create()
    user = _staff(program)
    TaskFactory.create(owner=user, program=program, title="Undated", due_on=None)
    TaskFactory.create(owner=user, program=program, title="Next week", due_on=TODAY + timedelta(7))
    TaskFactory.create(owner=user, program=program, title="Yesterday", due_on=TODAY - timedelta(1))
    TaskFactory.create(owner=user, program=program, title="Today", due_on=TODAY)
    TaskFactory.create(owner=user, program=program, title="Finished", done_at=now)
    client.force_login(user)
    html = client.get(_url("tasks", program)).content.decode()
    positions = _titles(html, "Yesterday", "Today", "Next week", "Undated")
    assert positions == sorted(positions)
    assert "Finished" not in html
    assert "Overdue" in html and "Due today" in html


def test_done_tab_newest_first(client: Any, now: datetime) -> None:
    program = ProgramFactory.create()
    user = _staff(program)
    TaskFactory.create(owner=user, program=program, title="Older", done_at=now - timedelta(2))
    TaskFactory.create(owner=user, program=program, title="Newer", done_at=now - timedelta(1))
    TaskFactory.create(owner=user, program=program, title="Still open")
    client.force_login(user)
    html = client.get(_url("tasks", program) + "?tab=done").content.decode()
    newer, older = _titles(html, "Newer", "Older")
    assert newer < older
    assert "Still open" not in html


def test_list_page_has_no_form_only_an_add_button(client: Any, now: datetime) -> None:
    program = ProgramFactory.create()
    client.force_login(_staff(program))
    html = client.get(_url("tasks", program)).content.decode()
    assert 'name="title"' not in html
    new_url = _url("task-new", program)
    assert f'href="{new_url}" hx-get="{new_url}" hx-target="#app-dialog-body"' in html
    assert client.post(_url("tasks", program), {"title": "x"}).status_code == 405


def test_add_task(client: Any, now: datetime) -> None:
    program = ProgramFactory.create()
    user = _staff(program)
    client.force_login(user)
    response = client.post(
        _url("task-new", program),
        {"title": "Call TCU registrar", "due_on": "2026-11-20", "notes": "About the slip"},
    )
    assert response.status_code == 302 and response["Location"] == _url("tasks", program)
    task = Task.objects.get()
    assert (task.owner, task.program, task.due_on) == (user, program, date(2026, 11, 20))
    event = AuditEvent.objects.get(action="task.created")
    assert event.program == program and event.target_id == str(task.pk)
    assert "Call TCU" not in str(event.data)


def test_blank_title_and_long_notes_rejected(client: Any, now: datetime) -> None:
    program = ProgramFactory.create()
    client.force_login(_staff(program))
    response = client.post(_url("task-new", program), {"title": "  ", "notes": "x"})
    assert response.status_code == 200
    response = client.post(_url("task-new", program), {"title": "Ok", "notes": "x" * 2001})
    assert response.status_code == 200
    assert not Task.objects.exists()
    assert not AuditEvent.objects.exclude(action="user.signed_in").exists()


def test_add_task_in_the_dialog(client: Any, now: datetime) -> None:
    program = ProgramFactory.create()
    client.force_login(_staff(program))
    url = _url("task-new", program)
    form = client.get(url, headers={"HX-Request": "true"}).content.decode()
    assert 'id="app-dialog-title"' in form and "<html" not in form
    assert f'hx-post="{url}"' in form
    invalid = client.post(url, {"title": ""}, headers={"HX-Request": "true"})
    assert invalid.status_code == 200 and 'id="app-dialog-title"' in invalid.content.decode()
    saved = client.post(url, {"title": "Print the claim list"}, headers={"HX-Request": "true"})
    assert saved.status_code == 204 and saved["HX-Refresh"] == "true"
    assert "closeDialog" in saved["HX-Trigger"]
    assert Task.objects.get().title == "Print the claim list"


def test_add_task_due_date_from_the_query(client: Any, now: datetime) -> None:
    program = ProgramFactory.create()
    client.force_login(_staff(program))
    url = _url("task-new", program)
    assert 'value="2026-12-01"' in client.get(url + "?due=2026-12-01").content.decode()
    assert (
        'value="'
        not in client.get(url + "?due=2026-13-45")
        .content.decode()
        .split('name="due_on"')[1]
        .split(">")[0]
    )


def test_add_task_from_the_dashboard_goes_back_there(client: Any, now: datetime) -> None:
    program = ProgramFactory.create()
    client.force_login(_staff(program))
    response = client.post(_url("task-new", program) + "?from=dashboard", {"title": "Call"})
    assert response["Location"] == _url("dashboard", program)


def test_edit_done_reopen_delete_round_trip(client: Any, now: datetime) -> None:
    program = ProgramFactory.create()
    user = _staff(program)
    task = TaskFactory.create(owner=user, program=program, title="Old")
    client.force_login(user)
    response = client.post(_url("task-edit", program, task), {"title": "New", "notes": ""})
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.title == "New"
    client.post(_url("task-done", program, task), {"done": "1"})
    client.post(_url("task-done", program, task), {"done": "1"})
    assert Task.objects.get(pk=task.pk).done_at is not None
    client.post(_url("task-done", program, task), {"done": "0"})
    assert Task.objects.get(pk=task.pk).done_at is None
    client.post(_url("task-delete", program, task))
    assert not Task.objects.exists()
    actions = list(
        AuditEvent.objects.exclude(action="user.signed_in")
        .order_by("pk")
        .values_list("action", flat=True)
    )
    assert actions == [
        "task.updated",
        "task.completed",
        "task.reopened",
        "task.deleted",
    ]


@pytest.mark.parametrize("who", ["head", "office"])
def test_another_users_task_is_404_for_head_and_office(
    client: Any, now: datetime, who: str
) -> None:
    program = ProgramFactory.create()
    task = TaskFactory.create(owner=_staff(program), program=program, title="Mine")
    if who == "head":
        viewer = _staff(program, ProgramMembership.Level.HEAD)
    else:
        viewer = UserFactory.create(role=User.Role.SUPER_ADMIN)
    client.force_login(viewer)
    assert client.get(_url("task-edit", program, task)).status_code == 404
    assert client.post(_url("task-edit", program, task), {"title": "x"}).status_code == 404
    assert client.post(_url("task-done", program, task), {"done": "1"}).status_code == 404
    assert client.post(_url("task-delete", program, task)).status_code == 404
    task.refresh_from_db()
    assert (task.title, task.done_at) == ("Mine", None)
    assert not AuditEvent.objects.exclude(action="user.signed_in").exists()
    assert "Mine" not in client.get(_url("tasks", program)).content.decode()


def test_task_in_another_program_is_404(client: Any, now: datetime) -> None:
    first, second = ProgramFactory.create_batch(2)
    user = _staff(first)
    MembershipFactory.create(program=second, user=user)
    task = TaskFactory.create(owner=user, program=first)
    client.force_login(user)
    assert client.get(_url("task-edit", second, task)).status_code == 404


def test_nav_count_is_tasks_due_today_or_earlier(client: Any, now: datetime) -> None:
    program = ProgramFactory.create()
    user = _staff(program)
    TaskFactory.create(owner=user, program=program, due_on=TODAY - timedelta(1))
    TaskFactory.create(owner=user, program=program, due_on=TODAY)
    TaskFactory.create(owner=user, program=program, due_on=TODAY + timedelta(1))
    TaskFactory.create(owner=user, program=program, due_on=TODAY, done_at=now)
    TaskFactory.create(program=program, due_on=TODAY)  # someone else's
    assert tasks.due_count(user, program, today=TODAY) == 2
    client.force_login(user)
    response = client.get(_url("tasks", program))
    tasks_item = next(item for item in response.context["nav_items"] if item["label"] == "Tasks")
    assert tasks_item["count"] == 2
    assert tasks_item["current"] is True


def test_task_status() -> None:
    task = Task(due_on=TODAY - timedelta(1))
    assert tasks.task_status(task, TODAY) == ("danger", "Overdue")
    task.due_on = TODAY
    assert tasks.task_status(task, TODAY) == ("warning", "Due today")
    task.due_on = None
    assert tasks.task_status(task, TODAY) is None
    task.done_at = NOON
    assert tasks.task_status(task, TODAY) == ("success", "Done")


def test_tasks_page_query_count(
    client: Any, now: datetime, django_assert_max_num_queries: Any
) -> None:
    program = ProgramFactory.create()
    user = _staff(program)
    TaskFactory.create_batch(50, owner=user, program=program)
    client.force_login(user)
    with django_assert_max_num_queries(16):
        assert client.get(_url("tasks", program)).status_code == 200


def test_task_and_support_events_have_ip_hash(client) -> None:
    from apps.accounts.models import User as _User
    from apps.accounts.tests.factories import UserFactory as _Users
    from apps.core.models import AuditEvent as _Events
    from apps.programs.tests.factories import MembershipFactory as _Members
    from apps.programs.tests.factories import ProgramFactory as _Programs

    program = _Programs.create(slug="tcu-ceaa")
    staff = _Members.create(program=program).user
    client.force_login(staff)
    client.post("/staff/tcu-ceaa/tasks/new/", {"title": "Call the school"})
    task_event = _Events.objects.get(action="task.created")
    assert task_event.ip_hash
    student = _Users.create(verified=True)
    client.force_login(student)
    client.post("/me/support/", {"topic": "account", "program": "", "message": "Hello"})
    office = _Users.create(role=_User.Role.SUPER_ADMIN)
    client.force_login(office)
    from apps.workspace.models import SupportRequest

    row = SupportRequest.objects.get()
    client.post(f"/office/support/{row.pk}/answer/")
    assert _Events.objects.get(action="support.sent").ip_hash
    assert _Events.objects.get(action="support.answered").ip_hash
