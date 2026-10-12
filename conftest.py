import shutil
import subprocess
from pathlib import Path

import pytest
from django.test import Client

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "static" / "dist" / ".vite" / "manifest.json"


class HttpsClient(Client):
    """Test client that always uses HTTPS, as every real request does behind Vercel."""

    def generic(self, *args, **kwargs):
        kwargs["secure"] = True
        return super().generic(*args, **kwargs)


@pytest.fixture
def client() -> HttpsClient:
    return HttpsClient()


@pytest.fixture(autouse=True)
def _plain_static_storage(settings):
    """Tests don't run collectstatic, so the manifest storage would fail on {% static %}."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture(scope="session")
def vite_build() -> Path:
    """Build the front end once per session so django-vite has a real manifest."""
    if not MANIFEST.exists():
        npm = shutil.which("npm")
        assert npm, "npm is required to build the front end for tests"
        subprocess.run([npm, "--prefix", "frontend", "run", "build"], check=True, cwd=ROOT)  # noqa: S603
        # django-vite parses the manifest once in AppConfig.ready(); drop that cached,
        # manifest-less loader so the next template render reads the fresh build.
        from django_vite.core.asset_loader import DjangoViteAssetLoader

        DjangoViteAssetLoader._instance = None
    return MANIFEST
