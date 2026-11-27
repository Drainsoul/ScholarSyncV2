"""Deploy checks that must work whether or not optional apps are installed."""

from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, Warning, register

from config.demo import demo_installed


@register(Tags.security, deploy=True)
def demo_folder_removed(app_configs: object, **kwargs: object) -> list[CheckMessage]:
    """Fail `check --deploy` while the demo folder exists (production doesn't install it)."""
    # The hosted demo keeps the folder on purpose (branch `demo` only, design section 5.1).
    if not demo_installed(settings.BASE_DIR) or getattr(settings, "PUBLIC_DEMO", False):
        return []
    return [
        Error(
            "The demo app is still installed.",
            hint="Delete the apps/demo folder before deploying (docs/HOSTING.md).",
            id="demo.E001",
        )
    ]


@register(Tags.security, deploy=True)
def csp_enforced(app_configs: object, **kwargs: object) -> list[CheckMessage]:
    """Warn when production only reports CSP violations (`--fail-level WARNING` stops a deploy)."""
    if settings.CONTENT_SECURITY_POLICY is not None:
        return []
    return [
        Warning(
            "The Content Security Policy only reports violations; it doesn't block them.",
            hint="Unset CSP_REPORT_ONLY (and VITE_DEV_MODE) in production.",
            id="security.W_CSP_REPORT_ONLY",
        )
    ]
