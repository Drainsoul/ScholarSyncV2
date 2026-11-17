"""Staff screens for a program's scholars."""

from typing import Any
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.awards import importing, services
from apps.awards.models import Award, ScholarTerm
from apps.awards.selectors import (
    DEFAULT_SCHOLAR_TAB,
    SCHOLAR_TABS,
    Renewal,
    RenewalStatus,
    ScholarFilters,
    addable_profiles,
    at_risk_reasons,
    next_year_level,
    parse_scholar_filters,
    program_profiles,
    renewal_for,
    scholar_record,
    scholars,
    staff_award,
)
from apps.awards.services import STATUS_LABELS
from apps.awards.staff_forms import (
    AwardEditForm,
    MeritForm,
    NewScholarForm,
    StatusForm,
    TermRecordForm,
)
from apps.awards.views import AWARD_TONES
from apps.core.params import positive_id
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context
from apps.files import storage
from apps.files.models import StoredFile
from apps.files.selectors import usable_file
from apps.files.views import UNAVAILABLE
from apps.programs.models import AcademicTerm, Program
from apps.programs.selectors import application_term, current_term, window_state

PAGE_SIZE = 25
MAX_QUERY = 200
CHOOSE_STUDENT = "Choose a student first."
UPLOAD_AGAIN = "Upload the file again."


def staff_renewal_text(renewal: Renewal, program: Program, today: Any) -> str:
    """Where the scholar stands on renewing, for staff."""
    term = renewal.term
    status = renewal.status
    if status == RenewalStatus.NOT_ACTIVE:
        return "Not active, so no renewal is due."
    if status == RenewalStatus.NO_TERM:
        return "No current term is set."
    if status == RenewalStatus.SUMMER:
        return "No renewal in the summer term."
    if status == RenewalStatus.RENEWED:
        return f"Renewed for {term}."
    if status == RenewalStatus.REJECTED:
        return f"Renewal not approved for {term}."
    if status == RenewalStatus.OPEN:
        return f"Renewal in progress for {term}."
    if window_state(program, today) != "open":
        return f"Due to renew for {term}. Renewals are closed."
    return f"Due to renew for {term}."


def _query(filters: ScholarFilters, **overrides: str) -> str:
    params = {"status": filters.status, "q": filters.q, "tier": filters.tier, **overrides}
    if params["status"] == DEFAULT_SCHOLAR_TAB:
        params.pop("status")
    return urlencode({key: value for key, value in params.items() if value})


def drawer_for(
    program: Program, raw: str, term: AcademicTerm | None, today: Any
) -> dict[str, Any] | None:
    """The drawer for `?scholar=<id>`; anything not one of the program's awards opens nothing."""
    if not raw.isascii() or not raw.isdigit() or len(raw) > 10:
        return None
    try:
        award = staff_award(program, int(raw))
    except Http404:
        return None
    return {
        "award": award,
        "tone": AWARD_TONES[award.status],
        "renewal": staff_renewal_text(renewal_for(award, term), program, today),
        "at_risk": at_risk_reasons(award, program, term, today),
    }


class ScholarListView(ProgramStaffRequiredMixin, TemplateView):
    template_name = "scholars/list.html"
    http_method_names = ["get", "head", "options"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        today = timezone.localdate()
        term = application_term(today)
        filters = parse_scholar_filters(self.request.GET, self.program)
        rows = scholars(self.program, filters, term=term, today=today)
        page = Paginator(rows, PAGE_SIZE).get_page(self.request.GET.get("page"))
        base = reverse("scholars:list", kwargs={"program": self.program.slug})
        list_query = _query(filters, page=str(page.number) if page.number > 1 else "")
        tiers = (
            self.program.tiers.order_by("code", "sort_order").values_list("code", "name").distinct()
        )
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="staff", program=self.program),
            "term": term,
            "filters": filters,
            "page": page,
            "rows": [
                {"award": award, "tone": AWARD_TONES[award.status]} for award in page.object_list
            ],
            "tabs": [
                {
                    "label": label,
                    "url": f"{base}?{_query(filters, status=key)}"
                    if _query(filters, status=key)
                    else base,
                    "current": key == filters.status,
                }
                for key, label in SCHOLAR_TABS.items()
            ],
            "tiers": list(dict(tiers).items()),
            "list_url": base,
            "list_query": list_query,
            "drawer": drawer_for(self.program, self.request.GET.get("scholar", ""), term, today),
            "close_url": f"{base}?{list_query}" if list_query else base,
            "statuses": Award.Status,
        }


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)  # the staff mixin has signed them in
    return user


