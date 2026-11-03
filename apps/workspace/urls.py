from django.urls import path

from . import views

app_name = "workspace"

urlpatterns = [
    path("", views.NoProgramsView.as_view(), name="no_programs"),
    path("<slug:program>/", views.DashboardView.as_view(), name="dashboard"),
]
