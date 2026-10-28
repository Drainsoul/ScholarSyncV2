from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("_kit/", include("apps.kit.urls")),
]
