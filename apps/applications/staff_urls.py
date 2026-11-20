from django.urls import path

from . import behalf_views, staff_views

app_name = "review"

urlpatterns = [
    path("", staff_views.QueueView.as_view(), name="queue"),
    path("bulk/", staff_views.BulkView.as_view(), name="bulk"),
    path("new/", behalf_views.NewView.as_view(), name="behalf-new"),
    path("behalf/<int:pk>/", behalf_views.FilingView.as_view(), name="behalf"),
    path(
        "behalf/<int:pk>/academics/",
        behalf_views.AcademicsView.as_view(),
        name="behalf-academics",
    ),
    path(
        "behalf/<int:pk>/documents/<int:requirement>/",
        behalf_views.DocumentView.as_view(),
        name="behalf-document",
    ),
    path("behalf/<int:pk>/submit/", behalf_views.SubmitView.as_view(), name="behalf-submit"),
    path("behalf/<int:pk>/withdraw/", behalf_views.WithdrawView.as_view(), name="behalf-withdraw"),
    path("<int:pk>/", staff_views.ReviewView.as_view(), name="detail"),
    path("<int:pk>/start/", staff_views.StartReviewView.as_view(), name="start"),
    path(
        "<int:pk>/documents/<int:document>/approve/",
        staff_views.ApproveDocumentView.as_view(),
        name="document-approve",
    ),
    path(
        "<int:pk>/documents/<int:document>/decline/",
        staff_views.DeclineDocumentView.as_view(),
        name="document-decline",
    ),
    path(
        "<int:pk>/documents/<int:document>/preview/",
        staff_views.DocumentPreviewView.as_view(),
        name="document-preview",
    ),
    path("<int:pk>/decide/", staff_views.DecideView.as_view(), name="decide"),
]
