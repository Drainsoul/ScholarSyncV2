import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import time_machine
from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.checks import run_checks
from django.core.management import call_command
from django.core.management.base import CommandError
from django.template import Context, Template
from django.template.utils import get_app_template_dirs
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application
from apps.demo import loader
from apps.demo.accounts import ACCOUNTS, PASSWORD
from apps.matching.selectors import match_page
from apps.students.models import ProfileInvite, StudentProfile
from apps.students.selectors import profile_page

DEMO_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def demo_app(settings):
    """Install the demo as explore and developer modes do (production never installs it)."""
    settings.INSTALLED_APPS = [*settings.INSTALLED_APPS, "apps.demo"]


def test_production_does_not_install_the_demo_even_with_the_folder_present():
    assert DEMO_DIR.is_dir()
    assert settings.PRODUCTION is True
    assert settings.DEMO_INSTALLED is True
    assert settings.DEMO_ACTIVE is False
    assert "apps.demo" not in settings.INSTALLED_APPS


def test_production_never_loads_demo_templates():
    template_dirs = get_app_template_dirs("templates")
    assert not [d for d in template_dirs if Path(d).is_relative_to(DEMO_DIR)]
    out = Template('{% load slots %}[{% include_if_present "demo/login_notice.html" %}]').render(
        Context()
    )
    assert out == "[]"


def test_production_has_no_demo_command():
    with pytest.raises(CommandError, match="Unknown command"):
        call_command("load_demo")


def test_load_demo_refuses_in_production_mode(demo_app):
    with pytest.raises(CommandError, match="production"):
        call_command("load_demo")


@pytest.mark.django_db
def test_load_demo_runs_when_active(demo_app, settings, capsys):
    settings.DEMO_ACTIVE = True
    call_command("load_demo")
    assert "Demo data: 4 new objects." in capsys.readouterr().out
    call_command("load_demo")
    assert "Demo data: 0 new objects." in capsys.readouterr().out


@pytest.mark.django_db
def test_load_creates_four_verified_accounts_once(demo_app, settings):
    settings.DEMO_ACTIVE = True
    assert loader.load() == 4
    assert loader.load() == 0
    for account in ACCOUNTS:
        user = User.objects.get(email=account.email)
        assert user.role == account.role
        assert user.check_password(PASSWORD)
        assert EmailAddress.objects.get(user=user).verified
    head = User.objects.get(email="head@scholarsync.test")
    assert head.memberships.get().level == "head"


@pytest.mark.django_db
def test_load_completes_a_partial_earlier_run(demo_app, settings):
    settings.DEMO_ACTIVE = True
    loader.load()
    User.objects.filter(email="office@scholarsync.test").delete()
    assert loader.load() == 1


@pytest.mark.django_db
def test_load_twice_leaves_one_student_profile_and_one_staff_created_profile(demo_app, settings):
    settings.DEMO_ACTIVE = True
    loader.load()
    loader.load()
    assert StudentProfile.objects.filter(user__email="student@scholarsync.test").count() == 1
    unclaimed = StudentProfile.objects.filter(user__isnull=True)
    assert unclaimed.count() == 1
    assert ProfileInvite.objects.filter(email="paolo@scholarsync.test").count() == 1
    paolo = unclaimed.get()
    assert (paolo.first_name, paolo.last_name) == ("Paolo", "Villanueva")
    assert paolo.created_for is not None
    assert paolo.created_for.slug == "tcu-ceaa"
    assert paolo.created_by is not None
    assert paolo.created_by.email == "staff@scholarsync.test"


@pytest.mark.django_db
def test_demo_student_profile_is_92_percent_complete_without_a_photo(demo_app, settings):
    settings.DEMO_ACTIVE = True
    loader.load()
    profile, completion = profile_page(User.objects.get(email="student@scholarsync.test"))
    assert profile is not None
    assert completion.percent == 92
    assert [s.missing for s in completion.sections if s.key == "photo"] == [("a photo",)]
    assert profile.barangay == "ususan"
    assert profile.family.get().name == "Teresa Hawkins"
    assert profile.education.count() == 2
    current = profile.education.get(is_current=True)
    assert current.school is not None
    assert current.school.name == "Taguig City University"


@pytest.fixture
def frozen_today():
    with time_machine.travel(
        datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Manila")), tick=False
    ):
        yield


@pytest.mark.django_db
def test_load_gives_test_student_a_lani_draft(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    loader.load()
    application = Application.objects.get(profile__user__email="student@scholarsync.test")
    assert application.program.slug == "lani"
    assert application.status == Application.Status.DRAFT


@pytest.mark.django_db
def test_load_without_a_term_skips_the_draft(demo_app, settings, frozen_today, monkeypatch):
    settings.DEMO_ACTIVE = True
    monkeypatch.setattr(loader, "application_term", lambda today: None)
    loader.load()
    assert not Application.objects.exists()


@pytest.mark.django_db
def test_load_twice_keeps_one_draft(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    loader.load()
    loader.load()
    assert Application.objects.filter(profile__user__email="student@scholarsync.test").count() == 1


@pytest.mark.django_db
def test_test_student_qualifies_for_both_programs(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    loader.load()
    page = match_page(
        User.objects.get(email="student@scholarsync.test"), today=timezone.localdate()
    )
    assert len(page.matches) == 2
    assert all(m.result.eligible for m in page.matches)


def test_password_passes_the_validators():
    validate_password(PASSWORD)


@pytest.mark.django_db
def test_notice_lists_accounts_without_js(demo_app, client, vite_build):
    response = client.get("/accounts/login/")
    html = response.content.decode()
    assert "Exploring ScholarSync? Use a test account" in html
    assert PASSWORD in html
    for account in ACCOUNTS:
        assert account.email in html
    assert html.count("data-fill-email=") == 4
    assert html.count(" hidden>") >= 4


def test_deploy_check_fails_while_the_demo_folder_exists():
    errors = run_checks(include_deployment_checks=True)
    assert any(e.id == "demo.E001" for e in errors)


def test_nothing_outside_the_demo_imports_it():
    root = Path(__file__).resolve().parents[3]
    tracked = subprocess.run(
        ["git", "ls-files", "*.py"],  # noqa: S607
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    offenders = []
    for rel in tracked:
        if rel.startswith("apps/demo/") or rel in {"config/settings.py", "config/demo.py"}:
            continue
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "apps.demo" in text or "from apps import demo" in text:
            offenders.append(rel)
    assert offenders == []
