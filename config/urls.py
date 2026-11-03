from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("accounts/", include("allauth.urls")),
    path("_kit/", include("apps.kit.urls")),
]
