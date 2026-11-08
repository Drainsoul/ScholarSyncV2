from django.urls import path

from . import views

app_name = "workspace"

urlpatterns = [
    path("", views.NoProgramsView.as_view(), name="no_programs"),
    path("<slug:program>/", views.DashboardView.as_view(), name="dashboard"),
    path("<slug:program>/students/", views.StudentListView.as_view(), name="students"),
    path("<slug:program>/students/new/", views.StudentCreateView.as_view(), name="students-new"),
    path(
        "<slug:program>/students/<int:profile_id>/invite/",
        views.StudentInviteView.as_view(),
        name="students-invite",
    ),
]
