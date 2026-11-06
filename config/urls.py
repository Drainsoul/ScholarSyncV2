from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("me/", include("apps.students.urls")),
    path("staff/", include("apps.workspace.urls")),
    path("office/", include("apps.office.urls")),
    path("files/", include("apps.files.urls")),
    path("accounts/", include("allauth.urls")),
    path("_kit/", include("apps.kit.urls")),
]
