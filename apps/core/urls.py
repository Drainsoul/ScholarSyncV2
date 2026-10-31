from django.urls import path

from apps.core import pages, views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("about/", pages.about, name="about"),
    path("privacy/", pages.privacy, name="privacy"),
    path("terms/", pages.terms, name="terms"),
    path("cookies/", pages.cookies, name="cookies"),
    path("help/", pages.help_page, name="help"),
    path("contact/", pages.contact, name="contact"),
]
