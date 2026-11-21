"""The office reviews program reports: accept, or return with a note (spec §4.8, M11c)."""

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.core.params import positive_id
from apps.core.permissions import SuperAdminRequiredMixin
from apps.core.shell import shell_context
from apps.files.preview import can_preview, render_preview
from apps.programs.models import Program

from . import selectors, services
from .forms import DecideForm
from .models import Report

PAGE_SIZE = 25


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


class OfficeReportListView(SuperAdminRequiredMixin, TemplateView):
    template_name = "reports/office_list.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        params = self.request.GET
        tab = params.get("tab", "submitted")
        if tab not in selectors.REPORT_TABS_OFFICE:
            tab = "submitted"
        programs = list(Program.objects.order_by("name"))
        program_id = positive_id(params.get("program", ""))
        if program_id not in {program.pk for program in programs}:
            program_id = None
        counts = selectors.status_counts(
            next((program for program in programs if program.pk == program_id), None),
            office=True,
        )
        base = reverse("office:reports")
        suffix = f"&program={program_id}" if program_id is not None else ""
        page = Paginator(selectors.office_reports(tab, program_id), PAGE_SIZE).get_page(
            params.get("page")
        )
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="office"),
            "page": page,
            "tab": tab,
            "programs": programs,
            "program_id": program_id,
            "tabs": [
                {
                    "label": label,
                    "url": f"{base}?tab={key}{suffix}",
                    "current": key == tab,
                    "count": counts.get(key, 0),
                }
                for key, label in selectors.REPORT_TABS_OFFICE.items()
            ],
        }


def _detail(request: HttpRequest, report: Report, form: DecideForm | None) -> HttpResponse:
    context = {
        **shell_context(request, area="office"),
        "report": report,
        "files": selectors.report_files(report),
        "form": form if report.status == Report.Status.SUBMITTED else None,
    }
    return render(request, "reports/office_detail.html", context)


class OfficeReportDetailView(SuperAdminRequiredMixin, View):
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        return _detail(request, selectors.office_report(pk), DecideForm())


class OfficeReportDecideView(SuperAdminRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        report = selectors.office_report(pk)
        if report.status != Report.Status.SUBMITTED:
            messages.error(request, services.already(report))
            return redirect("office:report-detail", pk=report.pk)
        form = DecideForm(request.POST)
        if form.is_valid():
            accept = form.cleaned_data["decision"] == "accept"
            try:
                services.decide_report(
                    actor=_actor(request),
                    report=report,
                    accept=accept,
                    note=form.cleaned_data["note"],
                    request=request,
                )
            except ValidationError as error:
                if error.messages == [services.NEED_NOTE]:
                    form.add_error("note", error)
                else:
                    messages.error(request, " ".join(error.messages))
                    return redirect("office:report-detail", pk=report.pk)
            else:
                if accept:
                    messages.success(request, "Report accepted.")
                else:
                    messages.success(request, f"Report returned to {report.program.name}.")
                return redirect("office:report-detail", pk=report.pk)
        return _detail(request, report, form)


class OfficeReportFilePreviewView(SuperAdminRequiredMixin, View):
    """A report file (PDF) in the app dialog (apps/files/preview.py, spec §12 rev 27)."""

    http_method_names = ["get", "options"]

    def get(self, request: HttpRequest, pk: int, file: int) -> HttpResponse:
        report = selectors.office_report(pk)
        row = selectors.report_file(report, file)
        if not can_preview(row.file):
            raise Http404("Nothing to preview.")
        return render_preview(
            request,
            user=_actor(request),
            file=row.file,
            label=report.title,
            back_url=reverse("office:report-detail", kwargs={"pk": pk}),
            layout="layouts/office.html",
            shell=shell_context(request, area="office"),
        )
