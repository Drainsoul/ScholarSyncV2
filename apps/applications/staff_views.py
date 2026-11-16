from datetime import date
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, QueryDict
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.generic import TemplateView, View

from apps.accounts.models import User
from apps.applications import review
from apps.applications.models import Application, Document, DocumentFile
from apps.applications.review_selectors import (
    DEFAULT_SORT,
    STATUS_FILTERS,
    applications_for_program,
    history,
    parse_queue_filters,
    queue,
    queue_position,
    staff_application,
)
from apps.applications.selectors import document_rows
from apps.applications.staff_forms import (
    APPROVE,
    RETURN,
    START_REVIEW,
    BulkForm,
    DecisionForm,
    DeclineForm,
)
from apps.applications.views import APPLICATION_TONES, DOCUMENT_TONES
from apps.awards.selectors import other_active_awards
from apps.core.htmx import HtmxHttpRequest, close_dialog, toast
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context
from apps.matching.checklist import CHECK_LABELS, snapshot_items
from apps.programs.models import AcademicTerm, Program

PAGE_SIZE = 25
TABLE_ID = "queue-table"
BULK_APPROVE_FILTERS = frozenset({"waiting", "under_review"})  # approval needs a review
QUEUE_KEYS = ("status", "term", "q", "sort", "page")
MAX_QUEUE_VALUE = 200


def queue_query(params: QueryDict) -> str:
    """The queue's own filter parameters, re-encoded: unknown keys and anything else are dropped."""
    kept = QueryDict(mutable=True)
    for key in QUEUE_KEYS:
        value = params.get(key, "")
        if value:
            kept[key] = value[:MAX_QUEUE_VALUE]
    return kept.urlencode()


class QueueView(ProgramStaffRequiredMixin, TemplateView):
    request: HtmxHttpRequest
    template_name = "review/queue.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        filters = parse_queue_filters(self.request.GET)
        paginator = Paginator(queue(self.program, filters), PAGE_SIZE)
        # get_page() turns ?page=abc or ?page=999 into a valid page instead of an error.
        page = paginator.get_page(self.request.GET.get("page"))
        terms = AcademicTerm.objects.filter(
            pk__in=applications_for_program(self.program).values("term_id")
        ).order_by("-sort_key")
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="staff", program=self.program),
            "page": page,
            "rows": [
                {"application": application, "tone": APPLICATION_TONES[application.status]}
                for application in page.object_list
            ],
            "filters": filters,
            "status_choices": [(key, label) for key, (label, _) in STATUS_FILTERS.items()],
            "terms": list(terms),
            "total": paginator.count,
            "default_sort": DEFAULT_SORT,
            # A valid ?sort= rides along with filter requests; the default needs no parameter.
            "sort": filters.sort if self.request.GET.get("sort") == filters.sort else "",
            "clear_url": reverse("review:queue", kwargs={"program": self.program.slug}),
            "can_approve": filters.status in BULK_APPROVE_FILTERS,
            # The no-JS bulk form posts this back, so its redirect lands on the same filters.
            "next_query": queue_query(self.request.GET),
        }

    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any) -> HttpResponse:
        htmx = self.request.htmx
        if htmx and htmx.target == TABLE_ID:
            context["count_oob"] = True
            response = TemplateResponse(self.request, f"{self.template_name}#queue_table", context)
        else:
            response = TemplateResponse(self.request, self.template_name, context)
        patch_vary_headers(response, ("HX-Request", "HX-Target"))
        return response


def _evaluated_on(snapshot: dict[str, Any]) -> date | None:
    try:
        return date.fromisoformat(str(snapshot.get("evaluated_on", "")))
    except ValueError:
        return None


def _hint(snapshot: dict[str, Any]) -> dict[str, str]:
    raw = snapshot.get("hint")
    if not isinstance(raw, dict):
        return {}
    return {"label": str(raw.get("label", "")), "reason": str(raw.get("reason", ""))}


