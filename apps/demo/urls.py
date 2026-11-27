from django.urls import path

from apps.demo.views import reset_view

urlpatterns = [path("reset/", reset_view, name="demo_reset")]
