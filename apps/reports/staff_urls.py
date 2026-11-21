from django.urls import path

from . import staff_views

app_name = "reports"

urlpatterns = [
    path("", staff_views.ReportListView.as_view(), name="list"),
    path("new/", staff_views.ReportNewView.as_view(), name="new"),
    path("<int:pk>/", staff_views.ReportDetailView.as_view(), name="detail"),
    path(
        "<int:pk>/files/<int:file>/preview/",
        staff_views.ReportFilePreviewView.as_view(),
        name="file-preview",
    ),
    path("<int:pk>/resubmit/", staff_views.ReportResubmitView.as_view(), name="resubmit"),
    path("<int:pk>/approve/", staff_views.ReportApproveView.as_view(), name="approve"),
    path("<int:pk>/return/", staff_views.ReportReturnView.as_view(), name="return"),
    path("<int:pk>/send/", staff_views.ReportSendView.as_view(), name="send"),
]
