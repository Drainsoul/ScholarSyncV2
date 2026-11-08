from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.core.permissions import StudentRequiredMixin
from apps.core.shell import shell_context
from apps.students import services
from apps.students.forms import PersonalForm
from apps.students.selectors import profile_page


def _student(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


def _url_or_none(url_name: str) -> str | None:
    """A section's edit page, or None until its screen exists."""
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return None


class HomeView(StudentRequiredMixin, TemplateView):
    template_name = "students/home.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        _, completion = profile_page(_student(self.request))
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="student"),
            "completion": completion,
        }


class ProfileView(StudentRequiredMixin, TemplateView):
    template_name = "students/profile/overview.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        _, completion = profile_page(_student(self.request))
        sections = [
            {"section": section, "edit_url": _url_or_none(section.url_name)}
            for section in completion.sections
        ]
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="student"),
            "completion": completion,
            "sections": sections,
        }


class PersonalView(StudentRequiredMixin, View):
    template_name = "students/profile/personal.html"

    def _render(self, request: HttpRequest, form: PersonalForm, status: int = 200) -> HttpResponse:
        context = {**shell_context(request, area="student"), "form": form}
        return render(request, self.template_name, context, status=status)

    def get(self, request: HttpRequest) -> HttpResponse:
        profile, _ = profile_page(_student(request))
        return self._render(request, PersonalForm(instance=profile))

    def post(self, request: HttpRequest) -> HttpResponse:
        profile, _ = profile_page(_student(request))
        form = PersonalForm(request.POST, instance=profile)
        if not form.is_valid():
            return self._render(request, form, status=200)
        services.ensure_profile(user=_student(request))
        services.update_personal(user=_student(request), data=form.cleaned_data)
        messages.success(request, "Personal details saved.")
        return redirect("students:profile")
