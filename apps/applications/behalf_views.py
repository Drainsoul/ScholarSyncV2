"""Staff screens for filing an application on a student's behalf."""

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View

from apps.applications import behalf
from apps.applications.forms import DocumentForm
from apps.applications.models import Application, Document
from apps.applications.review import DECISION_REASON_TOO_LONG
from apps.applications.review_selectors import (
    MAX_TERM_ID,
    behalf_application,
    behalf_in_progress,
    filing_profiles,
)
from apps.applications.selectors import document_rows
from apps.applications.staff_forms import AcademicsForm, BehalfSubmitForm
from apps.applications.staff_views import PAGE_SIZE, _actor, _error_text, _evaluated_on
from apps.applications.views import APPLICATION_TONES, DOCUMENT_TONES, DocumentCard
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context
from apps.matching.checklist import checklist_items, snapshot_items
from apps.matching.eligibility import Academic
from apps.matching.selectors import eligibility_with
from apps.programs.models import BenefitTier, Program, RequiredDocument
from apps.programs.selectors import tiers_in_force

CHOOSE_STUDENT = "Choose a student."
MAX_QUERY = 200


def _profile_id(raw: str) -> int | None:
    """The posted profile id, or None for anything that is not a plausible row id."""
    if not raw.isascii() or not raw.isdigit():
        return None
    value = int(raw)
    return value if 0 < value <= MAX_TERM_ID else None


class NewView(ProgramStaffRequiredMixin, View):
    http_method_names = ["get", "head", "post", "options"]

    def _render(self, request: HttpRequest, *, error: str = "", status: int = 200) -> HttpResponse:
        q = request.GET.get("q", "").replace("\x00", "").strip()[:MAX_QUERY]
        paginator = Paginator(filing_profiles(self.program, q), PAGE_SIZE)
        page = paginator.get_page(request.GET.get("page"))
        in_progress = [
            {"application": application, "tone": APPLICATION_TONES[application.status]}
            for application in behalf_in_progress(self.program)
        ]
        return render(
            request,
            "review/behalf_new.html",
            {
                **shell_context(request, area="staff", program=self.program),
                "program": self.program,
                "q": q,
                "page": page,
                "profile_rows": [
                    {"profile": profile, "claimed": profile.user_id is not None}
                    for profile in page.object_list
                ],
                "in_progress": in_progress,
                "total": paginator.count,
                "clear_url": reverse("review:behalf-new", kwargs={"program": self.program.slug}),
                "error": error,
            },
            status=status,
        )

    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        return self._render(request)

    def post(self, request: HttpRequest, program: str) -> HttpResponse:
        profile_id = _profile_id(request.POST.get("profile", ""))
        if profile_id is None:
            return self._render(request, error=CHOOSE_STUDENT, status=400)
        try:
            application = behalf.start_on_behalf(
                actor=_actor(request),
                program=self.program,
                profile_id=profile_id,
                request=request,
            )
        except ValidationError as error:  # a missing profile is an Http404, not caught
            return self._render(request, error=_error_text(error), status=400)
        messages.success(request, f"Application started for {application.profile.full_name}.")
        return redirect("review:behalf", program=self.program.slug, pk=application.pk)


EDITABLE = (Application.Status.DRAFT, Application.Status.RETURNED)
OVERRIDE_SENTENCES = (behalf.NEED_OVERRIDE, DECISION_REASON_TOO_LONG)


def _academics_initial(application: Application) -> dict[str, Any]:
    return {
        "school": application.school_id,
        "school_name": application.school_name,
        "school_type": application.school_type,
        "gwa_scale": application.gwa_scale,
        "course": application.course,
        "year_level": application.year_level,
        "gwa": application.gwa,
        "units": application.units,
    }


def _frozen(application: Application) -> dict[str, Any]:
    """The school and grades a returned application was submitted with, for reading only."""
    school = application.school.name if application.school is not None else application.school_name
    return {
        "school": school,
        "course": application.course,
        "year_level": application.year_level,
        "gwa": application.gwa,
        "gwa_scale": application.get_gwa_scale_display() if application.gwa_scale else "",
        "units": application.units,
    }


def _live_items(application: Application) -> list[dict[str, str]]:
    """The live checklist for a draft. Staff get no "fix this in your profile" links."""
    result = eligibility_with(
        application.profile,
        application.program,
        Academic.from_application(application),
        today=timezone.localdate(),
    )
    return [{**item, "url": "", "url_label": ""} for item in checklist_items(result)]


def _candidates(application: Application) -> list[BenefitTier]:
    """Tiers staff can pick: those in force for a draft, none on a resubmit (the tier is kept)."""
    if application.status != Application.Status.DRAFT:
        return []
    return tiers_in_force(application.program, application.term)


