"""Program staff send reports to the office and fix returned ones (spec §4.8, M11c)."""

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context

from . import selectors, services
from .forms import ReportForm
from .models import Report

PAGE_SIZE = 25


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


class ReportListView(ProgramStaffRequiredMixin, TemplateView):
    template_name = "reports/staff_list.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        tab = self.request.GET.get("tab", "all")
        if tab not in selectors.REPORT_TABS_STAFF:
            tab = "all"
        base = reverse("reports:list", kwargs={"program": self.program.slug})
        counts = {
            row["status"]: row["n"]
            for row in Report.objects.filter(program=self.program)
            .values("status")
            .order_by()
            .annotate(n=Count("pk"))
        }
        counts["all"] = sum(counts.values())
        page = Paginator(selectors.program_reports(self.program, tab), PAGE_SIZE).get_page(
            self.request.GET.get("page")
        )
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="staff", program=self.program),
            "page": page,
            "tab": tab,
            "tabs": [
                {
                    "label": label,
                    "url": base if key == "all" else f"{base}?tab={key}",
                    "current": key == tab,
                    "count": counts.get(key, 0),
                }
                for key, label in selectors.REPORT_TABS_STAFF.items()
            ],
        }


class ReportNewView(ProgramStaffRequiredMixin, View):
    template_name = "reports/staff_new.html"

    def _render(self, request: HttpRequest, form: ReportForm) -> HttpResponse:
        context = {**shell_context(request, area="staff", program=self.program), "form": form}
        return render(request, self.template_name, context)

    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        return self._render(request, ReportForm(_actor(request)))

    def post(self, request: HttpRequest, program: str) -> HttpResponse:
        form = ReportForm(_actor(request), request.POST)
        if form.is_valid():
            try:
                report = services.submit_report(
                    actor=_actor(request),
                    program=self.program,
                    request=request,
                    **form.cleaned_data,
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Report sent to the scholarship office.")
                return redirect("reports:detail", program=self.program.slug, pk=report.pk)
        return self._render(request, form)


def _detail_context(
    request: HttpRequest, report: Report, form: ReportForm | None = None
) -> dict[str, Any]:
    if form is None and report.status == Report.Status.RETURNED:
        form = ReportForm(
            _actor(request),
            require_file=False,
            initial={
                "title": report.title,
                "period_start": report.period_start,
                "period_end": report.period_end,
                "description": report.description,
            },
        )
    return {
        "report": report,
        "files": selectors.report_files(report),
        "form": form,
    }


class ReportDetailView(ProgramStaffRequiredMixin, View):
    template_name = "reports/staff_detail.html"
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        report = selectors.staff_report(self.program, pk)
        context = {
            **shell_context(request, area="staff", program=self.program),
            **_detail_context(request, report),
        }
        return render(request, self.template_name, context)


class ReportResubmitView(ProgramStaffRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        report = selectors.staff_report(self.program, pk)
        if report.status != Report.Status.RETURNED:
            messages.error(request, services.NOT_RETURNED)
            return redirect("reports:detail", program=self.program.slug, pk=report.pk)
        form = ReportForm(_actor(request), request.POST, require_file=False)
        if form.is_valid():
            try:
                services.resubmit_report(
                    actor=_actor(request), report=report, request=request, **form.cleaned_data
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Report sent again.")
                return redirect("reports:detail", program=self.program.slug, pk=report.pk)
        context = {
            **shell_context(request, area="staff", program=self.program),
            **_detail_context(request, report, form),
        }
        return render(request, "reports/staff_detail.html", context)
