from django.urls import path

from apps.kit import views

app_name = "kit"

urlpatterns = [
    path("", views.index, name="index"),
    path("demo/toast/", views.demo_toast, name="demo-toast"),
    path("demo/dialog/", views.demo_dialog, name="demo-dialog"),
    path("demo/bulk/", views.demo_bulk, name="demo-bulk"),
]