def render_filing(
    request: HttpRequest,
    program: Program,
    application: Application,
    *,
    academics_form: AcademicsForm | None = None,
    submit_form: BehalfSubmitForm | None = None,
    error_for: RequiredDocument | None = None,
    error: str = "",
    banner: str = "",
    status: int = 200,
) -> HttpResponse:
    """The filing page; `error` shows on the row of `error_for`, and a banner points there.

    Anything past draft or returned belongs on the review screen; a message, if any, goes along.
    """
    if application.status not in EDITABLE:
        if banner or error:
            messages.error(request, banner or error)
        return redirect("review:detail", program=program.slug, pk=application.pk)
    draft = application.status == Application.Status.DRAFT
    cards = []
    error_card: DocumentCard | None = None
    for row in document_rows(application):
        document = row.document
        approved = document is not None and document.status == Document.Status.APPROVED
        has_error = error_for is not None and error_for.pk == row.requirement.pk
        card = DocumentCard(
            row=row,
            anchor=f"doc-{row.requirement.pk}",
            field_id=f"doc-{row.requirement.pk}-file",
            editable=not approved,
            tone=DOCUMENT_TONES[document.status] if document is not None else "info",
            error=error if has_error else "",
        )
        cards.append(card)
        if has_error:
            error_card = card
    if error and error_card is None and not banner:
        banner = error  # no row to show it on: say it at the top instead
    snapshot = application.match_snapshot if isinstance(application.match_snapshot, dict) else {}
    if draft:
        items = _live_items(application)
        if academics_form is None:
            academics_form = AcademicsForm(initial=_academics_initial(application))
    else:
        items = snapshot_items(snapshot)
        academics_form = None
    if submit_form is None:
        submit_form = BehalfSubmitForm(candidates=_candidates(application))
    required = [card for card in cards if card.row.requirement.is_required]
    filer = application.created_by
    context = {
        **shell_context(request, area="staff", program=program),
        "program": program,
        "application": application,
        "profile": application.profile,
        "tone": APPLICATION_TONES[application.status],
        "filed_by": filer.full_name if filer is not None and filer.full_name else "staff",
        "draft": draft,
        "academics_form": academics_form,
        "frozen": None if draft else _frozen(application),
        "checks": items,
        "rules_met": sum(1 for item in items if item["state"] == "met"),
        "any_unmet": draft and any(item["state"] != "met" for item in items),
        "evaluated_on": None if draft else _evaluated_on(snapshot),
        "cards": cards,
        "error_card": error_card,
        "uploaded_count": sum(1 for card in required if card.row.current is not None),
        "required_count": len(required),
        "submit_form": submit_form,
        "banner": banner,
    }
    return render(request, "review/behalf_detail.html", context, status=status)


class _FilingView(ProgramStaffRequiredMixin, View):
    def refused(self, request: HttpRequest, pk: int, **kwargs: Any) -> HttpResponse:
        """Re-read the row after a refusal: show the state that refused, not the one first seen."""
        application = behalf_application(self.program, pk)
        return render_filing(request, self.program, application, status=400, **kwargs)


class FilingView(_FilingView):
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        return render_filing(request, self.program, behalf_application(self.program, pk))


class AcademicsView(_FilingView):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        application = behalf_application(self.program, pk)
        if application.status != Application.Status.DRAFT:
            return self.refused(request, pk, banner=behalf.ACADEMICS_FROZEN)
        form = AcademicsForm(request.POST)
        if not form.is_valid():
            return render_filing(
                request, self.program, application, academics_form=form, status=400
            )
        try:
            behalf.set_academics(
                actor=_actor(request),
                program=self.program,
                pk=pk,
                data=form.cleaned_data,
                request=request,
            )
        except ValidationError as error:  # a missing application is an Http404, not caught
            return self.refused(request, pk, academics_form=form, banner=_error_text(error))
        messages.success(request, "School and grades saved.")
        return redirect("review:behalf", program=self.program.slug, pk=pk)


class DocumentView(_FilingView):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, pk: int, requirement: int) -> HttpResponse:
        behalf_application(self.program, pk)  # another program's or a student's row is a 404
        required = get_object_or_404(RequiredDocument, pk=requirement, program=self.program)
        form = DocumentForm(request.POST)
        try:
            if not form.is_valid():
                raise ValidationError(list(form.errors["file"]))
            behalf.attach_on_behalf(
                actor=_actor(request),
                program=self.program,
                pk=pk,
                requirement=required,
                file_id=form.cleaned_data["file"],
                request=request,
            )
        except ValidationError as error:
            return self.refused(request, pk, error_for=required, error=_error_text(error))
        messages.success(request, "Document saved.")
        target = reverse("review:behalf", kwargs={"program": self.program.slug, "pk": pk})
        return redirect(f"{target}#doc-{required.pk}")


class SubmitView(_FilingView):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        application = behalf_application(self.program, pk)
        # A resubmit keeps its tier and snapshot: nothing posted beyond the button counts.
        data = request.POST if application.status == Application.Status.DRAFT else {}
        form = BehalfSubmitForm(data, candidates=_candidates(application))
        if not form.is_valid():
            return render_filing(request, self.program, application, submit_form=form, status=400)
        try:
            behalf.submit_on_behalf(
                actor=_actor(request),
                program=self.program,
                pk=pk,
                tier=form.cleaned_data.get("tier"),
                override_reason=form.cleaned_data.get("override_reason") or "",
                request=request,
            )
        except ValidationError as error:  # InvalidTransition is one too; Http404 is not caught
            text = _error_text(error)
            if text in OVERRIDE_SENTENCES and "override_reason" in form.fields:
                form.add_error("override_reason", text)  # said where the reason goes
                return self.refused(request, pk, submit_form=form)
            return self.refused(request, pk, submit_form=form, banner=text)
        messages.success(request, f"Submitted {application.profile.full_name}'s application.")
        return redirect("review:detail", program=self.program.slug, pk=pk)


class WithdrawView(ProgramStaffRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        try:
            behalf.withdraw_on_behalf(
                actor=_actor(request), program=self.program, pk=pk, request=request
            )
        except ValidationError as error:  # a missing application is an Http404, not caught
            messages.error(request, _error_text(error))
            return redirect("review:behalf", program=self.program.slug, pk=pk)
        messages.success(request, "Application withdrawn.")
        return redirect("review:behalf-new", program=self.program.slug)
