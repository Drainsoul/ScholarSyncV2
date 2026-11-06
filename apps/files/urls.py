from django.urls import path

from . import views

app_name = "files"

urlpatterns = [
    path("uploads/", views.upload_intent, name="upload-intent"),
    path("uploads/<uuid:file_id>/confirm/", views.upload_confirm, name="upload-confirm"),
    path("<uuid:file_id>/", views.download, name="download"),
]
