"""The app shell for allauth's account pages (spec §12 rev 26): the session list, two-factor
setup and the other "manage" pages render in the signed-in user's own layout, with its sidebar,
instead of the sign-in layout. Other pages get nothing, so they pay no queries."""

from allauth.mfa.models import Authenticator
from django.conf import settings
from django.http import HttpRequest

from apps.accounts.models import User
from apps.core.shell import shell_context
from apps.programs.selectors import programs_for

MANAGE_PAGES = frozenset(
    {
        "usersessions_list",
        "mfa_index",
        "mfa_activate_totp",
        "mfa_deactivate_totp",
        "mfa_view_recovery_codes",
        "mfa_generate_recovery_codes",
        "account_email",
        "account_change_password",
        "account_set_password",
        "socialaccount_connections",
    }
)


def account_shell(request: HttpRequest) -> dict[str, object]:
    match = request.resolver_match
    user = getattr(request, "user", None)
    if match is None or match.url_name not in MANAGE_PAGES or not isinstance(user, User):
        return {}
    if user.is_super_admin:
        layout, shell = "layouts/office.html", shell_context(request, area="office")
    elif user.is_program_staff:
        program = programs_for(user).order_by("name").first()
        layout = "layouts/staff.html" if program is not None else "layouts/app.html"
        shell = shell_context(request, area="staff", program=program)
    else:
        layout, shell = "layouts/student.html", shell_context(request, area="student")
    context: dict[str, object] = {"account_layout": layout, **shell}
    if match.url_name == "mfa_index":
        context.update(_mfa_overview(user))
    return context


def _mfa_overview(user: User) -> dict[str, object]:
    """What the two-factor overview shows beyond allauth's context: whether this account must keep
    the app on, and how many recovery codes are left."""
    codes = Authenticator.objects.filter(user=user, type=Authenticator.Type.RECOVERY_CODES).first()
    total = left = 0
    if codes is not None:
        wrapped = codes.wrap()
        total, left = len(wrapped.generate_codes()), len(wrapped.get_unused_codes())
    return {
        "mfa_required": settings.MFA_REQUIRED_FOR_STAFF
        and (user.is_program_staff or user.is_super_admin),
        "codes_total": total,
        "codes_left": left,
        "codes_left_label": f"{left} of {total} left",
    }
