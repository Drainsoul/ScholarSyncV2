"""Small ASVS 5.0 L2 gaps closed in M12 (docs/security/asvs-l2.md names each by id)."""

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.awards import tabular
from apps.awards.tabular import TableError, read_table
from apps.core.gunicorn_logging import redact_atoms
from apps.files import storage
from apps.files.models import StoredFile
from apps.files.policy import XLSX
from apps.files.tests.factories import StoredFileFactory
from config.tests.test_settings import settings_values

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.django_db
def test_google_login_by_token_is_404_even_with_keys(client: Any, settings: Any) -> None:
    """V9.1.2, V10.5.1: allauth's One Tap token route is unused and takes `alg` from the token."""
    settings.SOCIALACCOUNT_PROVIDERS = {"google": {"APPS": [{"client_id": "id", "secret": "x"}]}}
    url = reverse("google_login_by_token")
    assert client.get(url).status_code == 404
    assert client.post(url, {"credential": "x.y.z"}).status_code == 404


def test_csrf_cookie_is_httponly(settings: Any) -> None:
    """V3.3.4: htmx takes the token from `hx-headers`; no script reads the cookie."""
    assert settings.CSRF_COOKIE_HTTPONLY is True


def test_production_cookies_use_the_host_prefix(tmp_path: Path) -> None:
    """V3.3.1, V3.3.3: `__Host-` cookies (HTTPS only, this host only); messages live in the
    session, so there is no separate messages cookie."""
    names = ["SESSION_COOKIE_NAME", "CSRF_COOKIE_NAME", "THEME_COOKIE_NAME"]
    values = settings_values(tmp_path, [*names, "MESSAGE_STORAGE"])
    assert values == {
        "SESSION_COOKIE_NAME": "__Host-sessionid",
        "CSRF_COOKIE_NAME": "__Host-csrftoken",
        "THEME_COOKIE_NAME": "__Host-theme",  # spec §12 rev 29: the light/dark choice
        "MESSAGE_STORAGE": "django.contrib.messages.storage.session.SessionStorage",
    }
    developer = settings_values(tmp_path, names, DJANGO_DEBUG="true")
    assert developer == {
        "SESSION_COOKIE_NAME": "sessionid",
        "CSRF_COOKIE_NAME": "csrftoken",
        "THEME_COOKIE_NAME": "theme",
    }


@pytest.mark.django_db
def test_download_503_has_a_charset(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """V4.1.1: text answers name their charset."""
    user = UserFactory.create(verified=True)
    file = StoredFileFactory.create(
        uploaded_by=user,
        status=StoredFile.Status.READY,
        sniffed_type="application/pdf",
        sha256="0" * 64,
    )

    def not_configured(**kwargs: Any) -> str:
        raise storage.StorageNotConfigured("none")

    monkeypatch.setattr(storage, "presigned_get", not_configured)
    client.force_login(user)
    response = client.get(reverse("files:download", args=[file.pk]))
    assert response.status_code == 503
    assert response["Content-Type"] == "text/plain; charset=utf-8"


def test_xlsx_with_too_many_entries_is_refused() -> None:
    """V5.2.3: an archive's entry count is checked before it is unpacked."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for n in range(101):
            archive.writestr(f"x/{n}.xml", "<a/>")
    with pytest.raises(TableError) as caught:
        read_table(buffer.getvalue(), XLSX)
    assert str(caught.value) == getattr(tabular, "TOO_MANY_ENTRIES", "missing")


def test_access_log_redacts_name_searches() -> None:
    """V14.2.1, V16.2.5: a name search (`?q=`) is personal data; the access log drops it."""
    atoms = redact_atoms(
        {
            "r": "GET /staff/tcu-ceaa/scholars/?status=active&q=Juan+Dela+Cruz HTTP/1.1",
            "q": "q=Juan+Dela+Cruz&status=active",
            "f": "https://host.example/office/scholars/?q=Maria",
        }
    )
    assert "Juan" not in str(atoms) and "Maria" not in str(atoms)
    assert atoms["r"] == "GET /staff/tcu-ceaa/scholars/?status=active&q=[redacted] HTTP/1.1"
    assert atoms["q"] == "q=[redacted]&status=active"


@pytest.mark.django_db
def test_signed_in_account_pages_offer_sign_out(client: Any, vite_build: Any) -> None:
    """V7.4.4: every signed-in page has a visible way out."""
    client.force_login(UserFactory.create(verified=True))
    for name in ("account_change_password", "account_email"):
        html = client.get(reverse(name)).content.decode()
        assert f'action="{reverse("account_logout")}"' in html, name
        assert "Sign out" in html, name


def test_dependencies_are_watched() -> None:
    """V15.2.1: Dependabot watches every ecosystem, and the audits also run on a schedule."""
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    for ecosystem in ("uv", "npm", "github-actions", "docker"):
        assert f'package-ecosystem: "{ecosystem}"' in dependabot, ecosystem
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "schedule:" in workflow and "cron:" in workflow


@pytest.mark.parametrize(
    "password", ["Taguig-2026-pass", "myScholarSync!!1", "scholarship-please-9", "tcu-ceaa-forever"]
)
def test_password_with_a_site_word_is_refused(password: str) -> None:
    """V6.1.2, V6.2.11: passwords can't contain the site's own words."""
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError) as caught:
        validate_password(password)
    assert "Choose a password without the name of this site, the city or a program." in (
        caught.value.messages
    )


def test_ordinary_password_passes_the_site_word_check() -> None:
    from django.contrib.auth.password_validation import validate_password

    validate_password("planing-a-long-trip-77")  # "lani" inside a word is fine
