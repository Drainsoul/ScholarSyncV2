from typing import Any

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.accounts.models import User
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context

from . import tasks
from .forms import TaskForm
from .models import Task

PAGE_SIZE = 25
TABS = {"open": "Open", "done": "Done"}


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


class TaskListView(ProgramStaffRequiredMixin, View):
    """The owner's open or done tasks, with the add form on top."""

    template_name = "workspace/tasks/list.html"

    def _render(self, request: HttpRequest, form: TaskForm) -> HttpResponse:
        user, today = _actor(request), timezone.localdate()
        tab = request.GET.get("tab", "open")
        if tab not in TABS:
            tab = "open"
        open_rows = tasks.open_tasks(user, self.program, today=today)
        done_rows = tasks.done_tasks(user, self.program)
        rows = open_rows if tab == "open" else done_rows
        page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))
        base = reverse("workspace:tasks", kwargs={"program": self.program.slug})
        counts = {"open": open_rows.count(), "done": done_rows.count()}
        context = {
            **shell_context(request, area="staff", program=self.program),
            "form": form,
            "page": page,
            "tab": tab,
            "rows": [(task, tasks.task_status(task, today)) for task in page.object_list],
            "tabs": [
                {
                    "label": label,
                    "url": base if key == "open" else f"{base}?tab={key}",
                    "current": key == tab,
                    "count": counts[key],
                }
                for key, label in TABS.items()
            ],
        }
        return render(request, self.template_name, context)

    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        return self._render(request, TaskForm())

    def post(self, request: HttpRequest, program: str) -> HttpResponse:
        form = TaskForm(request.POST)
        if not form.is_valid():
            return self._render(request, form)
        tasks.create_task(actor=_actor(request), program=self.program, **form.cleaned_data)
        messages.success(request, "Task added.")
        return redirect("workspace:tasks", program=self.program.slug)


class TaskEditView(ProgramStaffRequiredMixin, View):
    template_name = "workspace/tasks/edit.html"

    def _render(self, request: HttpRequest, task: Task, form: TaskForm) -> HttpResponse:
        context: dict[str, Any] = {
            **shell_context(request, area="staff", program=self.program),
            "task": task,
            "form": form,
            "status": tasks.task_status(task, timezone.localdate()),
        }
        return render(request, self.template_name, context)

    def get(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        task = tasks.own_task(_actor(request), self.program, pk)
        initial = {"title": task.title, "due_on": task.due_on, "notes": task.notes}
        return self._render(request, task, TaskForm(initial=initial))

    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        task = tasks.own_task(_actor(request), self.program, pk)
        form = TaskForm(request.POST)
        if not form.is_valid():
            return self._render(request, task, form)
        tasks.update_task(actor=_actor(request), task=task, **form.cleaned_data)
        messages.success(request, "Task saved.")
        return redirect("workspace:tasks", program=self.program.slug)


class TaskDoneView(ProgramStaffRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        task = tasks.own_task(_actor(request), self.program, pk)
        done = request.POST.get("done") == "1"
        tasks.set_done(actor=_actor(request), task=task, done=done)
        messages.success(request, "Task done." if done else "Task reopened.")
        tab = "?tab=done" if not done else ""
        return redirect(reverse("workspace:tasks", kwargs={"program": self.program.slug}) + tab)


class TaskDeleteView(ProgramStaffRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        task = tasks.own_task(_actor(request), self.program, pk)
        tasks.delete_task(actor=_actor(request), task=task)
        messages.success(request, "Task deleted.")
        return redirect("workspace:tasks", program=self.program.slug)
