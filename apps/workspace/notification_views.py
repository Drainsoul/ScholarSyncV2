"""Notification centres: one list, open and mark-all-read for each area (student, staff, office).

The staff centre lists every notification of the user; the program in its URL only picks the
layout (a `Notification` has no program)."""

from typing import Any, ClassVar

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.core.permissions import (
    ProgramStaffRequiredMixin,
    StudentRequiredMixin,
    SuperAdminRequiredMixin,
)
from apps.core.shell import shell_context

from . import selectors, services

PAGE_SIZE = 25

LAYOUTS = {
    "student": "layouts/student.html",
    "staff": "layouts/staff.html",
    "office": "layouts/office.html",
}


def _user(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


class _Area:
    """What differs per area: the layout, the shell and the URL names."""

    area: ClassVar[str]
    request: HttpRequest
    kwargs: dict[str, Any]

    def _names(self) -> dict[str, str]:
        if self.area == "student":
            return {
                "list": "notifications:list",
                "open": "notifications:open",
                "read": "notifications:read-all",
            }
        if self.area == "staff":
            return {
                "list": "notifications-staff:list",
                "open": "notifications-staff:open",
                "read": "notifications-staff:read-all",
            }
        return {
            "list": "office:notifications",
            "open": "office:notification-open",
            "read": "office:notifications-read",
        }

    def _url_kwargs(self) -> dict[str, str]:
        return {"program": self.kwargs["program"]} if self.area == "staff" else {}

    def list_url(self) -> str:
        return reverse(self._names()["list"], kwargs=self._url_kwargs())

    def shell(self) -> dict[str, object]:
        program = getattr(self, "program", None)
        return shell_context(self.request, area=self.area, program=program)


class NotificationListBase(_Area, TemplateView):
    template_name = "workspace/notifications.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = self.shell()
        page = Paginator(selectors.notifications_for(_user(self.request)), PAGE_SIZE).get_page(
            self.request.GET.get("page")
        )
        names = self._names()
        url_kwargs = self._url_kwargs()
        return {
            **super().get_context_data(**kwargs),
            **context,
            "layout": LAYOUTS[self.area],
            "page": page,
            "rows": [
                (item, reverse(names["open"], kwargs={**url_kwargs, "pk": item.pk}))
                for item in page.object_list
            ],
            "has_unread": bool(context.get("notifications_count")),
            "read_all_url": reverse(names["read"], kwargs=url_kwargs),
        }


class OpenNotificationBase(_Area, View):
    """Mark one notification read and follow it; a link that leaves the site goes to the list."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, pk: int, **kwargs: Any) -> HttpResponse:
        row = services.mark_read(user=_user(request), pk=pk)
        safe = row.url and url_has_allowed_host_and_scheme(
            row.url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        )
        return redirect(row.url if safe else self.list_url())


class MarkAllReadBase(_Area, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        services.mark_all_read(user=_user(request))
        return redirect(self.list_url())


class NotificationListView(StudentRequiredMixin, NotificationListBase):
    area = "student"


class OpenNotificationView(StudentRequiredMixin, OpenNotificationBase):
    area = "student"


class MarkAllReadView(StudentRequiredMixin, MarkAllReadBase):
    area = "student"


class StaffNotificationListView(ProgramStaffRequiredMixin, NotificationListBase):
    area = "staff"


class StaffOpenNotificationView(ProgramStaffRequiredMixin, OpenNotificationBase):
    area = "staff"


class StaffMarkAllReadView(ProgramStaffRequiredMixin, MarkAllReadBase):
    area = "staff"


class OfficeNotificationListView(SuperAdminRequiredMixin, NotificationListBase):
    area = "office"


class OfficeOpenNotificationView(SuperAdminRequiredMixin, OpenNotificationBase):
    area = "office"


class OfficeMarkAllReadView(SuperAdminRequiredMixin, MarkAllReadBase):
    area = "office"
