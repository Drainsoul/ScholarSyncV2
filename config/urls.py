from django.http import Http404, HttpRequest, HttpResponse
from django.urls import include, path

from apps.accounts.reauth import MfaReauthenticateView, ReauthenticateView, SessionListView
from apps.accounts.session_policy import keep_alive, status
from apps.accounts.theme import set_theme


def not_offered(request: HttpRequest) -> HttpResponse:
    """Google One Tap isn't used, and allauth's token route trusts the token header's `alg`
    (ASVS V9.1.2, V10.5.1): it answers 404 like any unknown page."""
    raise Http404("Not offered.")


urlpatterns = [
    path("", include("apps.core.urls")),
    path("programs/", include("apps.programs.urls")),
    path("me/match/", include("apps.matching.urls")),
    path("me/applications/", include("apps.applications.urls")),
    path("me/scholarships/", include("apps.awards.urls")),
    path("me/notifications/", include("apps.workspace.notification_urls")),
    path("", include("apps.workspace.support_urls")),
    path("me/", include("apps.students.urls")),
    path("staff/<slug:program>/applications/", include("apps.applications.staff_urls")),
    path("staff/<slug:program>/scholars/", include("apps.awards.staff_urls")),
    path("staff/<slug:program>/settings/", include("apps.programs.settings_urls")),
    path("staff/<slug:program>/reports/", include("apps.reports.staff_urls")),
    path("staff/<slug:program>/audit/", include("apps.core.audit_urls")),
    path(
        "staff/<slug:program>/notifications/",
        include("apps.workspace.staff_notification_urls"),
    ),
    path("staff/<slug:program>/", include("apps.money.staff_urls")),
    path("staff/", include("apps.workspace.urls")),
    path("office/", include("apps.office.urls")),
    path("files/", include("apps.files.urls")),
    path("accounts/claim/", include("apps.students.claim_urls")),
    path("accounts/google/login/token/", not_offered, name="google_login_by_token"),
    path("accounts/session/keep-alive/", keep_alive, name="session_keep_alive"),
    path("accounts/session/status/", status, name="session_status"),
    path("accounts/theme/", set_theme, name="theme_set"),
    path(
        "accounts/reauthenticate/",
        ReauthenticateView.as_view(),
        name="account_reauthenticate",
    ),
    path("accounts/sessions/", SessionListView.as_view(), name="usersessions_list"),
    path(
        "accounts/2fa/reauthenticate/",
        MfaReauthenticateView.as_view(),
        name="mfa_reauthenticate",
    ),
    path("accounts/", include("allauth.urls")),
    path("_kit/", include("apps.kit.urls")),
]
