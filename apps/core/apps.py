from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from django.urls import register_converter

        from . import checks  # noqa: F401
        from .converters import IsoDateConverter

        register_converter(IsoDateConverter, "isodate")
