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
]
