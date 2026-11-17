from typing import Any

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.core.permissions import StudentRequiredMixin
from apps.core.shell import shell_context

from . import selectors, services

PAGE_SIZE = 25


def _user(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


class NotificationListView(StudentRequiredMixin, TemplateView):
    template_name = "workspace/notifications.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = shell_context(self.request, area="student")
        page = Paginator(selectors.notifications_for(_user(self.request)), PAGE_SIZE).get_page(
            self.request.GET.get("page")
        )
        return {
            **super().get_context_data(**kwargs),
            **context,
            "page": page,
            "has_unread": bool(context.get("notifications_count")),
        }


class OpenNotificationView(StudentRequiredMixin, View):
    """Mark one notification read and follow it; a link that leaves the site goes nowhere."""

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        row = services.mark_read(user=_user(request), pk=pk)
        safe = row.url and url_has_allowed_host_and_scheme(
            row.url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        )
        return redirect(row.url if safe else reverse("notifications:list"))


class MarkAllReadView(StudentRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest) -> HttpResponse:
        services.mark_all_read(user=_user(request))
        return redirect("notifications:list")
