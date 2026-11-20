from django.urls import path

from . import task_views, views

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
    path("<slug:program>/tasks/", task_views.TaskListView.as_view(), name="tasks"),
    path("<slug:program>/tasks/new/", task_views.TaskCreateView.as_view(), name="task-new"),
    path("<slug:program>/tasks/<int:pk>/", task_views.TaskEditView.as_view(), name="task-edit"),
    path(
        "<slug:program>/tasks/<int:pk>/done/", task_views.TaskDoneView.as_view(), name="task-done"
    ),
    path(
        "<slug:program>/tasks/<int:pk>/delete/",
        task_views.TaskDeleteView.as_view(),
        name="task-delete",
    ),
]
