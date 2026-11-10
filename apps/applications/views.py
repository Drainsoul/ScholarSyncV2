from dataclasses import dataclass
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.applications import services
from apps.applications.forms import DocumentForm, SubmitForm
from apps.applications.models import Application, Document
from apps.applications.selectors import (
    DocumentRow,
    applications_for_student,
    document_rows,
    open_application,
    own_application,
)
from apps.core.permissions import StudentRequiredMixin
from apps.core.shell import shell_context
from apps.matching.checklist import checklist_items
from apps.matching.selectors import eligibility_for
from apps.programs.models import BenefitTier, Program, RequiredDocument
from apps.programs.selectors import application_term
from apps.students.selectors import current_education, profile_for

APPLICATION_TONES: dict[str, str] = {
    Application.Status.DRAFT: "warning",
    Application.Status.RETURNED: "warning",
    Application.Status.SUBMITTED: "info",
    Application.Status.UNDER_REVIEW: "info",
    Application.Status.APPROVED: "success",
    Application.Status.REJECTED: "neutral",
    Application.Status.WITHDRAWN: "neutral",
}
DOCUMENT_TONES: dict[str, str] = {
    Document.Status.PENDING: "info",
    Document.Status.APPROVED: "success",
    Document.Status.DECLINED: "danger",
}


def _student(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


def _error_text(error: ValidationError) -> str:
    return " ".join(error.messages)


class ListView(StudentRequiredMixin, TemplateView):
    template_name = "applications/list.html"
    http_method_names = ["get", "head", "options"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        rows = [
            {"application": application, "tone": APPLICATION_TONES[application.status]}
            for application in applications_for_student(_student(self.request))
        ]
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="student"),
            "rows": rows,
            "match_url": reverse("matching:match"),
        }


class NewView(StudentRequiredMixin, View):
    template_name = "applications/new.html"

    def _render(
        self, request: HttpRequest, program: Program, *, error: str = "", status: int = 200
    ) -> HttpResponse:
        profile = profile_for(_student(request))
        result = (
            eligibility_for(profile, program, today=timezone.localdate())
            if profile is not None
            else None
        )
        context = {
            **shell_context(request, area="student"),
            "program": program,
            "has_profile": profile is not None,
            "items": checklist_items(result) if result is not None else [],
            "eligible": result is not None and result.eligible,
            "error": error,
            "profile_url": reverse("students:profile"),
        }
        return render(request, self.template_name, context, status=status)

    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        found = get_object_or_404(Program, slug=program, is_active=True)
        profile = profile_for(_student(request))
        term = application_term(timezone.localdate())
        if profile is not None and term is not None:
            existing = open_application(profile, found, term)
            if existing is not None:
                return redirect("applications:detail", pk=existing.pk)
        return self._render(request, found)

    def post(self, request: HttpRequest, program: str) -> HttpResponse:
        found = get_object_or_404(Program, slug=program, is_active=True)
        try:
            application = services.start_application(
                user=_student(request), program=found, request=request
            )
        except ValidationError as error:
            return self._render(request, found, error=_error_text(error), status=400)
        messages.success(request, "Application started.")
        return redirect("applications:detail", pk=application.pk)


@dataclass(frozen=True)
class DocumentCard:
    row: DocumentRow
    anchor: str
    field_id: str
    editable: bool
    tone: str
    error: str


def _academic(application: Application, user: User) -> dict[str, Any] | None:
    """The live current school and grades for a draft, the frozen copy for anything else."""
    if application.status == Application.Status.DRAFT:
        profile = profile_for(user)
        record = current_education(profile) if profile is not None else None
        if record is None:
            return None
        school = record.school.name if record.school is not None else record.school_name
        return {
            "school": school,
            "course": record.course,
            "year_level": record.year_level,
            "gwa": record.gwa,
            "units": record.units,
            "live": True,
        }
    school = application.school.name if application.school is not None else application.school_name
    return {
        "school": school,
        "course": application.course,
        "year_level": application.year_level,
        "gwa": application.gwa,
        "units": application.units,
        "live": False,
    }


WITHDRAWABLE = (
    Application.Status.DRAFT,
    Application.Status.SUBMITTED,
    Application.Status.RETURNED,
)


