from django.urls import path

from . import views

app_name = "scholarships"

urlpatterns = [
    path("", views.ScholarshipsView.as_view(), name="list"),
    path("<int:pk>/renew/", views.RenewView.as_view(), name="renew"),
]