def _record_url(program: Program, pk: int) -> str:
    return reverse("scholars:detail", kwargs={"program": program.slug, "pk": pk})


class ScholarDetailView(ProgramStaffRequiredMixin, TemplateView):
    template_name = "scholars/detail.html"
    http_method_names = ["get", "head", "options"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        award = staff_award(self.program, kwargs["pk"])
        today = timezone.localdate()
        term = application_term(today)
        record = scholar_record(award, term=term, today=today)
        status_url = reverse(
            "scholars:status", kwargs={"program": self.program.slug, "pk": award.pk}
        )
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="staff", program=self.program),
            "award": award,
            "tone": AWARD_TONES[award.status],
            "record": record,
            "renewal": staff_renewal_text(record.renewal, self.program, today),
            "actions": [
                {"label": STATUS_LABELS[to], "url": f"{status_url}?{urlencode({'to': to})}"}
                for to in sorted(Award.TRANSITIONS.get(award.status, frozenset()))
            ],
            "list_url": reverse("scholars:list", kwargs={"program": self.program.slug}),
        }


class ScholarEditView(ProgramStaffRequiredMixin, View):
    template_name = "scholars/edit.html"

    def _render(
        self, request: HttpRequest, award: Award, form: AwardEditForm, status: int = 200
    ) -> HttpResponse:
        context = {
            **shell_context(request, area="staff", program=self.program),
            "award": award,
            "form": form,
            "record_url": _record_url(self.program, award.pk),
        }
        return render(request, self.template_name, context, status=status)

    def get(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        award = staff_award(self.program, pk)
        initial = {"student_number": award.student_number, "notes": award.notes, "tier": award.tier}
        return self._render(request, award, AwardEditForm(initial=initial, award=award))

    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        award = staff_award(self.program, pk)
        form = AwardEditForm(request.POST, award=award)
        if not form.is_valid():
            return self._render(request, award, form, status=400)
        try:
            services.update_award(
                actor=_actor(request),
                program=self.program,
                award=award,
                student_number=form.cleaned_data["student_number"],
                notes=form.cleaned_data["notes"],
                tier=form.cleaned_data["tier"],
                request=request,
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self._render(request, award, form, status=400)
        messages.success(request, "Scholar details saved.")
        return redirect(_record_url(self.program, award.pk))


class ScholarStatusView(ProgramStaffRequiredMixin, View):
    template_name = "scholars/status.html"

    def _render(
        self, request: HttpRequest, award: Award, form: StatusForm, to: str, status: int = 200
    ) -> HttpResponse:
        context = {
            **shell_context(request, area="staff", program=self.program),
            "award": award,
            "form": form,
            "to": to,
            "label": STATUS_LABELS[to],
            "record_url": _record_url(self.program, award.pk),
        }
        return render(request, self.template_name, context, status=status)

    def get(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        award = staff_award(self.program, pk)
        to = request.GET.get("to", "")
        if to not in Award.TRANSITIONS.get(award.status, frozenset()):
            return redirect(_record_url(self.program, award.pk))
        return self._render(request, award, StatusForm(initial={"to": to}), to)

    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        award = staff_award(self.program, pk)
        form = StatusForm(request.POST)
        if not form.is_valid():
            to = request.POST.get("to", "")
            if to not in STATUS_LABELS:
                return redirect(_record_url(self.program, award.pk))
            return self._render(request, award, form, to, status=400)
        to = form.cleaned_data["to"]
        try:
            changed = services.change_status(
                actor=_actor(request),
                program=self.program,
                award=award,
                to=to,
                reason=form.cleaned_data["reason"],
                request=request,
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self._render(request, award, form, to, status=400)
        messages.success(
            request,
            f"{STATUS_LABELS[to]}. The award is now {changed.get_status_display().lower()}.",
        )
        return redirect(_record_url(self.program, award.pk))


class TermFormView(ProgramStaffRequiredMixin, View):
    """Add a term record (no `term` in the URL) or correct one."""

    template_name = "scholars/term_form.html"

    def _record(self, award: Award, kwargs: dict[str, Any]) -> ScholarTerm | None:
        if "term" not in kwargs:
            return None
        record = award.terms.select_related("term", "school").filter(pk=kwargs["term"]).first()
        if record is None:
            raise Http404("No such term record.")
        return record

    def _render(
        self,
        request: HttpRequest,
        award: Award,
        form: TermRecordForm,
        record: ScholarTerm | None,
        status: int = 200,
    ) -> HttpResponse:
        context = {
            **shell_context(request, area="staff", program=self.program),
            "award": award,
            "form": form,
            "record": record,
            "record_url": _record_url(self.program, award.pk),
        }
        return render(request, self.template_name, context, status=status)

    def get(self, request: HttpRequest, program: str, pk: int, **kwargs: Any) -> HttpResponse:
        award = staff_award(self.program, pk)
        record = self._record(award, kwargs)
        if record is None:
            term = current_term()
            initial: dict[str, Any] = {"term": term}
            if term is not None:
                initial["year_level"] = next_year_level(award, term)
            form = TermRecordForm(initial=initial, award=award)
        else:
            form = TermRecordForm(
                initial={
                    "school": record.school,
                    "school_name": record.school_name,
                    "school_type": record.school_type,
                    "gwa_scale": record.gwa_scale,
                    "course": record.course,
                    "year_level": record.year_level,
                    "gwa": record.gwa,
                    "units": record.units,
                    "compliance_checked": record.compliance == ScholarTerm.Compliance.COMPLETE,
                },
                award=award,
                editing=True,
            )
        return self._render(request, award, form, record)

    def post(self, request: HttpRequest, program: str, pk: int, **kwargs: Any) -> HttpResponse:
        award = staff_award(self.program, pk)
        record = self._record(award, kwargs)
        form = TermRecordForm(request.POST, award=award, editing=record is not None)
        if not form.is_valid():
            return self._render(request, award, form, record, status=400)
        try:
            if record is None:
                services.add_term(
                    actor=_actor(request),
                    program=self.program,
                    award=award,
                    data=form.term_data(form.cleaned_data["term"]),
                    request=request,
                )
                message = "Term record added."
            else:
                services.edit_term(
                    actor=_actor(request),
                    program=self.program,
                    award=award,
                    scholar_term_id=record.pk,
                    data=form.term_data(record.term),
                    request=request,
                )
                message = "Term record saved."
        except ValidationError as error:
            form.add_error(None, error)
            return self._render(request, award, form, record, status=400)
        messages.success(request, message)
        return redirect(_record_url(self.program, award.pk))


class TermMeritView(ProgramStaffRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, pk: int, term: int) -> HttpResponse:
        award = staff_award(self.program, pk)
        form = MeritForm(request.POST)
        if not form.is_valid():
            return HttpResponse("Choose Confirm merit or No merit.", status=400)
        merit = form.cleaned_data["merit"] == "yes"
        services.confirm_merit(
            actor=_actor(request),
            program=self.program,
            award=award,
            scholar_term_id=term,
            merit=merit,
            request=request,
        )
        messages.success(request, "Merit confirmed." if merit else "Marked as no merit.")
        return redirect(_record_url(self.program, award.pk))


class NewScholarView(ProgramStaffRequiredMixin, View):
    """Add scholar: pick one of the program's students (GET), then the award form (?profile=)."""

    template_name = "scholars/new.html"

    def _picker(self, request: HttpRequest, *, error: str = "", status: int = 200) -> HttpResponse:
        q = request.GET.get("q", "").replace("\x00", "").strip()[:MAX_QUERY]
        paginator = Paginator(addable_profiles(self.program, q), PAGE_SIZE)
        page = paginator.get_page(request.GET.get("page"))
        context = {
            **shell_context(request, area="staff", program=self.program),
            "program": self.program,
            "q": q,
            "page": page,
            "profiles": page.object_list,
            "total": paginator.count,
            "new_url": reverse("scholars:new", kwargs={"program": self.program.slug}),
            "error": error,
            "form": None,
        }
        return render(request, self.template_name, context, status=status)

    def _form(
        self, request: HttpRequest, profile: Any, form: NewScholarForm, status: int = 200
    ) -> HttpResponse:
        context = {
            **shell_context(request, area="staff", program=self.program),
            "program": self.program,
            "profile": profile,
            "form": form,
            "new_url": reverse("scholars:new", kwargs={"program": self.program.slug}),
        }
        return render(request, self.template_name, context, status=status)

    def _profile(self, raw: str) -> Any:
        profile_id = positive_id(raw)
        if profile_id is None:
            return None
        profile = program_profiles(self.program).filter(pk=profile_id).first()
        if profile is None:
            raise Http404("No such student.")
        return profile

    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        profile = self._profile(request.GET.get("profile", ""))
        if profile is None:
            return self._picker(request)
        return self._form(request, profile, NewScholarForm(program=self.program))

    def post(self, request: HttpRequest, program: str) -> HttpResponse:
        profile = self._profile(request.POST.get("profile", ""))
        if profile is None:
            return self._picker(request, error=CHOOSE_STUDENT, status=400)
        form = NewScholarForm(request.POST, program=self.program)
        if not form.is_valid():
            return self._form(request, profile, form, status=400)
        try:
            award = services.create_award(
                actor=_actor(request),
                program=self.program,
                profile_id=profile.pk,
                data=form.award_data(),
                source=Award.Source.MANUAL,
                request=request,
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self._form(request, profile, form, status=400)
        messages.success(request, f"Added {profile.full_name} as a scholar.")
        return redirect(_record_url(self.program, award.pk))


# What each import column takes, for the import page.
IMPORT_COLUMN_HELP: tuple[tuple[str, str, str], ...] = (
    ("last_name", "Yes", "Text"),
    ("first_name", "Yes", "Text"),
    ("middle_name", "No", "Text"),
    ("suffix", "No", "Text"),
    ("birth_date", "Yes", "A date: 2005-03-14 or 3/14/2005"),
    ("student_number", "No", "Text, up to 50 characters"),
    ("tier", "Yes", "A tier code in force for the row's term"),
    ("school_year", "No", "2026-2027 or 2026; blank with term for the current term"),
    ("term", "No", "1, 2, 3, 1st semester, 2nd semester or summer"),
    ("school", "Yes", "A listed school's name, or any other name"),
    ("school_type", "If not listed", "Public, private, SUC or LCU"),
    ("gwa_scale", "If not listed", "percent, one_to_five or four_point"),
    ("course", "No", "Text"),
    ("year_level", "No", "1 to 10"),
    ("gwa", "No", "Within the grading scale's range"),
    ("units", "No", "0 to 1000"),
)


class ScholarImportView(ProgramStaffRequiredMixin, View):
    """Upload a file, check every row (the preview), then import them all (spec §4.6, M9b)."""

    template_name = "scholars/import.html"

    def _active(self) -> None:
        if not self.program.is_active:
            raise Http404("No such program.")

    def _render(
        self,
        request: HttpRequest,
        *,
        preview: importing.ImportPreview | None = None,
        file: StoredFile | None = None,
        error: str = "",
        status: int = 200,
    ) -> HttpResponse:
        context = {
            **shell_context(request, area="staff", program=self.program),
            "program": self.program,
            "preview": preview,
            "file": file,
            "error": error,
            "columns": IMPORT_COLUMN_HELP,
            "import_url": reverse("scholars:import", kwargs={"program": self.program.slug}),
            "template_url": reverse(
                "scholars:import-template", kwargs={"program": self.program.slug}
            ),
        }
        return render(request, self.template_name, context, status=status)

    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        self._active()
        return self._render(request)

    def post(self, request: HttpRequest, program: str) -> HttpResponse:
        self._active()
        action = request.POST.get("action", "")
        if action not in ("check", "import"):
            return self._render(request, error=UPLOAD_AGAIN, status=400)
        file = usable_file(_actor(request), request.POST.get("file", ""), StoredFile.Purpose.IMPORT)
        if file is None:
            return self._render(request, error=UPLOAD_AGAIN, status=400)
        try:
            if action == "check":
                preview = importing.check_import(self.program, file)
                status = 200 if preview.ok else 400
                return self._render(request, preview=preview, file=file, status=status)
            batch = importing.import_scholars(
                actor=_actor(request), program=self.program, file_id=file.pk, request=request
            )
        except storage.StorageUnavailable:
            return self._render(request, error=UNAVAILABLE, status=503)
        except importing.ImportRejected as rejected:
            return self._render(request, preview=rejected.preview, file=file, status=400)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("scholars:list", program=self.program.slug)
        noun = "scholar" if batch.row_count == 1 else "scholars"
        messages.success(request, f"Imported {batch.row_count} {noun}.")
        return redirect("scholars:list", program=self.program.slug)


class ImportTemplateView(ProgramStaffRequiredMixin, View):
    """The import template: a CSV with the column names and no rows."""

    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        response = HttpResponse(importing.TEMPLATE_CSV, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="scholars-import-template.csv"'
        response["Cache-Control"] = "no-store"
        return response