def _candidates(user: User, application: Application) -> list[BenefitTier]:
    """The tiers the student can pick: live for a draft, the requested one once returned."""
    if application.status != Application.Status.DRAFT:
        return [application.requested_tier] if application.requested_tier is not None else []
    profile = profile_for(user)
    if profile is None:
        return []
    result = eligibility_for(profile, application.program, today=timezone.localdate())
    return list(result.tier_candidates)


def _submit_form(user: User, application: Application, data: QueryDict | None = None) -> SubmitForm:
    return SubmitForm(data, candidates=_candidates(user, application))


def render_detail(
    request: HttpRequest,
    application: Application,
    *,
    error_for: RequiredDocument | None = None,
    error: str = "",
    status: int = 200,
    submit_form: SubmitForm | None = None,
    banner: str = "",
) -> HttpResponse:
    """The application page; `error` shows on the row of `error_for` only.

    `submit_form` is a bound form from a failed submit; `banner` is a service sentence.
    """
    rows = document_rows(application)
    cards = []
    for row in rows:
        document = row.document
        approved = document is not None and document.status == Document.Status.APPROVED
        has_error = error_for is not None and error_for.pk == row.requirement.pk
        cards.append(
            DocumentCard(
                row=row,
                anchor=f"doc-{row.requirement.pk}",
                field_id=f"doc-{row.requirement.pk}-file",
                editable=application.is_editable and not approved,
                tone=DOCUMENT_TONES[document.status] if document is not None else "info",
                error=error if has_error else "",
            )
        )
    required = [row for row in rows if row.requirement.is_required]
    if not application.is_editable:
        submit_form = None
    elif submit_form is None:
        submit_form = _submit_form(_student(request), application)
    context = {
        "submit_form": submit_form,
        "banner": banner,
        "can_withdraw": application.status in WITHDRAWABLE,
        **shell_context(request, area="student"),
        "application": application,
        "status_tone": APPLICATION_TONES[application.status],
        "academic": _academic(application, _student(request)),
        "cards": cards,
        "uploaded_count": sum(1 for row in required if row.current is not None),
        "required_count": len(required),
        "education_url": reverse("students:profile-education"),
    }
    return render(request, "applications/detail.html", context, status=status)


class DetailView(StudentRequiredMixin, View):
    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        return render_detail(request, own_application(_student(request), pk))


class SubmitView(StudentRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        user = _student(request)
        application = own_application(user, pk)
        form = _submit_form(user, application, request.POST)
        if not form.is_valid():
            return render_detail(request, application, submit_form=form, status=400)
        try:
            services.submit_application(
                user=user,
                application=application,
                tier=form.cleaned_data.get("tier"),
                request=request,
            )
        except ValidationError as error:
            # The service read the row under a lock; show it as it is now, not as we first saw it.
            fresh = own_application(user, pk)
            return render_detail(
                request, fresh, submit_form=form, banner=_error_text(error), status=400
            )
        messages.success(request, "Application submitted. We've emailed you a copy.")
        return redirect("applications:detail", pk=application.pk)


class WithdrawView(StudentRequiredMixin, View):
    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        application = own_application(_student(request), pk)
        context = {
            **shell_context(request, area="student"),
            "application": application,
            "cancel_url": reverse("applications:detail", args=[application.pk]),
        }
        return render(request, "applications/withdraw.html", context)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        application = own_application(_student(request), pk)
        try:
            services.withdraw_application(
                user=_student(request), application=application, request=request
            )
        except ValidationError as error:
            messages.error(request, _error_text(error))
            return redirect("applications:detail", pk=application.pk)
        messages.success(request, "Application withdrawn.")
        return redirect("applications:list")


class DocumentView(StudentRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int, requirement: int) -> HttpResponse:
        user = _student(request)
        application = own_application(user, pk)
        required = get_object_or_404(RequiredDocument, pk=requirement)
        form = DocumentForm(request.POST)
        try:
            if not form.is_valid():
                raise ValidationError(list(form.errors["file"]))
            services.attach_document(
                user=user,
                application=application,
                requirement=required,
                file_id=form.cleaned_data["file"],
                request=request,
            )
        except ValidationError as error:
            return render_detail(
                request, application, error_for=required, error=_error_text(error), status=400
            )
        messages.success(request, "Document saved.")
        target = reverse("applications:detail", args=[application.pk])
        return redirect(f"{target}#doc-{required.pk}")
