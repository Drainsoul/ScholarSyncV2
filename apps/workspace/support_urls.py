from django.urls import path

from . import support_views

app_name = "support"

urlpatterns = [
    path("me/support/", support_views.StudentSupportView.as_view(), name="student"),
    path("me/support/replies/", support_views.StudentSupportView.as_view(), name="replies"),
    path("office/support/", support_views.OfficeSupportView.as_view(), name="office"),
    path("office/support/<int:pk>/answer/", support_views.AnswerView.as_view(), name="answer"),
]
