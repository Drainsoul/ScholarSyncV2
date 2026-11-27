"""The project's URLs plus the public demo's reset route, as config/urls.py adds it there."""

from django.urls import include, path

from config.urls import urlpatterns as project_urlpatterns

urlpatterns = [*project_urlpatterns, path("_demo/", include("apps.demo.urls"))]
