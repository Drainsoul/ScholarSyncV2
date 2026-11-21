from django.urls import path

from . import support_views

app_name = "support"

urlpatterns = [
    path("me/support/", support_views.StudentSupportView.as_view(), name="student"),
    path("me/support/replies/", support_views.StudentRepliesView.as_view(), name="replies"),
    path("office/support/", support_views.OfficeSupportView.as_view(), name="office"),
    path("office/support/templates/", support_views.TemplateListView.as_view(), name="templates"),
    path(
        "office/support/templates/new/",
        support_views.TemplateNewView.as_view(),
        name="template-new",
    ),
    path(
        "office/support/templates/<int:pk>/",
        support_views.TemplateEditView.as_view(),
        name="template-edit",
    ),
    path(
        "office/support/templates/<int:pk>/active/",
        support_views.TemplateActiveView.as_view(),
        name="template-active",
    ),
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
