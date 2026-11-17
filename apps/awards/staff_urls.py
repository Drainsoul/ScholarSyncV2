from django.urls import path

from . import staff_views

app_name = "scholars"

urlpatterns = [
    path("", staff_views.ScholarListView.as_view(), name="list"),
    path("new/", staff_views.NewScholarView.as_view(), name="new"),
    path("import/", staff_views.ScholarImportView.as_view(), name="import"),
    path("export/", staff_views.ScholarExportView.as_view(), name="export"),
    path(
        "import/template/",
        staff_views.ImportTemplateView.as_view(),
        name="import-template",
    ),
    path("<int:pk>/", staff_views.ScholarDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", staff_views.ScholarEditView.as_view(), name="edit"),
    path("<int:pk>/status/", staff_views.ScholarStatusView.as_view(), name="status"),
    path("<int:pk>/terms/new/", staff_views.TermFormView.as_view(), name="term-new"),
    path("<int:pk>/terms/<int:term>/", staff_views.TermFormView.as_view(), name="term-edit"),
    path(
        "<int:pk>/terms/<int:term>/merit/",
        staff_views.TermMeritView.as_view(),
        name="term-merit",
    ),
]
