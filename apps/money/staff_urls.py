from django.urls import path

from . import staff_views

app_name = "money"

urlpatterns = [
    path("schedules/", staff_views.SchedulesView.as_view(), name="schedules"),
    path("schedules/new/", staff_views.ScheduleFormView.as_view(), name="schedule-new"),
    path("schedules/<int:pk>/", staff_views.ScheduleFormView.as_view(), name="schedule-edit"),
    path(
        "schedules/<int:pk>/publish/",
        staff_views.SchedulePublishView.as_view(),
        name="schedule-publish",
    ),
    path("disbursements/", staff_views.OverviewView.as_view(), name="overview"),
    path("disbursements/<int:schedule>/", staff_views.ScheduleView.as_view(), name="schedule"),
    path(
        "disbursements/<int:schedule>/generate/",
        staff_views.GenerateView.as_view(),
        name="generate",
    ),
    path("disbursements/<int:schedule>/bulk/", staff_views.BulkView.as_view(), name="bulk"),
    path(
        "disbursements/<int:schedule>/<int:pk>/reject/",
        staff_views.RejectView.as_view(),
        name="reject",
    ),
    path(
        "disbursements/<int:schedule>/<int:pk>/revert/",
        staff_views.RevertView.as_view(),
        name="revert",
    ),
    path("budget/", staff_views.BudgetView.as_view(), name="budget"),
    path("budget/edit/", staff_views.BudgetEditView.as_view(), name="budget-edit"),
]
