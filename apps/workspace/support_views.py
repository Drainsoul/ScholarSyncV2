from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.accounts.models import User
from apps.core.permissions import StudentRequiredMixin, SuperAdminRequiredMixin
from apps.core.shell import shell_context

from . import support
from .forms import SupportForm
from .models import SupportRequest

PAGE_SIZE = 25


def _user(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


class StudentSupportView(StudentRequiredMixin, View):
    template_name = "workspace/support/student.html"

    def _render(self, request: HttpRequest, form: SupportForm) -> HttpResponse:
        context = {
            **shell_context(request, area="student"),
            "form": form,
            "rows": support.own_rows(_user(request)),
        }
        return render(request, self.template_name, context)

    def get(self, request: HttpRequest) -> HttpResponse:
        return self._render(request, SupportForm())

    def post(self, request: HttpRequest) -> HttpResponse:
        form = SupportForm(request.POST)
        if not form.is_valid():
            return self._render(request, form)
        try:
            support.send(sender=_user(request), now=timezone.now(), **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
            return self._render(request, form)
        messages.success(request, "Message sent. The scholarship office will reply by email.")
        return redirect("support:student")


class OfficeSupportView(SuperAdminRequiredMixin, View):
    template_name = "workspace/support/office.html"
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest) -> HttpResponse:
        tab = request.GET.get("tab", "open")
        if tab not in support.OFFICE_TABS:
            tab = "open"
        page = Paginator(support.office_rows(tab), PAGE_SIZE).get_page(request.GET.get("page"))
        base = reverse("support:office")
        context = {
            **shell_context(request, area="office"),
            "page": page,
            "tab": tab,
            "tabs": [
                {
                    "label": label,
                    "url": base if key == "open" else f"{base}?tab={key}",
                    "current": key == tab,
                    "count": support.open_count() if key == "open" else 0,
                }
                for key, label in support.OFFICE_TABS.items()
            ],
        }
        return render(request, self.template_name, context)


class AnswerView(SuperAdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        row = get_object_or_404(SupportRequest, pk=pk)
        support.answer(actor=_user(request), request_row=row, now=timezone.now())
        messages.success(request, "Marked as answered.")
        return redirect("support:office")
