from django.urls import path

from . import support_views

app_name = "support"

urlpatterns = [
    path("me/support/", support_views.StudentSupportView.as_view(), name="student"),
    path("me/support/replies/", support_views.StudentSupportView.as_view(), name="replies"),
    path("office/support/", support_views.OfficeSupportView.as_view(), name="office"),
    path(
        "office/support/<int:pk>/", support_views.OfficeDetailView.as_view(), name="office-detail"
    ),
    path(
        "office/support/<int:pk>/reply/",
        support_views.OfficeReplyView.as_view(),
        name="office-reply",
    ),
    path(
        "office/support/<int:pk>/email/",
        support_views.OfficeEmailView.as_view(),
        name="office-email",
    ),
    path("office/support/<int:pk>/answer/", support_views.AnswerView.as_view(), name="answer"),
]
