from django.urls import path

from . import staff_views

app_name = "review"

urlpatterns = [
    path("", staff_views.QueueView.as_view(), name="queue"),
    path("<int:pk>/", staff_views.ReviewView.as_view(), name="detail"),
    path("<int:pk>/", staff_views.ReviewView.as_view(), name="detail"),
]
