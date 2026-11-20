"""Task screens for program staff (`/staff/<slug>/tasks/`) and the office (`/office/tasks/`).

The views are shared; a scope mixin says whose tasks they are (a program, or none for the office),
which layout and shell they render in, and how to build their URLs."""

from datetime import date
from typing import Any

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views import View

from apps.accounts.models import User
from apps.core.htmx import HtmxHttpRequest, close_dialog
from apps.core.permissions import ProgramStaffRequiredMixin, SuperAdminRequiredMixin
from apps.core.shell import shell_context
from apps.programs.models import Program

from . import tasks
from .forms import TaskForm
from .models import Task

PAGE_SIZE = 25
TABS = {"open": "Open", "done": "Done"}


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


class TaskScope:
    """Whose tasks a view shows, where it renders and how it links (one subclass per area)."""

    layout = ""
    scope_label = ""

    @property
    def scope_program(self) -> Program | None:
        raise NotImplementedError

    def task_url(self, name: str, **kwargs: Any) -> str:
        raise NotImplementedError

    def dashboard_url(self) -> str:
        raise NotImplementedError

    def shell(self, request: HttpRequest) -> dict[str, Any]:
        raise NotImplementedError


class StaffTaskScope(ProgramStaffRequiredMixin, TaskScope):
    """A staff member's tasks in the program of the URL."""

    program: Program
    layout = "layouts/staff.html"

    @property
    def scope_program(self) -> Program | None:
        return self.program

    @property
    def scope_label(self) -> str:  # type: ignore[override]
        return self.program.name

    def task_url(self, name: str, **kwargs: Any) -> str:
        return reverse(f"workspace:{name}", kwargs={"program": self.program.slug, **kwargs})

    def dashboard_url(self) -> str:
        return reverse("workspace:dashboard", kwargs={"program": self.program.slug})

    def shell(self, request: HttpRequest) -> dict[str, Any]:
        return shell_context(request, area="staff", program=self.program)


class OfficeTaskScope(SuperAdminRequiredMixin, TaskScope):
    """The office's own tasks, with no program."""

    layout = "layouts/office.html"
    scope_label = "the scholarship office"

    @property
    def scope_program(self) -> Program | None:
        return None

    def task_url(self, name: str, **kwargs: Any) -> str:
        return reverse(f"office:{name}", kwargs=kwargs)

    def dashboard_url(self) -> str:
        return reverse("office:home")

    def shell(self, request: HttpRequest) -> dict[str, Any]:
        return shell_context(request, area="office")