def render_review(
    request: HttpRequest,
    program: Program,
    application: Application,
    *,
    decision_form: Any = None,
    error: str = "",
    status: int = 200,
) -> HttpResponse:
    """The review screen. The POST views reuse it to show an error or a bound form."""
    snapshot = application.match_snapshot if isinstance(application.match_snapshot, dict) else {}
    items = snapshot_items(snapshot)
    under_review = application.status == Application.Status.UNDER_REVIEW
    if under_review and decision_form is None:
        decision_form = DecisionForm(program=program, application=application)
    versions = dict(
        DocumentFile.objects.filter(document__application=application, is_current=True).values_list(
            "document_id", "version"
        )
    )
    doc_rows = document_rows(application)
    rows = [
        {
            "row": row,
            "tone": DOCUMENT_TONES[row.document.status] if row.document is not None else "neutral",
            "version": versions.get(row.document.pk, 1) if row.document is not None else 1,
        }
        for row in doc_rows
    ]
    filer = application.created_by
    overridden = snapshot.get("override") if application.on_behalf else None
    overrides = [
        CHECK_LABELS.get(code, code.replace("_", " ").capitalize())
        for code in (overridden if isinstance(overridden, list) else [])
        if isinstance(code, str)
    ]
    return render(
        request,
        "review/detail.html",
        {
            "filed_by": filer.full_name if filer is not None and filer.full_name else "staff",
            "overrides": overrides,
            **shell_context(request, area="staff", program=program),
            "program": program,
            "application": application,
            "profile": application.profile,
            "tone": APPLICATION_TONES[application.status],
            "position": queue_position(program, application),
            "other_awards": other_active_awards(application.profile, program),
            "document_rows": rows,
            "documents_total": len(rows),
            "documents_approved": sum(
                1
                for row in doc_rows
                if row.document is not None and row.document.status == Document.Status.APPROVED
            ),
            "under_review": under_review,
            "evaluated_on": _evaluated_on(snapshot),
            "checks": items,
            "rules_met": sum(1 for item in items if item["state"] == "met"),
            "rules_total": len(items),
            "hint": _hint(snapshot),
            "history": history(application),
            "decision_form": decision_form,
            "error": error,
        },
        status=status,
    )


class ReviewView(ProgramStaffRequiredMixin, View):
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        return render_review(request, self.program, staff_application(self.program, pk))


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)  # the staff mixin has signed them in
    return user


def _error_text(error: ValidationError) -> str:
    return " ".join(error.messages)


def _done(request: HttpRequest, program: Program, pk: int, message: str) -> HttpResponse:
    messages.success(request, message)
    return redirect("review:detail", program=program.slug, pk=pk)


class ReviewActionView(ProgramStaffRequiredMixin, View):
    """A POST that changes one application through a service, then goes back to the review page."""

    http_method_names = ["post", "options"]
    success_message = ""

    def act(self, request: HttpRequest, application: Application, **kwargs: int) -> None:
        raise NotImplementedError

    def post(self, request: HttpRequest, program: str, pk: int, **kwargs: int) -> HttpResponse:
        application = staff_application(self.program, pk)  # another program's id is a 404
        try:
            self.act(request, application, **kwargs)
        except ValidationError as error:  # InvalidTransition is one too; Http404 is not caught
            return self.fail(request, pk, _error_text(error))
        return _done(request, self.program, pk, self.success_message)

    def fail(self, request: HttpRequest, pk: int, error: str) -> HttpResponse:
        # A fresh read: the state the staff member sees must be the state that refused them.
        fresh = staff_application(self.program, pk)
        return render_review(request, self.program, fresh, error=error, status=400)


class StartReviewView(ReviewActionView):
    success_message = "Review started."

    def act(self, request: HttpRequest, application: Application, **kwargs: int) -> None:
        review.start_review(
            actor=_actor(request), program=self.program, application=application, request=request
        )


class ApproveDocumentView(ReviewActionView):
    success_message = "Document approved."

    def act(self, request: HttpRequest, application: Application, **kwargs: int) -> None:
        review.approve_document(
            actor=_actor(request),
            program=self.program,
            application=application,
            document_id=kwargs["document"],
            request=request,
        )


class DecideView(ReviewActionView):
    def post(self, request: HttpRequest, program: str, pk: int, **kwargs: int) -> HttpResponse:
        application = staff_application(self.program, pk)
        form = DecisionForm(request.POST, program=self.program, application=application)
        if not form.is_valid():
            moved = application.status != Application.Status.UNDER_REVIEW
            return render_review(
                request,
                self.program,
                application,
                decision_form=form,
                error="This application is no longer under review." if moved else "",
                status=400,
            )
        decision = form.cleaned_data["decision"]
        reason = form.cleaned_data["reason"]
        common: dict[str, Any] = {
            "actor": _actor(request),
            "program": self.program,
            "application": application,
            "request": request,
        }
        try:
            if decision == APPROVE:
                review.approve_application(**common, tier=form.cleaned_data["tier"], note=reason)
                message = "Application approved. The award has been created."
            elif decision == RETURN:
                review.return_application(**common, reason=reason)
                message = "Application returned to the student."
            else:
                review.reject_application(**common, reason=reason)
                message = "Application not approved."
        except ValidationError as error:
            return self.fail(request, pk, _error_text(error))
        return _done(request, self.program, pk, message)


