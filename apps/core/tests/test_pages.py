import re
import subprocess
from pathlib import Path

import pytest
from django.urls import reverse

ROOT = Path(__file__).resolve().parents[3]
PAGES = ["about", "privacy", "terms", "cookies", "help", "contact"]
DISCLAIMER = (
    "Independent portfolio project. Not affiliated with or endorsed by the City of Taguig. "
    "All sample people and data are fictional."
)


@pytest.mark.parametrize("name", PAGES)
def test_every_information_page_renders(client, vite_build, name):
    response = client.get(reverse(f"core:{name}"))
    body = response.content.decode()
    assert response.status_code == 200
    assert body.count("<h1") == 1
    assert DISCLAIMER in body
    assert "·" not in body.split('<main id="main"')[1]


@pytest.mark.parametrize("name", PAGES)
def test_information_pages_are_safe_methods_only(client, vite_build, name):
    assert client.post(reverse(f"core:{name}")).status_code == 405


@pytest.mark.parametrize("layout", ["public", "auth", "student", "staff", "office"])
def test_every_layout_has_the_footer_and_no_affiliation_claim(client, settings, vite_build, layout):
    settings.KIT_ENABLED = True
    body = client.get(f"/_kit/layouts/{layout}/").content.decode()
    assert DISCLAIMER in body
    for name in PAGES:
        assert f'href="{reverse(f"core:{name}")}"' in body
    assert "ScholarSync is the scholarship platform of the City of Taguig" not in body


def test_privacy_page_names_the_operator_and_contact(client, settings, vite_build):
    settings.SITE_OPERATOR_NAME = "Example Org"
    settings.PRIVACY_CONTACT_EMAIL = "dpo@example.org"
    privacy = client.get("/privacy/").content.decode()
    contact = client.get("/contact/").content.decode()
    for body in (privacy, contact):
        assert "Example Org" in body
        assert "dpo@example.org" in body
    assert "National Privacy Commission" in privacy
    assert "RA 10173" in privacy


def test_explore_notice_only_in_explore_mode(client, settings, vite_build):
    notice = (
        "This copy runs on your computer. Anything you enter stays in its database, "
        "and emails go to the local inbox, not to real people."
    )
    assert notice not in client.get("/privacy/").content.decode()
    settings.EXPLORE = True
    assert notice in client.get("/privacy/").content.decode()


def test_cookie_notice_lists_every_cookie_the_app_sets(client, settings, vite_build):
    settings.KIT_ENABLED = True
    response = client.get("/_kit/layouts/student/")  # renders a CSRF token, so sets the cookie
    names = {*response.cookies.keys(), settings.SESSION_COOKIE_NAME}
    assert settings.CSRF_COOKIE_NAME in names
    body = client.get("/cookies/").content.decode()
    for name in names:
        assert name in body


def test_production_requires_the_operator_settings(tmp_path):
    from config.tests.test_settings import _run_settings

    for missing in ("SITE_OPERATOR_NAME", "PRIVACY_CONTACT_EMAIL"):
        result = _run_settings(tmp_path, [missing], _unset=[missing])
        assert result.returncode != 0
        assert missing in result.stderr


def test_no_personal_email_in_repo():
    files = subprocess.run(  # noqa: S603
        ["git", "ls-files", "-z"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    allowed = re.compile(
        r"@(?:[a-z0-9-]+\.)*(?:example\.[a-z]+|scholarsync\.test|sentry\.io)$|^no-?reply@",
        re.IGNORECASE,
    )
    pattern = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
    offenders = []
    for name in files:
        if not name or name.startswith("docs/") or name.endswith((".lock", "-lock.json")):
            continue
        path = ROOT / name
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in pattern.finditer(text):
            address = match.group(0)
            if not allowed.search(address):
                offenders.append(f"{name}: {address}")
    assert offenders == []
