"""The office's staff and office accounts (M11b). Account changes ask for the password again."""

from typing import Any

from allauth.account.decorators import reauthentication_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from apps.accounts import services
from apps.accounts.models import User
from apps.accounts.selectors import staff_account, staff_accounts
from apps.core.permissions import SuperAdminRequiredMixin
from apps.core.shell import shell_context

from .forms import AccountForm

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
        """Hook for the membership forms."""
        return {}


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


class StaffWelcomeView(SuperAdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        account = _account(pk)
        if account.last_login is None:
            services.send_welcome(actor=_actor(request), user=account)
            messages.success(request, "Email sent again.")
        return redirect("office:staff-detail", pk=account.pk)
