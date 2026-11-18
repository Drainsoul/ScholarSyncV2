"""The office's staff and office accounts (M11b). Account changes ask for the password again."""

from typing import Any

from allauth.account.decorators import reauthentication_required
from allauth.mfa.models import Authenticator
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from apps.accounts import services
from apps.accounts.models import User
from apps.accounts.selectors import staff_account, staff_accounts
from apps.core.permissions import SuperAdminRequiredMixin
from apps.core.shell import shell_context
from apps.programs import services as programs
from apps.programs.models import ProgramMembership

from .forms import AccountForm, MembershipForm

PAGE_SIZE = 25


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


def _account(pk: int) -> User:
    account = staff_account(pk)
    if account is None:
        raise Http404("No such staff or office account.")
    return account


class StaffListView(SuperAdminRequiredMixin, View):
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest) -> HttpResponse:
        q = request.GET.get("q", "").replace("\x00", "").strip()[:200]
        page = Paginator(staff_accounts(q), PAGE_SIZE).get_page(request.GET.get("page"))
        context: dict[str, Any] = {**shell_context(request, area="office"), "page": page, "q": q}
        return render(request, "office/staff/list.html", context)


@method_decorator(reauthentication_required, name="post")
class StaffNewView(SuperAdminRequiredMixin, View):
    def _render(self, request: HttpRequest, form: AccountForm) -> HttpResponse:
        context = {**shell_context(request, area="office"), "form": form}
        return render(request, "office/staff/new.html", context)

    def get(self, request: HttpRequest) -> HttpResponse:
        return self._render(request, AccountForm(initial={"role": User.Role.STAFF}))

    def post(self, request: HttpRequest) -> HttpResponse:
        form = AccountForm(request.POST)
        if not form.is_valid():
            return self._render(request, form)
        try:
            account = services.create_account(
                actor=_actor(request),
                email=form.cleaned_data["email"],
                full_name=form.cleaned_data["full_name"],
                role=User.Role(form.cleaned_data["role"]),
                request=request,
            )
        except ValidationError as error:
            for field, problems in error.message_dict.items():
                form.add_error(field if field in form.fields else None, problems)
            return self._render(request, form)
        messages.success(
            request, f"Account created. We emailed {account.email} a link to set a password."
        )
        return redirect("office:staff-detail", pk=account.pk)


class StaffDetailView(SuperAdminRequiredMixin, View):
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        account = _account(pk)
        context: dict[str, Any] = {
            **shell_context(request, area="office"),
            "account": account,
            "memberships": list(account.memberships.all()),
            "is_self": account.pk == request.user.pk,
        }
        context.update(self.extra_context(request, account))
        return render(request, "office/staff/detail.html", context)

    def extra_context(self, request: HttpRequest, account: User) -> dict[str, Any]:
        return {
            "membership_form": MembershipForm(),
            "has_mfa": Authenticator.objects.filter(user=account).exists(),
            "levels": ProgramMembership.Level.choices,
        }


@method_decorator(reauthentication_required, name="post")
class StaffActiveView(SuperAdminRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        account = _account(pk)
        active = request.POST.get("active") == "1"
        try:
            services.set_account_active(
                actor=_actor(request), user=account, active=active, request=request
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Account reactivated." if active else "Account deactivated.")
        return redirect("office:staff-detail", pk=account.pk)


@method_decorator(reauthentication_required, name="post")
class StaffMfaView(SuperAdminRequiredMixin, View):
    """Remove an account's two-factor sign-in (a lost phone); asks for the password again."""

    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        account = _account(pk)
        try:
            services.remove_mfa(actor=_actor(request), user=account, request=request)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(
                request, "Two-factor sign-in removed. They set it up again at their next sign-in."
            )
        return redirect("office:staff-detail", pk=account.pk)


class StaffWelcomeView(SuperAdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        account = _account(pk)
        if account.last_login is None:
            services.send_welcome(actor=_actor(request), user=account)
            messages.success(request, "Email sent again.")
        return redirect("office:staff-detail", pk=account.pk)


@method_decorator(reauthentication_required, name="post")
class MembershipAddView(SuperAdminRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        account = _account(pk)
        form = MembershipForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Pick a program and a level.")
            return redirect("office:staff-detail", pk=account.pk)
        program = form.cleaned_data["program"]
        try:
            programs.add_membership(
                actor=_actor(request),
                user=account,
                program=program,
                level=ProgramMembership.Level(form.cleaned_data["level"]),
                request=request,
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, f"Added to {program.name}.")
        return redirect("office:staff-detail", pk=account.pk)


@method_decorator(reauthentication_required, name="post")
class MembershipChangeView(SuperAdminRequiredMixin, View):
    """Change a membership's level (`level=`) or remove it (`remove=1`)."""

    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        membership = get_object_or_404(
            ProgramMembership.objects.select_related("program", "user"), pk=pk
        )
        account, program = membership.user, membership.program
        if request.POST.get("remove") == "1":
            programs.remove_membership(
                actor=_actor(request), membership=membership, request=request
            )
            messages.success(request, f"Removed from {program.name}.")
            return redirect("office:staff-detail", pk=account.pk)
        level = request.POST.get("level", "")
        if level not in ProgramMembership.Level.values:
            messages.error(request, "Pick a level.")
            return redirect("office:staff-detail", pk=account.pk)
        changed = programs.change_membership(
            actor=_actor(request),
            membership=membership,
            level=ProgramMembership.Level(level),
            request=request,
        )
        messages.success(request, f"Now {changed.get_level_display()} in {program.name}.")
        return redirect("office:staff-detail", pk=account.pk)
