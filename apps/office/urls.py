from django.urls import path

from apps.workspace import notification_views

from . import program_views, school_views, staff_views, views

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
    path("staff/", staff_views.StaffListView.as_view(), name="staff"),
    path("staff/new/", staff_views.StaffNewView.as_view(), name="staff-new"),
    path("staff/<int:pk>/", staff_views.StaffDetailView.as_view(), name="staff-detail"),
    path("staff/<int:pk>/active/", staff_views.StaffActiveView.as_view(), name="staff-active"),
    path("staff/<int:pk>/welcome/", staff_views.StaffWelcomeView.as_view(), name="staff-welcome"),
    path(
        "staff/<int:pk>/memberships/",
        staff_views.MembershipAddView.as_view(),
        name="membership-add",
    ),
    path(
        "memberships/<int:pk>/",
        staff_views.MembershipChangeView.as_view(),
        name="membership-change",
    ),
    path("schools/", school_views.SchoolListView.as_view(), name="schools"),
    path("schools/new/", school_views.SchoolNewView.as_view(), name="school-new"),
    path("schools/<int:pk>/", school_views.SchoolEditView.as_view(), name="school-edit"),
    path(
        "notifications/",
        notification_views.OfficeNotificationListView.as_view(),
        name="notifications",
    ),
    path(
        "notifications/read/",
        notification_views.OfficeMarkAllReadView.as_view(),
        name="notifications-read",
    ),
    path(
        "notifications/<int:pk>/",
        notification_views.OfficeOpenNotificationView.as_view(),
        name="notification-open",
    ),
    path("terms/", views.TermsView.as_view(), name="terms"),
    path("terms/add/", views.AddYearView.as_view(), name="terms-add"),
    path("terms/<int:pk>/current/", views.MakeCurrentView.as_view(), name="terms-current"),
]
