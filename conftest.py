import pytest


@pytest.fixture(autouse=True)
def _plain_static_storage(settings):
    """Tests don't run collectstatic, so the manifest storage would fail on {% static %}."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
