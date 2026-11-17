"""Reads for accounts: the office's list of staff and office accounts."""

from django.db.models import Prefetch, Q, QuerySet

from apps.programs.models import ProgramMembership

from .models import User


def staff_accounts(q: str = "") -> QuerySet[User]:
    """Staff and office accounts (never students), by name, with their memberships."""
    rows = User.objects.filter(role__in=[User.Role.STAFF, User.Role.SUPER_ADMIN])
    for word in q.split():
        rows = rows.filter(Q(full_name__icontains=word) | Q(email__icontains=word))
    return rows.order_by("full_name", "email").prefetch_related(
        Prefetch(
            "memberships",
            queryset=ProgramMembership.objects.select_related("program").order_by("program__name"),
        )
    )


def staff_account(pk: int) -> User | None:
    return staff_accounts().filter(pk=pk).first()
