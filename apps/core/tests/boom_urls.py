"""A URLconf with one view that fails, for the 500-page header test."""

from django.http import HttpRequest, HttpResponse
from django.urls import include, path


def boom(request: HttpRequest) -> HttpResponse:
    raise RuntimeError("A test failure.")


urlpatterns = [path("boom/", boom), path("", include("config.urls"))]
