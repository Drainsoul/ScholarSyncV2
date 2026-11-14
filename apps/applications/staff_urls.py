from django.urls import path

from . import staff_views

app_name = "review"

urlpatterns = [
    path("", staff_views.QueueView.as_view(), name="queue"),
]
