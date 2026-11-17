from typing import Any
from urllib.parse import quote

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import models
from django.http import Http404, HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.views import View
from django.views.defaults import page_not_found
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.core.permissions import StudentRequiredMixin
from apps.core.shell import shell_context
from apps.students import services
from apps.students.dashboard import student_dashboard
from apps.students.forms import ClaimForm, EducationForm, FamilyMemberForm, PersonalForm, PhotoForm
from apps.students.models import EducationRecord, FamilyMember, ProfileInvite
from apps.students.selectors import (
    claim_problem,
    education_for,
    family_for,
    find_invite,
    mask_email,
    own_education_record,
    own_family_member,
    profile_for,
    profile_page,
)


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
        user = _student(self.request)
        _, completion = profile_page(user)
        missing = next((section for section in completion.sections if not section.done), None)
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="student"),
            "completion": completion,
            "next_section": missing.label if missing is not None else "",
            "board": student_dashboard(user, today=timezone.localdate()),
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


class PhotoView(StudentRequiredMixin, View):
    template_name = "students/profile/photo.html"

    def _render(self, request: HttpRequest, form: PhotoForm, status: int = 200) -> HttpResponse:
        profile = profile_for(_student(request))
        photo = profile.photo if profile else None
        context = {**shell_context(request, area="student"), "form": form, "photo": photo}
        return render(request, self.template_name, context, status=status)

    def get(self, request: HttpRequest) -> HttpResponse:
        return self._render(request, PhotoForm(user=_student(request)))

    def post(self, request: HttpRequest) -> HttpResponse:
        user = _student(request)
        if request.POST.get("action") == "remove":
            services.remove_photo(user=user)
            messages.success(request, "Photo removed.")
            return redirect("students:profile-photo")
        form = PhotoForm(request.POST, user=user)
        if not form.is_valid():
            return self._render(request, form)
        services.set_photo(user=user, file=form.cleaned_data["photo"])
        messages.success(request, "Photo saved.")
        return redirect("students:profile")


class FamilyListView(StudentRequiredMixin, TemplateView):
    template_name = "students/profile/family.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        profile = profile_for(_student(self.request))
        members = list(family_for(profile)) if profile else []
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="student"),
            "members": members,
        }


