"""The office's schools (M11b): list, add and edit. No delete: applications point to them."""

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.accounts.models import User
from apps.core.permissions import SuperAdminRequiredMixin
from apps.core.shell import shell_context
from apps.programs import services
from apps.programs.models import School

from .forms import SchoolForm

PAGE_SIZE = 25


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


class SchoolListView(SuperAdminRequiredMixin, View):
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest) -> HttpResponse:
        q = request.GET.get("q", "").replace("\x00", "").strip()[:200]
        rows = School.objects.order_by("name")
        for word in q.split():
            rows = rows.filter(name__icontains=word)
        page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))
        context: dict[str, Any] = {**shell_context(request, area="office"), "page": page, "q": q}
        return render(request, "office/schools/list.html", context)


class _SchoolFormView(SuperAdminRequiredMixin, View):
    def _render(
        self, request: HttpRequest, form: SchoolForm, school: School | None
    ) -> HttpResponse:
        context = {**shell_context(request, area="office"), "form": form, "school": school}
        return render(request, "office/schools/form.html", context)

    def _save(self, request: HttpRequest, school: School | None) -> HttpResponse:
        form = SchoolForm(request.POST)
        if not form.is_valid():
            return self._render(request, form, school)
        try:
            services.save_school(
                actor=_actor(request), school=school, request=request, **form.cleaned_data
            )
        except ValidationError as error:
            for field, problems in error.message_dict.items():
                form.add_error(field if field in form.fields else None, problems)
            return self._render(request, form, school)
        messages.success(request, "School saved." if school else "School added.")
        return redirect("office:schools")


class SchoolNewView(_SchoolFormView):
    def get(self, request: HttpRequest) -> HttpResponse:
        return self._render(request, SchoolForm(), None)

    def post(self, request: HttpRequest) -> HttpResponse:
        return self._save(request, None)


class SchoolEditView(_SchoolFormView):
    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        school = get_object_or_404(School, pk=pk)
        initial = {
            "name": school.name,
            "type": school.type,
            "grading_scale": school.grading_scale,
            "is_in_taguig": school.is_in_taguig,
        }
        return self._render(request, SchoolForm(initial=initial), school)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        return self._save(request, get_object_or_404(School, pk=pk))
