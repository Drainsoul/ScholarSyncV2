from django.urls import path

from . import views

app_name = "office"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("terms/", views.TermsView.as_view(), name="terms"),
    path("terms/add/", views.AddYearView.as_view(), name="terms-add"),
    path("terms/<int:pk>/current/", views.MakeCurrentView.as_view(), name="terms-current"),
]
