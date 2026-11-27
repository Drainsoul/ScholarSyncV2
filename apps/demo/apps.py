from django.apps import AppConfig
from django.conf import settings


class DemoConfig(AppConfig):
    name = "apps.demo"
    label = "demo"

    def ready(self) -> None:
        # The hosted demo's shared accounts (branch `demo`, design section 5.2).
        if getattr(settings, "PUBLIC_DEMO", False):
            from apps.demo import lockdown

            lockdown.connect_guards()
