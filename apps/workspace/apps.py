from django.apps import AppConfig


class WorkspaceConfig(AppConfig):
    name = "apps.workspace"
    label = "workspace"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Connects the request signals that send queued email after the response.
        from . import emails  # noqa: F401
