from django.urls import path

from apps.programs import views

app_name = "programs"

urlpatterns = [
    path("", views.program_list, name="list"),
    path("<slug:slug>/", views.program_detail, name="detail"),
]
