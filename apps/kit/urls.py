from django.urls import path

from apps.kit import views

app_name = "kit"

urlpatterns = [
    path("", views.index, name="index"),
]
