from django.urls import path

from . import settings_views

app_name = "settings"

urlpatterns = [
    path("", settings_views.RulesView.as_view(), name="rules"),
    path("tiers/", settings_views.TiersView.as_view(), name="tiers"),
    path("tiers/new/", settings_views.TierNewView.as_view(), name="tier-new"),
    path("tiers/<slug:code>/", settings_views.TierChangeView.as_view(), name="tier-change"),
]
