from typing import Any, ClassVar, cast

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404

from apps.accounts.models import User
from apps.programs.models import Program, ProgramMembership
from apps.programs.selectors import membership_for


class _RoleRequiredMixin:
    """Anonymous visitors go to sign in; the wrong role gets the 403 page."""

    allowed_roles: ClassVar[tuple[str, ...]] = ()

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if request.user.role not in self.allowed_roles:
            raise PermissionDenied
        return cast(HttpResponse, super().dispatch(request, *args, **kwargs))  # type: ignore[misc]


class StudentRequiredMixin(_RoleRequiredMixin):
    allowed_roles = (User.Role.STUDENT,)


class SuperAdminRequiredMixin(_RoleRequiredMixin):
    allowed_roles = (User.Role.SUPER_ADMIN,)


class ProgramStaffRequiredMixin:
    """Staff of the program in the URL, or the scholarship office.

    Order: sign in, role, program exists and is active (404), membership and level (403).
    Sets `self.program`, and `self.membership` (None for the office).
    """

    level: ClassVar[ProgramMembership.Level] = ProgramMembership.Level.STAFF
    program: Program
    membership: ProgramMembership | None

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (user.is_program_staff or user.is_super_admin):
            raise PermissionDenied
        self.program = get_object_or_404(Program, slug=kwargs.get("program"), is_active=True)
        if user.is_super_admin:
            self.membership = None
        else:
            self.membership = membership_for(user, self.program)
            if self.membership is None:
                raise PermissionDenied
            if (
                self.level == ProgramMembership.Level.HEAD
                and self.membership.level != ProgramMembership.Level.HEAD
            ):
                raise PermissionDenied
        return cast(HttpResponse, super().dispatch(request, *args, **kwargs))  # type: ignore[misc]
