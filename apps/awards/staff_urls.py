from django.urls import path

from . import staff_views

app_name = "scholars"

urlpatterns = [
    path("", staff_views.ScholarListView.as_view(), name="list"),
]