class FamilyFormView(StudentRequiredMixin, View):
    """Add (no pk) or edit one of the student's own family rows."""

    template_name = "students/profile/family_form.html"

    def _render(
        self, request: HttpRequest, form: FamilyMemberForm, member: FamilyMember | None
    ) -> HttpResponse:
        context = {**shell_context(request, area="student"), "form": form, "member": member}
        return render(request, self.template_name, context)

    def get(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        member = own_family_member(_student(request), pk) if pk is not None else None
        form = FamilyMemberForm(initial=_initial(member, services.FAMILY_FIELDS))
        return self._render(request, form, member)

    def post(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        user = _student(request)
        member = own_family_member(user, pk) if pk is not None else None
        form = FamilyMemberForm(request.POST)
        if not form.is_valid():
            return self._render(request, form, member)
        if member is None:
            services.add_family_member(user=user, data=form.cleaned_data)
            messages.success(request, "Family member added.")
        else:
            services.update_family_member(user=user, member=member, data=form.cleaned_data)
            messages.success(request, "Family member updated.")
        return redirect("students:profile-family")


class FamilyDeleteView(StudentRequiredMixin, View):
    template_name = "students/profile/confirm_delete.html"

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        member = own_family_member(_student(request), pk)
        context = {
            **shell_context(request, area="student"),
            "heading": "Remove family member",
            "what": f"{member.get_relation_display()}: {member.name}",
            "cancel_url": reverse("students:profile-family"),
        }
        return render(request, self.template_name, context)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        user = _student(request)
        services.remove_family_member(user=user, member=own_family_member(user, pk))
        messages.success(request, "Family member removed.")
        return redirect("students:profile-family")


class EducationListView(StudentRequiredMixin, TemplateView):
    template_name = "students/profile/education.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        profile = profile_for(_student(self.request))
        records = list(education_for(profile)) if profile else []
        return {
            **super().get_context_data(**kwargs),
            **shell_context(self.request, area="student"),
            "records": records,
        }


class EducationFormView(StudentRequiredMixin, View):
    """Add (no pk) or edit one of the student's own education rows."""

    template_name = "students/profile/education_form.html"

    def _render(
        self, request: HttpRequest, form: EducationForm, record: EducationRecord | None
    ) -> HttpResponse:
        context = {**shell_context(request, area="student"), "form": form, "record": record}
        return render(request, self.template_name, context)

    def get(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        record = own_education_record(_student(request), pk) if pk is not None else None
        initial = _initial(record, services.EDUCATION_FIELDS)
        if record is not None:
            initial["school"] = record.school_id
        return self._render(request, EducationForm(initial=initial), record)

    def post(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        user = _student(request)
        record = own_education_record(user, pk) if pk is not None else None
        form = EducationForm(request.POST)
        if not form.is_valid():
            return self._render(request, form, record)
        if record is None:
            services.add_education(user=user, data=form.cleaned_data)
            messages.success(request, "School added.")
        else:
            services.update_education(user=user, record=record, data=form.cleaned_data)
            messages.success(request, "School updated.")
        return redirect("students:profile-education")


class EducationDeleteView(StudentRequiredMixin, View):
    template_name = "students/profile/confirm_delete.html"

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        record = own_education_record(_student(request), pk)
        context = {
            **shell_context(request, area="student"),
            "heading": "Remove school",
            "what": f"{record.get_level_display()}: {record.school or record.school_name}",
            "cancel_url": reverse("students:profile-education"),
        }
        return render(request, self.template_name, context)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        user = _student(request)
        services.remove_education(user=user, record=own_education_record(user, pk))
        messages.success(request, "School removed.")
        return redirect("students:profile-education")


def _initial(instance: models.Model | None, fields: tuple[str, ...]) -> dict[str, Any]:
    if instance is None:
        return {}
    return {name: getattr(instance, name) for name in fields}


class ClaimView(View):
    """Open a staff-created profile from an emailed link. The path carries a secret token.

    Every response (the 404 too) is never cached and sends only the site's origin as Referrer,
    never the path, so the token cannot leak through a shared cache or to a page the user
    opens from here. Not "no-referrer": that makes the browser send "Origin: null" on the
    form POST, and Django's CSRF check then refuses the claim.
    """

    template_name = "students/claim.html"

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        response = super().dispatch(request, *args, **kwargs)
        add_never_cache_headers(response)
        response["Referrer-Policy"] = "strict-origin"
        return response

    def _render(
        self, request: HttpRequest, invite: ProfileInvite, form: ClaimForm, problem: str | None
    ) -> HttpResponse:
        context = {
            "invite": invite,
            "masked_email": mask_email(invite.email),
            "form": form,
            "problem": problem,
            "claim_path": quote(request.path, safe="/"),
        }
        return render(request, self.template_name, context)

    def get(self, request: HttpRequest, token: str) -> HttpResponse:
        invite = find_invite(token)
        if invite is None:
            return page_not_found(request, Http404("No such link."))
        problem = (
            claim_problem(invite, _student(request)) if request.user.is_authenticated else None
        )
        return self._render(request, invite, ClaimForm(), problem)

    def post(self, request: HttpRequest, token: str) -> HttpResponse:
        invite = find_invite(token)
        if invite is None:
            return page_not_found(request, Http404("No such link."))
        if not request.user.is_authenticated:
            return self._render(request, invite, ClaimForm(), None)
        user = _student(request)
        problem = claim_problem(invite, user)
        form = ClaimForm(request.POST)
        if problem is not None or not form.is_valid():
            return self._render(request, invite, form, problem)
        try:
            services.claim_profile(user=user, token=token, request=request)
        except ValidationError as error:
            return self._render(request, invite, form, " ".join(error.messages))
        messages.success(request, "Profile claimed. Check that your details are right.")
        return redirect("students:profile")
