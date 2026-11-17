from django.urls import path

from . import notification_views

app_name = "notifications"

urlpatterns = [
    path("", notification_views.NotificationListView.as_view(), name="list"),
    path("read/", notification_views.MarkAllReadView.as_view(), name="read-all"),
    path("<int:pk>/", notification_views.OpenNotificationView.as_view(), name="open"),
]
