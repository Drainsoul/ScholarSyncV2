from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from django.urls import register_converter
        from django.urls.converters import get_converters

        from . import checks  # noqa: F401
        from .converters import IsoDateConverter

        if "isodate" not in get_converters():  # ready() can run again (the demo tests reload apps)
            register_converter(IsoDateConverter, "isodate")
