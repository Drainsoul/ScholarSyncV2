from django.urls import path

from . import staff_views

app_name = "reports"

urlpatterns = [
    path("", staff_views.ReportListView.as_view(), name="list"),
    path("new/", staff_views.ReportNewView.as_view(), name="new"),
    path("<int:pk>/", staff_views.ReportDetailView.as_view(), name="detail"),
    path("<int:pk>/resubmit/", staff_views.ReportResubmitView.as_view(), name="resubmit"),
]
