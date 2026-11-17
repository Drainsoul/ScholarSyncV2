from django.urls import path

from . import settings_views

app_name = "settings"

urlpatterns = [
    path("", settings_views.RulesView.as_view(), name="rules"),
]
