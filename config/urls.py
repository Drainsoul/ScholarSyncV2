from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("programs/", include("apps.programs.urls")),
    path("me/match/", include("apps.matching.urls")),
    path("me/applications/", include("apps.applications.urls")),
    path("me/scholarships/", include("apps.awards.urls")),
    path("me/", include("apps.students.urls")),
    path("staff/<slug:program>/applications/", include("apps.applications.staff_urls")),
    path("staff/<slug:program>/scholars/", include("apps.awards.staff_urls")),
    path("staff/", include("apps.workspace.urls")),
    path("office/", include("apps.office.urls")),
    path("files/", include("apps.files.urls")),
    path("accounts/claim/", include("apps.students.claim_urls")),
    path("accounts/", include("allauth.urls")),
    path("_kit/", include("apps.kit.urls")),
]
