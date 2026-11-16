from django.urls import path

from . import staff_views

app_name = "scholars"

urlpatterns = [
    path("", staff_views.ScholarListView.as_view(), name="list"),
    path("<int:pk>/", staff_views.ScholarDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", staff_views.ScholarEditView.as_view(), name="edit"),
    path("<int:pk>/status/", staff_views.ScholarStatusView.as_view(), name="status"),
]
