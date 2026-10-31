from django.apps import AppConfig


class DemoConfig(AppConfig):
    name = "apps.demo"
    label = "demo"

    def ready(self) -> None:
        from . import checks  # noqa: F401
