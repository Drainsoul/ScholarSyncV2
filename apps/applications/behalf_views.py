"""Staff screens for filing an application on a student's behalf."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import View

from apps.applications import behalf
from apps.applications.review_selectors import (
    MAX_TERM_ID,
    behalf_application,
    behalf_in_progress,
    filing_profiles,
)
from apps.applications.staff_views import PAGE_SIZE, _actor, _error_text
from apps.applications.views import APPLICATION_TONES
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context

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


class FilingView(ProgramStaffRequiredMixin, View):
    """The filing page itself arrives later; until then it only proves the lookup."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        behalf_application(self.program, pk)
        return HttpResponse(status=204)


class _StubPostView(ProgramStaffRequiredMixin, View):
    """A POST-only filing action whose behaviour arrives later."""

    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, pk: int, **kwargs: int) -> HttpResponse:
        behalf_application(self.program, pk)
        return redirect("review:behalf", program=self.program.slug, pk=pk)


class AcademicsView(_StubPostView):
    pass


class DocumentView(_StubPostView):
    pass


class SubmitView(_StubPostView):
    pass


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
