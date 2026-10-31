from django.core.checks import CheckMessage, Error, Tags, register


@register(Tags.security, deploy=True)
def demo_not_installed(app_configs: object, **kwargs: object) -> list[CheckMessage]:
    return [
        Error(
            "The demo app is still installed.",
            hint="Delete the apps/demo folder before deploying (docs/HOSTING.md).",
            id="demo.E001",
        )
    ]
