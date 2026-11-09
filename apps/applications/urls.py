from django.urls import path

from . import views

app_name = "applications"

urlpatterns = [
    path("", views.ListView.as_view(), name="list"),
    path("new/<slug:program>/", views.NewView.as_view(), name="new"),
    path("<int:pk>/", views.DetailView.as_view(), name="detail"),
    path("<int:pk>/documents/<int:requirement>/", views.DocumentView.as_view(), name="document"),
]