class DeclineDocumentView(ProgramStaffRequiredMixin, View):
    request: HtmxHttpRequest
    http_method_names = ["get", "post", "options"]

    def _render(
        self, request: HtmxHttpRequest, application: Application, document: Document, form: Any
    ) -> HttpResponse:
        dialog = bool(request.htmx)
        response = render(
            request,
            "review/decline_dialog.html" if dialog else "review/decline_document.html",
            {
                **shell_context(request, area="staff", program=self.program),
                "program": self.program,
                "application": application,
                "document": document,
                "requirement": document.requirement,
                "form": form,
                "dialog": dialog,
            },
        )
        patch_vary_headers(response, ("HX-Request",))
        return response

    def _document(self, application: Application, document: int) -> Document:
        found = (
            Document.objects.select_related("requirement")
            .filter(pk=document, application=application)
            .first()
        )
        if found is None:
            raise Http404("No such document.")
        return found

    def get(self, request: HtmxHttpRequest, program: str, pk: int, document: int) -> HttpResponse:
        application = staff_application(self.program, pk)
        found = self._document(application, document)
        return self._render(request, application, found, DeclineForm())

    def post(self, request: HtmxHttpRequest, program: str, pk: int, document: int) -> HttpResponse:
        application = staff_application(self.program, pk)
        found = self._document(application, document)
        form = DeclineForm(request.POST)
        if form.is_valid():
            try:
                review.decline_document(
                    actor=_actor(request),
                    program=self.program,
                    application=application,
                    document_id=document,
                    reason=form.cleaned_data["reason"],
                    request=request,
                )
            except ValidationError as error:
                form.add_error(None, _error_text(error))
            else:
                if request.htmx:
                    # The reload below would destroy a toast; the queued message shows after it.
                    messages.success(request, "Document declined.")
                    response = close_dialog(HttpResponse(status=204))
                    response["HX-Refresh"] = "true"
                    return response
                return _done(request, self.program, pk, "Document declined.")
        return self._render(request, application, found, form)


def _plural(count: int) -> str:
    return f"{count} application{'s' if count != 1 else ''}"


class BulkView(ProgramStaffRequiredMixin, View):
    """Start review of, or approve, the ticked rows; refused rows are reported, not fatal."""

    request: HtmxHttpRequest
    http_method_names = ["post", "options"]

    def _back(self, request: HtmxHttpRequest) -> HttpResponse:
        """The queue, with the filters the form came from. The posted value is parsed as a
        querystring and only the queue's keys are re-encoded, so it can never name another URL."""
        url = reverse("review:queue", kwargs={"program": self.program.slug})
        posted = request.POST.get("next_query", "")[: len(QUEUE_KEYS) * (MAX_QUEUE_VALUE + 16)]
        query = queue_query(QueryDict(posted))
        return HttpResponseRedirect(f"{url}?{query}" if query else url)

    def _warn(self, request: HtmxHttpRequest, text: str) -> HttpResponse:
        if request.htmx:  # nothing reloads, so a toast survives
            return toast(HttpResponse(status=204), text, "warning")
        messages.warning(request, text)
        return self._back(request)

    def post(self, request: HtmxHttpRequest, program: str) -> HttpResponse:
        form = BulkForm(request.POST)
        if not form.is_valid():
            return self._warn(request, str(next(iter(form.errors.values()))[0]))
        action = form.cleaned_data["action"]
        try:
            result = review.bulk_action(
                actor=_actor(request),
                program=self.program,
                action="start_review" if action == START_REVIEW else "approve",
                ids=form.cleaned_data["ids"],
                request=request,
            )
        except ValidationError as error:
            return self._warn(request, _error_text(error))
        verb = "Started review of" if action == START_REVIEW else "Approved"
        text = f"{verb} {_plural(result.done)}."
        if result.skipped:
            text += f" Skipped {len(result.skipped)}."
            messages.warning(request, text)
        else:
            messages.success(request, text)
        for name, reason in result.skipped:
            messages.warning(request, f"{name}: {reason}" if name else reason)
        if request.htmx:
            # Queued, not toasted: the reload would destroy a toast; base.html shows these after it.
            response = HttpResponse(status=204)
            response["HX-Refresh"] = "true"
            return response
        return self._back(request)
