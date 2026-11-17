from django.urls import path

from . import student_views

app_name = "notifications"

urlpatterns = [
    path("", student_views.NotificationListView.as_view(), name="list"),
    path("read/", student_views.MarkAllReadView.as_view(), name="read-all"),
    path("<int:pk>/", student_views.OpenNotificationView.as_view(), name="open"),
]
