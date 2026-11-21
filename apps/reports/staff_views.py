"""Program staff send reports and fix returned ones; a head reviews a staff member's report and
sends it to the office (spec §4.8, M11c, rev 33)."""

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
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context
from apps.files.preview import can_preview, render_preview
from apps.programs.models import ProgramMembership

from . import selectors, services
from .forms import HeadReviewForm, ReportForm
from .models import Report

PAGE_SIZE = 25


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


def _is_head(membership: ProgramMembership | None) -> bool:
    """The viewer heads the program (the office has no membership and never reviews here)."""
    return membership is not None and membership.level == ProgramMembership.Level.HEAD


class ReportListView(ProgramStaffRequiredMixin, TemplateView):
    template_name = "reports/staff_list.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        tab = self.request.GET.get("tab", "all")
        if tab not in selectors.REPORT_TABS_STAFF:
            tab = "all"
        base = reverse("reports:list", kwargs={"program": self.program.slug})
        office = self.membership is None  # sees only the reports sent to it (rev 33)
        counts = selectors.status_counts(self.program, office=office)
        page = Paginator(
            selectors.program_reports(self.program, tab, office=office), PAGE_SIZE
        ).get_page(self.request.GET.get("page"))
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

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        # Reports come from programs (M14): the office goes back to the list.
        if request.user.is_authenticated and request.user.is_super_admin:
            messages.info(request, services.OFFICE_CANT_SEND)
            return redirect("reports:list", program=kwargs["program"])
        return super().dispatch(request, *args, **kwargs)

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
                if report.status == Report.Status.WITH_HEAD:
                    messages.success(request, "Report sent to the program head for review.")
                else:
                    messages.success(request, "Report sent to the scholarship office.")
                return redirect("reports:detail", program=self.program.slug, pk=report.pk)
        return self._render(request, form)


def _detail_context(
    request: HttpRequest,
    report: Report,
    membership: ProgramMembership | None,
    form: ReportForm | None = None,
    review_form: HeadReviewForm | None = None,
) -> dict[str, Any]:
    office = _actor(request).is_super_admin  # reviews reports; never resends them
    head = _is_head(membership)
    waiting = report.status == Report.Status.WITH_HEAD
    reviewer = report.reviewed_by
    # The latest note: from the head or the office. A note the office wrote on a report that has
    # since been sent back is history, and the form shows what's current.
    show_note = bool(report.review_note) and not (
        report.status in {Report.Status.WITH_HEAD, Report.Status.SUBMITTED}
        and reviewer is not None
        and reviewer.is_super_admin
    )
    if form is None and report.status == Report.Status.RETURNED and not office:
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
    if waiting and head and review_form is None:
        review_form = HeadReviewForm()
    return {
        "report": report,
        "files": selectors.report_files(report),
        "form": form,
        "review_form": review_form if waiting and head else None,
        "can_send": head and report.status == Report.Status.APPROVED,
        "no_head": services.NO_HEAD
        if waiting and not services.program_heads(report.program)
        else "",
        "show_note": show_note,
        "note_title": "Office note"
        if reviewer is not None and reviewer.is_super_admin
        else "Note from the head",
    }


class ReportDetailView(ProgramStaffRequiredMixin, View):
    template_name = "reports/staff_detail.html"
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        report = selectors.staff_report(self.program, pk, office=self.membership is None)
        context = {
            **shell_context(request, area="staff", program=self.program),
            **_detail_context(request, report, self.membership),
        }
        return render(request, self.template_name, context)


class ReportResubmitView(ProgramStaffRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        report = selectors.staff_report(self.program, pk, office=self.membership is None)
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
            **_detail_context(request, report, self.membership, form=form),
        }
        return render(request, "reports/staff_detail.html", context)


class _HeadActionView(ProgramStaffRequiredMixin, View):
    """A head's POST on a staff member's report; program staff get 403 from the mixin, the
    office from the service (it never reviews or sends for a program, rev 23)."""

    level = ProgramMembership.Level.HEAD
    http_method_names = ["post", "options"]

    def _back(self, report: Report) -> HttpResponse:
        return redirect("reports:detail", program=self.program.slug, pk=report.pk)

    def _refused(self, report: Report, error: ValidationError) -> HttpResponse:
        messages.error(self.request, " ".join(error.messages))
        return self._back(report)


class ReportApproveView(_HeadActionView):
    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        report = selectors.staff_report(self.program, pk, office=self.membership is None)
        form = HeadReviewForm(request.POST)
        if form.is_valid():
            try:
                services.head_approve_report(
                    actor=_actor(request),
                    report=report,
                    note=form.cleaned_data["note"],
                    request=request,
                )
            except ValidationError as error:
                return self._refused(report, error)
            messages.success(request, "Report approved. Send it to the scholarship office next.")
            return self._back(report)
        return self._render(request, report, form)

    def _render(self, request: HttpRequest, report: Report, form: HeadReviewForm) -> HttpResponse:
        context = {
            **shell_context(request, area="staff", program=self.program),
            **_detail_context(request, report, self.membership, review_form=form),
        }
        return render(request, "reports/staff_detail.html", context)


class ReportReturnView(ReportApproveView):
    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        report = selectors.staff_report(self.program, pk, office=self.membership is None)
        form = HeadReviewForm(request.POST)
        if form.is_valid():
            try:
                services.head_return_report(
                    actor=_actor(request),
                    report=report,
                    note=form.cleaned_data["note"],
                    request=request,
                )
            except ValidationError as error:
                if error.messages != [services.NEED_NOTE]:
                    return self._refused(report, error)
                form.add_error("note", error)
            else:
                writer = report.submitted_by.full_name or "the writer"
                messages.success(request, f"Report returned to {writer}.")
                return self._back(report)
        return self._render(request, report, form)


class ReportSendView(_HeadActionView):
    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        report = selectors.staff_report(self.program, pk, office=self.membership is None)
        try:
            services.send_report_to_office(actor=_actor(request), report=report, request=request)
        except ValidationError as error:
            return self._refused(report, error)
        messages.success(request, "Report sent to the scholarship office.")
        return self._back(report)


class ReportFilePreviewView(ProgramStaffRequiredMixin, View):
    """A report file (PDF) in the app dialog (apps/files/preview.py, spec §12 rev 27)."""

    http_method_names = ["get", "options"]

    def get(self, request: HttpRequest, program: str, pk: int, file: int) -> HttpResponse:
        report = selectors.staff_report(self.program, pk, office=self.membership is None)
        row = selectors.report_file(report, file)
        if not can_preview(row.file):
            raise Http404("Nothing to preview.")
        return render_preview(
            request,
            user=_actor(request),
            file=row.file,
            label=report.title,
            back_url=reverse("reports:detail", kwargs={"program": self.program.slug, "pk": pk}),
            layout="layouts/staff.html",
            shell=shell_context(request, area="staff", program=self.program),
        )