class _TaskList(TaskScope, View):
    """The owner's open or done tasks. Add task opens the form (_TaskCreate) in a dialog."""

    template_name = "workspace/tasks/list.html"
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        user, today = _actor(request), timezone.localdate()
        tab = request.GET.get("tab", "open")
        if tab not in TABS:
            tab = "open"
        open_rows = tasks.open_tasks(user, self.scope_program, today=today)
        done_rows = tasks.done_tasks(user, self.scope_program)
        rows = open_rows if tab == "open" else done_rows
        page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))
        base = self.task_url("tasks")
        counts = {"open": open_rows.count(), "done": done_rows.count()}
        context = {
            **self.shell(request),
            "layout": self.layout,
            "scope_label": self.scope_label,
            "new_url": self.task_url("task-new"),
            "page": page,
            "tab": tab,
            "rows": [
                {
                    "task": task,
                    "status": tasks.task_status(task, today),
                    "edit_url": self.task_url("task-edit", pk=task.pk),
                    "done_url": self.task_url("task-done", pk=task.pk),
                }
                for task in page.object_list
            ],
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


def _due_from_query(value: str | None) -> date | None:
    """`?due=YYYY-MM-DD` (a calendar day's Add task link); anything else is no date."""
    try:
        return date.fromisoformat(value) if value and len(value) == 10 else None
    except ValueError:
        return None


class _TaskCreate(TaskScope, View):
    """The add form: in the app dialog over HTMX, as a page without JavaScript (core/htmx.py)."""

    request: HtmxHttpRequest

    def _back_url(self, request: HttpRequest) -> str:
        """Where Cancel and a no-JS save go: the dashboard if the form came from it, else Tasks."""
        if request.GET.get("from") == "dashboard":
            return self.dashboard_url()
        return self.task_url("tasks")

    def _render(self, request: HtmxHttpRequest, form: TaskForm) -> HttpResponse:
        dialog = bool(request.htmx)
        response = render(
            request,
            "workspace/tasks/new_dialog.html" if dialog else "workspace/tasks/new.html",
            {
                **self.shell(request),
                "layout": self.layout,
                "form": form,
                "dialog": dialog,
                "back_url": self._back_url(request),
            },
        )
        patch_vary_headers(response, ("HX-Request",))
        return response

    def get(self, request: HtmxHttpRequest, **kwargs: Any) -> HttpResponse:
        due = _due_from_query(request.GET.get("due"))
        return self._render(request, TaskForm(initial={"due_on": due} if due else None))

    def post(self, request: HtmxHttpRequest, **kwargs: Any) -> HttpResponse:
        form = TaskForm(request.POST)
        if not form.is_valid():
            return self._render(request, form)
        tasks.create_task(
            actor=_actor(request),
            program=self.scope_program,
            request=request,
            **form.cleaned_data,
        )
        messages.success(request, "Task added.")
        if request.htmx:
            # The page behind the dialog (tasks or dashboard) reloads to show the new task.
            response = close_dialog(HttpResponse(status=204))
            response["HX-Refresh"] = "true"
            return response
        return redirect(self._back_url(request))


class _TaskEdit(TaskScope, View):
    template_name = "workspace/tasks/edit.html"

    def _render(self, request: HttpRequest, task: Task, form: TaskForm) -> HttpResponse:
        context: dict[str, Any] = {
            **self.shell(request),
            "layout": self.layout,
            "task": task,
            "form": form,
            "status": tasks.task_status(task, timezone.localdate()),
            "list_url": self.task_url("tasks"),
            "delete_url": self.task_url("task-delete", pk=task.pk),
        }
        return render(request, self.template_name, context)

    def get(self, request: HttpRequest, pk: int, **kwargs: Any) -> HttpResponse:
        task = tasks.own_task(_actor(request), self.scope_program, pk)
        initial = {"title": task.title, "due_on": task.due_on, "notes": task.notes}
        return self._render(request, task, TaskForm(initial=initial))

    def post(self, request: HttpRequest, pk: int, **kwargs: Any) -> HttpResponse:
        task = tasks.own_task(_actor(request), self.scope_program, pk)
        form = TaskForm(request.POST)
        if not form.is_valid():
            return self._render(request, task, form)
        tasks.update_task(actor=_actor(request), task=task, request=request, **form.cleaned_data)
        messages.success(request, "Task saved.")
        return redirect(self.task_url("tasks"))


class _TaskDone(TaskScope, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, pk: int, **kwargs: Any) -> HttpResponse:
        task = tasks.own_task(_actor(request), self.scope_program, pk)
        done = request.POST.get("done") == "1"
        tasks.set_done(actor=_actor(request), task=task, done=done, request=request)
        messages.success(request, "Task done." if done else "Task reopened.")
        tab = "?tab=done" if not done else ""
        return redirect(self.task_url("tasks") + tab)


class _TaskDelete(TaskScope, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, pk: int, **kwargs: Any) -> HttpResponse:
        task = tasks.own_task(_actor(request), self.scope_program, pk)
        tasks.delete_task(actor=_actor(request), task=task, request=request)
        messages.success(request, "Task deleted.")
        return redirect(self.task_url("tasks"))


class TaskListView(StaffTaskScope, _TaskList):
    pass


class TaskCreateView(StaffTaskScope, _TaskCreate):
    pass


class TaskEditView(StaffTaskScope, _TaskEdit):
    pass


class TaskDoneView(StaffTaskScope, _TaskDone):
    pass


class TaskDeleteView(StaffTaskScope, _TaskDelete):
    pass


class OfficeTaskListView(OfficeTaskScope, _TaskList):
    pass


class OfficeTaskCreateView(OfficeTaskScope, _TaskCreate):
    pass


class OfficeTaskEditView(OfficeTaskScope, _TaskEdit):
    pass


class OfficeTaskDoneView(OfficeTaskScope, _TaskDone):
    pass


class OfficeTaskDeleteView(OfficeTaskScope, _TaskDelete):
    pass
