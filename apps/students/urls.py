from django.urls import path

from . import views

app_name = "students"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/personal/", views.PersonalView.as_view(), name="profile-personal"),
    path("profile/photo/", views.PhotoView.as_view(), name="profile-photo"),
    path("profile/family/", views.FamilyListView.as_view(), name="profile-family"),
    path("profile/family/add/", views.FamilyFormView.as_view(), name="profile-family-add"),
    path("profile/family/<int:pk>/", views.FamilyFormView.as_view(), name="profile-family-edit"),
    path(
        "profile/family/<int:pk>/delete/",
        views.FamilyDeleteView.as_view(),
        name="profile-family-delete",
    ),
    path("profile/education/", views.EducationListView.as_view(), name="profile-education"),
    path(
        "profile/education/add/",
        views.EducationFormView.as_view(),
        name="profile-education-add",
    ),
    path(
        "profile/education/<int:pk>/",
        views.EducationFormView.as_view(),
        name="profile-education-edit",
    ),
    path(
        "profile/education/<int:pk>/delete/",
        views.EducationDeleteView.as_view(),
        name="profile-education-delete",
    ),
]
