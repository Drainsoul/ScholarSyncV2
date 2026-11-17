from django.urls import path

from . import program_views, views

app_name = "office"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("programs/", program_views.ProgramListView.as_view(), name="programs"),
    path("programs/new/", program_views.ProgramNewView.as_view(), name="program-new"),
    path("programs/<int:pk>/", program_views.ProgramEditView.as_view(), name="program-edit"),
    path(
        "programs/<int:pk>/active/",
        program_views.ProgramActiveView.as_view(),
        name="program-active",
    ),
    path("terms/", views.TermsView.as_view(), name="terms"),
    path("terms/add/", views.AddYearView.as_view(), name="terms-add"),
    path("terms/<int:pk>/current/", views.MakeCurrentView.as_view(), name="terms-current"),
]
