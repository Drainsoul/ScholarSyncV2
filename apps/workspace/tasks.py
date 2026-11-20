"""Personal to-dos of program staff (a program) and of the office (no program): reads and writes.
Only the owner ever reaches a task."""

from datetime import date

from django.db import transaction
from django.db.models import BooleanField, Case, F, Q, QuerySet, Value, When
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.models import User
from apps.core.audit import record
from apps.programs.models import Program

from .models import Task


def _own(user: User, program: Program | None) -> QuerySet[Task]:
    return Task.objects.filter(owner=user, program=program)


def open_tasks(user: User, program: Program | None, *, today: date) -> QuerySet[Task]:
    """Open tasks: overdue first, then by due date, undated last."""
    return (
        _own(user, program)
        .filter(done_at=None)
        .annotate(
            overdue=Case(
                When(due_on__lt=today, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )
        .order_by(F("due_on").asc(nulls_last=True), "pk")
    )


def done_tasks(user: User, program: Program | None) -> QuerySet[Task]:
    return _own(user, program).exclude(done_at=None).order_by("-done_at", "-pk")


def own_task(user: User, program: Program | None, pk: int) -> Task:
    return get_object_or_404(_own(user, program), pk=pk)


def due_count(user: User, program: Program | None, *, today: date) -> int:
    return _own(user, program).filter(Q(done_at=None) & Q(due_on__lte=today)).count()


def task_status(task: Task, today: date) -> tuple[str, str] | None:
    if task.done_at is not None:
        return ("success", "Done")
    if task.due_on is None:
        return None
    if task.due_on < today:
        return ("danger", "Overdue")
    if task.due_on == today:
        return ("warning", "Due today")
    return None


def _audit(actor: User, task: Task, action: str, request: HttpRequest | None) -> None:
    record(actor=actor, action=action, target=task, program=task.program, request=request)


@transaction.atomic
def create_task(
    *,
    actor: User,
    program: Program | None,
    title: str,
    notes: str,
    due_on: date | None,
    request: HttpRequest | None = None,
) -> Task:
    task = Task.objects.create(
        owner=actor, program=program, title=title, notes=notes, due_on=due_on
    )
    _audit(actor, task, "task.created", request)
    return task


@transaction.atomic
def update_task(
    *,
    actor: User,
    task: Task,
    title: str,
    notes: str,
    due_on: date | None,
    request: HttpRequest | None = None,
) -> Task:
    task.title, task.notes, task.due_on = title, notes, due_on
    task.save(update_fields=["title", "notes", "due_on", "updated_at"])
    _audit(actor, task, "task.updated", request)
    return task


@transaction.atomic
def set_done(*, actor: User, task: Task, done: bool, request: HttpRequest | None = None) -> Task:
    """Complete or reopen a task; asking for the state it is already in changes nothing."""
    if (task.done_at is not None) == done:
        return task
    task.done_at = timezone.now() if done else None
    task.save(update_fields=["done_at", "updated_at"])
    _audit(actor, task, "task.completed" if done else "task.reopened", request)
    return task


@transaction.atomic
def delete_task(*, actor: User, task: Task, request: HttpRequest | None = None) -> None:
    _audit(actor, task, "task.deleted", request)
    task.delete()
