from django.urls import path

from . import views

app_name = "claim"

urlpatterns = [
    path("<str:token>/", views.ClaimView.as_view(), name="start"),
]
