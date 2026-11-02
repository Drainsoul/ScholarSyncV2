"""Deploy checks that must work whether or not optional apps are installed."""

from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, register

from config.demo import demo_installed


@register(Tags.security, deploy=True)
def demo_folder_removed(app_configs: object, **kwargs: object) -> list[CheckMessage]:
    """Fail `check --deploy` while the demo folder exists (production doesn't install it)."""
    if not demo_installed(settings.BASE_DIR):
        return []
    return [
        Error(
            "The demo app is still installed.",
            hint="Delete the apps/demo folder before deploying (docs/HOSTING.md).",
            id="demo.E001",
        )
    ]
