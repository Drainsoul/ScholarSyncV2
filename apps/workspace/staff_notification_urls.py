from django.urls import path

from . import notification_views

app_name = "notifications-staff"

urlpatterns = [
    path("", notification_views.StaffNotificationListView.as_view(), name="list"),
    path("read/", notification_views.StaffMarkAllReadView.as_view(), name="read-all"),
    path("<int:pk>/", notification_views.StaffOpenNotificationView.as_view(), name="open"),
]
