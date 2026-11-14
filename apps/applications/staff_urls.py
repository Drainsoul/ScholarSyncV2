from django.urls import path

from . import staff_views

app_name = "review"

urlpatterns = [
    path("", staff_views.QueueView.as_view(), name="queue"),
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
    path("<int:pk>/decide/", staff_views.DecideView.as_view(), name="decide"),
]
