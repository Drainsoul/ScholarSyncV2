import logging
import subprocess
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import time_machine
from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.checks import run_checks
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.template import Context, Template
from django.template.utils import get_app_template_dirs
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application
from apps.awards.importing import check_import
from apps.awards.models import Award
from apps.awards.selectors import RenewalStatus, renewal_for, with_latest_term
from apps.core.models import AuditEvent
from apps.demo import loader
from apps.demo.accounts import ACCOUNTS, LISTED, LISTED_EMAILS, PASSWORD
from apps.demo.loader import SAMPLE_IMPORT
from apps.demo.samples import (
    HOLD_REASON,
    LANI_APPLICANTS,
    LANI_SCHOLARS,
    MANUAL_SCHOLAR,
    REJECT_REASON,
    SAMPLE_APPLICANTS,
    SAMPLE_SCHOLARS,
)
from apps.files import storage
from apps.files.models import StoredFile
from apps.files.policy import CSV
from apps.matching.selectors import match_page
from apps.programs.models import AcademicTerm, Program
from apps.programs.selectors import application_term
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
    assert "Demo data: 7 new objects." in capsys.readouterr().out
    call_command("load_demo")
    assert "Demo data: 0 new objects." in capsys.readouterr().out


@pytest.mark.django_db
def test_load_creates_seven_verified_role_accounts_once(demo_app, settings):
    settings.DEMO_ACTIVE = True
    assert loader.load() == 7
    assert loader.load() == 0
    for account in ACCOUNTS:
        user = User.objects.get(email=account.email)
        assert user.role == account.role
        assert user.check_password(PASSWORD)
        assert EmailAddress.objects.get(user=user).verified
    head = User.objects.get(email="head@scholarsync.test")
    assert head.memberships.get().level == "head"
    lani = User.objects.get(email="lani.head@scholarsync.test").memberships.get()
    assert (lani.program.slug, lani.level) == ("lani", "head")
    new = User.objects.get(email="new@scholarsync.test")
    assert not StudentProfile.objects.filter(user=new).exists()  # starts from an empty profile


@pytest.mark.django_db
def test_load_gives_existing_demo_accounts_the_current_password(demo_app, settings, frozen_today):
    # A database from before the password changed keeps working: the login page shows PASSWORD.
    settings.DEMO_ACTIVE = True
    loader.load()
    emails = list(User.objects.filter(email__in=LISTED_EMAILS).values_list("email", flat=True))
    assert {s.email for s in SAMPLE_SCHOLARS} - {SAMPLE_SCHOLARS[1].email} <= set(emails)
    for user in User.objects.filter(email__in=emails):
        user.set_password("explore-taguig-2026")
        user.save(update_fields=["password"])
    applicant = User.objects.filter(email__endswith="@scholarsync.test", password__startswith="!")
    unusable = set(applicant.values_list("pk", flat=True))
    assert unusable
    loader.load()
    for email in emails:
        assert User.objects.get(email=email).check_password(PASSWORD), email
    assert not any(u.has_usable_password() for u in User.objects.filter(pk__in=unusable))


@pytest.mark.django_db
def test_load_completes_a_partial_earlier_run(demo_app, settings, monkeypatch):
    settings.DEMO_ACTIVE = True
    # An earlier run from before the M11 samples, which give the office audited actions (an
    # account with audit events can't be deleted: they are append-only).
    monkeypatch.setattr(loader, "give_workspace_samples", lambda: None)
    monkeypatch.setattr(loader, "give_office_samples", lambda: None)
    monkeypatch.setattr(loader, "_give_lani_a_window", lambda: None)  # rev 26, also audited
    loader.load()
    User.objects.filter(email="office@scholarsync.test").delete()
    monkeypatch.undo()
    assert loader.load() == 1


@pytest.mark.django_db
def test_load_twice_leaves_one_student_profile_and_one_staff_created_profile(demo_app, settings):
    settings.DEMO_ACTIVE = True
    loader.load()
    loader.load()
    assert StudentProfile.objects.filter(user__email="student@scholarsync.test").count() == 1
    unclaimed = StudentProfile.objects.filter(user__isnull=True, first_name="Paolo")
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
def test_skipped_draft_log_holds_no_profile_values(
    demo_app, settings, frozen_today, monkeypatch, caplog
):
    settings.DEMO_ACTIVE = True

    def refuse(**kwargs):
        raise ValidationError("Your GWA of 80.00 doesn't meet this program's minimum of 85%.")

    monkeypatch.setattr(loader, "start_application", refuse)
    with caplog.at_level(logging.WARNING, logger="apps.demo.loader"):
        loader.load()
    assert not Application.objects.filter(on_behalf=False).exists()
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "Demo draft application skipped (ValidationError)." in logged
    assert "80.00" not in logged
    assert "85" not in logged


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
def test_notice_lists_accounts_without_js(
    demo_app, settings, client, vite_build, frozen_today, stored
):
    settings.DEMO_ACTIVE = True
    loader.load()
    response = client.get("/accounts/login/")
    html = response.content.decode()
    assert "Exploring ScholarSync? Use a test account" in html
    # Spec §11 rev 32: a closed <details> whose summary opens the accounts.
    assert '<details class="notice demo-accounts">' in html
    assert '<summary class="demo-accounts__toggle">' in html
    # rev 36: the password once, every listed account in its group, buttons hidden until JS.
    assert html.count(PASSWORD) == 1 + len(LISTED)  # the lead, then each button's data
    for account in LISTED:
        assert account.email in html
        assert f">{account.button}</button>" in html
    assert html.count("data-fill-email=") == len(LISTED) == 10
    assert html.count('class="demo-accounts__choice"') == html.count(" hidden>")
    for group in ("Students", "Program staff", "Scholarship office"):
        assert f">{group}</p>" in html
    assert html.count("data-fill-fallback") == 3


@pytest.mark.django_db
def test_notice_hides_accounts_that_cannot_sign_in(demo_app, settings, client, vite_build):
    # Before load_demo: no account, so no dead button.
    html = client.get("/accounts/login/").content.decode()
    assert "data-fill-email=" not in html
    assert "No test accounts on this copy yet." in html
    # Without storage the returned applicant isn't made, so only the rest are offered.
    settings.DEMO_ACTIVE = True
    loader.load()
    html = client.get("/accounts/login/").content.decode()
    assert "applicant4@scholarsync.test" not in html
    assert "office@scholarsync.test" in html
    User.objects.filter(email="office@scholarsync.test").update(is_active=False)
    assert "office@scholarsync.test" not in client.get("/accounts/login/").content.decode()


@pytest.mark.django_db
def test_listed_applicant_from_an_older_demo_gets_the_password(
    demo_app, settings, frozen_today, stored
):
    settings.DEMO_ACTIVE = True
    loader.load()
    miguel = User.objects.get(email="applicant4@scholarsync.test")
    assert miguel.check_password(PASSWORD)
    miguel.set_unusable_password()  # as a demo loaded before rev 36 made him
    miguel.save(update_fields=["password"])
    loader.load()
    miguel.refresh_from_db()
    assert miguel.check_password(PASSWORD)
    other = User.objects.get(email="applicant1@scholarsync.test")
    assert not other.has_usable_password()  # unlisted applicants never sign in


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


@pytest.fixture
def stored(monkeypatch):
    """Storage looks configured and records what is put, so no network is touched."""
    puts: list[tuple[str, bytes, str]] = []
    monkeypatch.setattr("apps.files.storage.is_configured", lambda: True)
    monkeypatch.setattr(
        "apps.files.storage.put",
        lambda *, key, body, content_type: puts.append((key, body, content_type)),
    )
    return puts


def _statuses() -> dict[str, str]:
    return {
        str(a.profile.user.email if a.profile.user else ""): a.status
        for a in Application.objects.filter(
            profile__user__email__startswith="applicant"
        ).select_related("profile__user")
    }


@pytest.mark.django_db
def test_loader_builds_the_review_queue(demo_app, settings, frozen_today, stored, client):
    settings.DEMO_ACTIVE = True
    loader.load()
    assert _statuses() == {
        "applicant1@scholarsync.test": "submitted",
        "applicant2@scholarsync.test": "submitted",
        "applicant3@scholarsync.test": "under_review",
        "applicant4@scholarsync.test": "returned",
        "applicant5@scholarsync.test": "approved",
        # rev 36: two more outcomes, neither waiting.
        "applicant6@scholarsync.test": "rejected",
        "applicant7@scholarsync.test": "withdrawn",
    }
    rejected = Application.objects.get(profile__user__email="applicant6@scholarsync.test")
    assert rejected.decision_reason == REJECT_REASON
    # One CEAA award from an application, one LANI (rev 36).
    assert Award.objects.filter(source=Award.Source.APPLIED).count() == 2
    returned = Application.objects.get(profile__user__email="applicant4@scholarsync.test")
    declined = returned.documents.get(status="declined")
    assert declined.decline_reason == "The scan is too dark to read."
    assert returned.decision_reason == "Upload a clearer copy of your certificate of registration."
    under_review = Application.objects.get(profile__user__email="applicant3@scholarsync.test")
    assert under_review.documents.filter(status="approved").count() == 1
    for file in StoredFile.objects.filter(uploaded_by__email__startswith="applicant"):
        assert file.status == "ready"
        assert file.key == f"files/document/{file.id}"
        assert file.sha256
    assert {content_type for _, _, content_type in stored} == {"application/pdf", "image/png"}
    assert not User.objects.get(email="applicant1@scholarsync.test").has_usable_password()
    client.force_login(User.objects.get(email="staff@scholarsync.test"))
    waiting = client.get("/staff/tcu-ceaa/applications/")
    assert [a.status for a in waiting.context["page"].object_list].count("returned") == 0
    # The default filter is Waiting: submitted + under review (the walk-in's filing included).
    assert waiting.context["total"] == 4
    everything = client.get("/staff/tcu-ceaa/applications/?status=all")
    assert everything.context["total"] == 8
    returned_only = client.get("/staff/tcu-ceaa/applications/?status=returned")
    assert returned_only.context["total"] == 1


@pytest.mark.django_db
def test_loader_is_idempotent_with_samples(demo_app, settings, frozen_today, stored):
    settings.DEMO_ACTIVE = True
    loader.load()
    counts = (
        User.objects.count(),
        Application.objects.count(),
        StoredFile.objects.count(),
        Award.objects.count(),
        len(stored),
    )
    assert loader.load() == 0
    assert counts == (
        User.objects.count(),
        Application.objects.count(),
        StoredFile.objects.count(),
        Award.objects.count(),
        len(stored),
    )


@pytest.mark.django_db
def test_loader_skips_samples_without_storage(
    demo_app, settings, frozen_today, monkeypatch, caplog
):
    settings.DEMO_ACTIVE = True
    monkeypatch.setattr("apps.files.storage.is_configured", lambda: False)
    with caplog.at_level(logging.WARNING, logger="apps.demo.loader"):
        loader.load()
    assert not User.objects.filter(email__startswith="applicant").exists()
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "Demo review samples skipped (StorageNotConfigured)." in logged
    assert "Carolyn" not in logged
    assert Application.objects.get(profile__user__email="student@scholarsync.test")


@pytest.mark.django_db
def test_loader_rolls_back_samples_when_storage_fails(
    demo_app, settings, frozen_today, monkeypatch, caplog
):
    from apps.files.storage import StorageUnavailable

    settings.DEMO_ACTIVE = True
    monkeypatch.setattr("apps.files.storage.is_configured", lambda: True)

    def fail(**kwargs):
        raise StorageUnavailable("Object storage request failed (EndpointConnectionError).")

    monkeypatch.setattr("apps.files.storage.put", fail)
    with caplog.at_level(logging.WARNING, logger="apps.demo.loader"):
        loader.load()
    assert not User.objects.filter(email__startswith="applicant").exists()
    assert "Demo review samples skipped (StorageUnavailable)." in " ".join(
        record.getMessage() for record in caplog.records
    )
    assert Application.objects.filter(profile__user__email="student@scholarsync.test").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["PermissionDenied", "ObjectDoesNotExist"])
def test_loader_skips_samples_when_a_service_refuses_staff(
    demo_app, settings, frozen_today, stored, monkeypatch, caplog, kind
):
    from django.core import exceptions

    settings.DEMO_ACTIVE = True

    def refuse(applications):
        raise getattr(exceptions, kind)("Carolyn is not staff of this program.")

    monkeypatch.setattr(loader, "_decide_samples", refuse)
    with caplog.at_level(logging.WARNING, logger="apps.demo.loader"):
        loader.load()
    assert not User.objects.filter(email__in=[a.email for a in SAMPLE_APPLICANTS]).exists()
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert f"Demo review samples skipped ({kind})." in logged
    assert "Carolyn" not in logged
    assert Application.objects.filter(profile__user__email="student@scholarsync.test").exists()


def _walk_in(first_name: str) -> StudentProfile:
    return StudentProfile.objects.get(
        user__isnull=True, created_for__slug="tcu-ceaa", first_name=first_name
    )


@pytest.mark.django_db
def test_demo_has_on_behalf_submitted_application(demo_app, settings, frozen_today, stored):
    settings.DEMO_ACTIVE = True
    loader.load()
    application = Application.objects.get(profile=_walk_in("Ramon"))
    assert application.on_behalf is True
    assert application.status == Application.Status.SUBMITTED
    assert application.match_snapshot["override"] == ["gwa"]
    assert application.override_reason == (
        "Walk-in applicant; the GWA shortfall was reviewed with the student's adviser."
    )
    assert application.created_by is not None
    assert application.created_by.email == "staff@scholarsync.test"
    assert application.documents.exists()


@pytest.mark.django_db
def test_demo_has_on_behalf_draft(demo_app, settings, frozen_today, stored):
    settings.DEMO_ACTIVE = True
    loader.load()
    draft = Application.objects.get(profile=_walk_in("Lorna"))
    assert draft.on_behalf is True
    assert draft.status == Application.Status.DRAFT
    assert draft.gwa is not None
    assert draft.course


@pytest.mark.django_db
def test_demo_on_behalf_rerun_is_idempotent(demo_app, settings, frozen_today, stored):
    settings.DEMO_ACTIVE = True
    loader.load()
    counts = (
        StudentProfile.objects.count(),
        Application.objects.filter(on_behalf=True).count(),
        StoredFile.objects.count(),
        ProfileInvite.objects.count(),
    )
    loader.load()
    assert counts == (
        StudentProfile.objects.count(),
        Application.objects.filter(on_behalf=True).count(),
        StoredFile.objects.count(),
        ProfileInvite.objects.count(),
    )
    assert counts[1] == 2


@pytest.mark.django_db
def test_demo_on_behalf_without_storage_skips_submitted_sample(
    demo_app, settings, frozen_today, monkeypatch
):
    settings.DEMO_ACTIVE = True
    monkeypatch.setattr("apps.files.storage.is_configured", lambda: False)
    loader.load()
    assert not StudentProfile.objects.filter(first_name="Ramon", user__isnull=True).exists()
    assert not Application.objects.filter(on_behalf=True, status="submitted").exists()
    draft = Application.objects.get(on_behalf=True)
    assert draft.status == Application.Status.DRAFT
    assert draft.profile.first_name == "Lorna"


# --- Scholars and renewals (M9) ---


def _scholar_award(email: str) -> Award:
    return Award.objects.select_related("program", "tier").get(profile__user__email=email)


@pytest.mark.django_db
def test_load_creates_three_scholars_once(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    loader.load()
    loader.load()
    emails = [scholar.email for scholar in SAMPLE_SCHOLARS]
    assert Award.objects.filter(profile__user__email__in=emails).count() == 3
    for email in emails:
        user = User.objects.get(email=email)
        assert user.check_password(PASSWORD)
        assert EmailAddress.objects.get(user=user).verified


@pytest.mark.django_db
def test_carmela_is_due(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    loader.load()
    award = _scholar_award("scholar@scholarsync.test")
    term = application_term(timezone.localdate())
    assert renewal_for(award, term).status == RenewalStatus.DUE
    assert award.source == Award.Source.MANUAL


@pytest.mark.django_db
def test_daniel_is_due_with_a_low_gwa(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    loader.load()
    award = _scholar_award("scholar2@scholarsync.test")
    term = application_term(timezone.localdate())
    assert renewal_for(award, term).status == RenewalStatus.DUE
    annotated: Any = with_latest_term(Award.objects.filter(pk=award.pk)).get()
    assert annotated.latest_gwa == Decimal("78")
    assert award.program.renewal_min_gwa_percent == Decimal("80")  # under the mark, no flag


@pytest.mark.django_db
def test_elena_on_hold_with_reason(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    loader.load()
    award = _scholar_award("scholar3@scholarsync.test")
    assert award.status == Award.Status.SUSPENDED
    assert award.status_reason == HOLD_REASON


@pytest.mark.django_db
def test_previous_term_created_once(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    loader.load()
    loader.load()
    # 15 October 2026 falls in term 1 of 2026-2027: the previous semester is term 2 of 2025-2026.
    previous = AcademicTerm.objects.filter(school_year_start=2025, term=2)
    assert previous.count() == 1
    assert not previous.get().is_current
    assert _scholar_award("scholar@scholarsync.test").started_term == previous.get()


@pytest.mark.django_db
def test_summer_skips_scholars(demo_app, settings):
    settings.DEMO_ACTIVE = True
    with time_machine.travel(
        datetime(2027, 7, 10, 12, 0, tzinfo=ZoneInfo("Asia/Manila")), tick=False
    ):
        loader.load()
    assert not Award.objects.filter(profile__user__email__startswith="scholar").exists()


@pytest.mark.django_db
def test_demo_does_not_change_program_config(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    call_command("seed_programs")
    fields = [f.name for f in Program._meta.concrete_fields if f.name != "updated_at"]
    before = list(Program.objects.order_by("pk").values(*fields))
    loader.load()
    # The demo adds its own closed sample program (M11b); the seeded ones stay as they were,
    # except LANI's empty application window, which the demo fills (spec §11 rev 26).
    seeded = Program.objects.filter(pk__in=[row["id"] for row in before])
    after = list(seeded.order_by("pk").values(*fields))
    window = ("applications_open_on", "applications_close_on")
    for row in [*before, *after]:
        if row["slug"] == "lani":
            for name in window:
                row.pop(name)
    assert after == before


@pytest.mark.django_db
def test_demo_gives_lani_a_window_around_today_once(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    loader.load()
    lani = Program.objects.get(slug="lani")
    today = timezone.localdate()
    assert lani.applications_open_on == today - loader.LANI_WINDOW_BEFORE
    assert lani.applications_close_on == today + loader.LANI_WINDOW_AFTER
    assert AuditEvent.objects.filter(
        action="program.rules_changed", actor__email="office@scholarsync.test"
    ).exists()
    # A window someone set is left alone on the next load.
    later = today + timedelta(days=3)
    Program.objects.filter(pk=lani.pk).update(applications_close_on=later)
    loader.load()
    lani.refresh_from_db()
    assert lani.applications_close_on == later


# --- Manual scholar and the sample import file (M9b) ---


@pytest.mark.django_db
def test_felipe_manual_scholar(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    loader.load()
    award = Award.objects.select_related("profile", "program").get(
        profile__first_name=MANUAL_SCHOLAR.first_name,
        profile__last_name=MANUAL_SCHOLAR.last_name,
    )
    assert award.source == Award.Source.MANUAL
    assert award.program.slug == "tcu-ceaa"
    assert award.profile.user is None
    assert award.profile.created_for == award.program
    assert not ProfileInvite.objects.filter(profile=award.profile).exists()
    assert award.terms.count() == 1


@pytest.mark.django_db
def test_felipe_load_is_idempotent(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    loader.load()
    loader.load()
    assert (
        Award.objects.filter(
            profile__first_name=MANUAL_SCHOLAR.first_name,
            profile__last_name=MANUAL_SCHOLAR.last_name,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_sample_import_previews_ok(demo_app, settings, frozen_today, monkeypatch):
    settings.DEMO_ACTIVE = True
    loader.load()
    body = SAMPLE_IMPORT.read_bytes()
    monkeypatch.setattr(storage, "read_all", lambda key: body)
    program = Program.objects.get(slug="tcu-ceaa")
    stored = StoredFile(key="files/import/sample", sniffed_type=CSV)
    preview = check_import(program, stored)
    assert preview.problem == ""
    assert [row.errors for row in preview.rows] == [[]] * 5
    assert preview.ok


@pytest.mark.django_db
def test_demo_money_samples(demo_app, settings, frozen_today):
    from decimal import Decimal

    from apps.money.models import Budget, Disbursement, DistributionSchedule

    settings.DEMO_ACTIVE = True
    loader.load()
    program = Program.objects.get(slug="tcu-ceaa")
    past, upcoming = DistributionSchedule.objects.filter(program=program).order_by(
        "distribution_date"
    )
    assert past.is_published and upcoming.is_published
    assert past.distribution_date < timezone.localdate() < upcoming.distribution_date
    assert (upcoming.distribution_date - timezone.localdate()).days == 14
    statuses = {
        row.scholar_term.award.profile.first_name: row.status
        for row in Disbursement.objects.filter(schedule=past).select_related(
            "scholar_term__award__profile"
        )
    }
    by_email = {s.state: s.first_name for s in SAMPLE_SCHOLARS}
    assert statuses == {by_email["due"]: "released", by_email["low_gwa"]: "approved"}
    felipe = Disbursement.objects.get(schedule=upcoming)
    assert felipe.status == "pending"
    assert felipe.scholar_term.award.profile.first_name == MANUAL_SCHOLAR.first_name
    budget = Budget.objects.get(program=program)
    assert (budget.fiscal_year, budget.amount) == (2026, Decimal("1000000.00"))
    loader.load()
    assert DistributionSchedule.objects.count() == 2
    assert Disbursement.objects.count() == 3


@pytest.mark.django_db
def test_demo_has_workspace_samples(demo_app, settings, frozen_today, stored):
    from apps.applications.review_selectors import applications_by_month
    from apps.core.charts import first_month, month_bars
    from apps.workspace.models import Notification, ReplyTemplate, SupportRequest, Task

    settings.DEMO_ACTIVE = True
    loader.load()
    loader.load()
    carmela = Notification.objects.filter(recipient__email="scholar@scholarsync.test")
    assert carmela.count() >= 2
    assert carmela.filter(read_at=None).count() == 1
    tasks = Task.objects.filter(owner__email="staff@scholarsync.test", program__slug="tcu-ceaa")
    today = timezone.localdate()
    assert tasks.count() == 3
    assert tasks.filter(done_at=None, due_on__lt=today).count() == 1
    assert tasks.filter(done_at=None, due_on=today).count() == 1
    assert tasks.exclude(done_at=None).count() == 1
    support = SupportRequest.objects.filter(sender__email="student@scholarsync.test")
    assert sorted(support.values_list("status", flat=True)) == ["answered", "open", "open"]
    answered = support.get(status="answered")
    assert answered.replies.count() == 1  # rev 35: the answer is in the app
    staff_inbox = support.filter(program__slug="tcu-ceaa", status="open")
    assert staff_inbox.count() == 1  # Carolyn's one for the CEAA staff and head to answer
    # rev 36: the sample applicants and scholars ask too, two per program.
    inbox = SupportRequest.objects.filter(status="open").exclude(
        sender__email=support[0].sender.email
    )
    assert sorted(inbox.values_list("program__slug", flat=True)) == [
        "lani",
        "lani",
        "tcu-ceaa",
        "tcu-ceaa",
    ]
    templates = ReplyTemplate.objects.filter(is_active=True)
    assert templates.count() == 14
    assert templates.filter(topic="").count() == 2  # fit any topic
    assert set(templates.exclude(topic="").values_list("topic", flat=True)) == {
        "account",
        "profile",
        "application",
        "allowance",
        "other",
    }  # every topic has one
    assert list(templates.exclude(program=None).values_list("program__slug", flat=True)) == ["lani"]
    assert templates.exclude(subject="").count() == 10
    program = Program.objects.get(slug="tcu-ceaa")
    counts = applications_by_month([program], since=first_month(today))
    bars = month_bars(counts, today=today)
    assert sum(1 for bar in bars if bar.count) >= 3
    queue = [
        a.status
        for a in Application.objects.filter(
            program=program, status__in=["submitted", "under_review"]
        )
    ]
    assert len(queue) == 4


@pytest.mark.django_db
def test_demo_has_office_samples(demo_app, settings, frozen_today):
    from datetime import timedelta
    from decimal import Decimal

    from apps.programs.models import BenefitTier
    from apps.programs.selectors import activation_problem, current_term

    settings.DEMO_ACTIVE = True
    loader.load()
    youth = Program.objects.get(slug="youth-grant")
    assert not youth.is_active
    assert activation_problem(youth, current_term()) is None
    former = User.objects.get(email="former.staff@scholarsync.test")
    assert (former.full_name, former.is_active, former.memberships.count()) == (
        "Ramil Ocampo",
        False,
        0,
    )
    term = current_term()
    assert term is not None
    AcademicTerm.objects.get_or_create(
        school_year_start=term.school_year_start + 1,
        term=AcademicTerm.Term.FIRST,
        defaults={
            "starts_on": term.ends_on + timedelta(days=1),
            "ends_on": term.ends_on + timedelta(days=150),
        },
    )
    loader.load()
    loader.load()
    change = BenefitTier.objects.get(
        program__slug="tcu-ceaa", effective_from__school_year_start=term.school_year_start + 1
    )
    assert (change.base_amount, change.merit_amount) == (Decimal("5500.00"), Decimal("11000.00"))
    assert Program.objects.filter(slug="youth-grant").count() == 1
    assert User.objects.filter(email="former.staff@scholarsync.test").count() == 1


@pytest.mark.django_db
def test_demo_has_report_samples(demo_app, settings, frozen_today, stored):
    from apps.reports.models import Report
    from apps.workspace.models import Notification

    settings.DEMO_ACTIVE = True
    loader.load()
    loader.load()
    reports = {report.title: report for report in Report.objects.filter(program__slug="tcu-ceaa")}
    assert {title: report.status for title, report in reports.items()} == {
        "Semester disbursement summary": "accepted",
        "Monthly applications report": "returned",
        "Quarterly scholar update": "submitted",
        "Scholar attendance summary": "with_head",
        "Renewal compliance checklist": "accepted",  # rev 36
        "Budget utilization report": "accepted",
    }
    # Everything but the report with the head was sent to the office (rev 33).
    assert {title for title, report in reports.items() if report.sent_at is None} == {
        "Scholar attendance summary"
    }
    sender = reports["Quarterly scholar update"].sent_by
    assert sender is not None and sender.email == "head@scholarsync.test"
    assert reports["Monthly applications report"].review_note
    accepted = reports["Semester disbursement summary"]
    assert accepted.period_end < reports["Quarterly scholar update"].period_start
    for report in reports.values():
        (version,) = report.files.all()
        assert version.file.purpose == "report"
        assert version.file.key == f"files/report/{version.file.pk}"
    assert len([key for key, _body, _type in stored if key.startswith("files/report/")]) == 10
    unread = Notification.objects.filter(read_at=None)
    office = unread.filter(recipient__email="office@scholarsync.test", kind="report_submitted")
    assert office.count() == 2  # CEAA's quarterly update and the LANI tier breakdown
    head = unread.filter(recipient__email="head@scholarsync.test")
    assert sorted(head.filter(kind__startswith="report").values_list("kind", flat=True)) == [
        "report_for_head",
        "report_returned",
    ]
    staff = unread.filter(recipient__email="staff@scholarsync.test", kind__startswith="report")
    assert not staff.exists()


@pytest.mark.django_db
@pytest.mark.django_db
def test_demo_adds_the_head_report_to_an_older_demo(demo_app, settings, frozen_today, stored):
    """A demo loaded before rev 33 has the other samples; the next run adds only the new one."""
    from apps.reports.models import Report

    settings.DEMO_ACTIVE = True
    loader.load()
    Report.objects.filter(title="Scholar attendance summary").delete()
    loader.load()
    titles = list(Report.objects.values_list("title", flat=True))
    assert len(titles) == 10 and titles.count("Scholar attendance summary") == 1


@pytest.mark.django_db
def test_demo_skips_report_samples_without_storage(demo_app, settings, frozen_today, monkeypatch):
    from apps.reports.models import Report

    monkeypatch.setattr("apps.files.storage.is_configured", lambda: False)
    settings.DEMO_ACTIVE = True
    loader.load()
    assert not Report.objects.exists()


@pytest.mark.django_db
def test_demo_has_lani_applicants_reviewed_by_lani_staff(
    demo_app, settings, frozen_today, stored, client
):
    settings.DEMO_ACTIVE = True
    loader.load()
    rows = {
        a.profile.user.email: a
        for a in Application.objects.filter(program__slug="lani").select_related("profile__user")
        if a.profile.user and a.profile.user.email.startswith("lani.applicant")
    }
    assert {email: row.status for email, row in rows.items()} == {
        a.email: a.state for a in LANI_APPLICANTS
    }
    approved = rows["lani.applicant4@scholarsync.test"]
    assert Award.objects.get(profile=approved.profile).tier.code == "priority"
    up = StudentProfile.objects.get(user__email="lani.applicant1@scholarsync.test")
    college = up.education.get(is_current=True)
    assert college.school is not None
    assert (college.school.name, college.gwa) == ("University of the Philippines", Decimal("1.75"))
    lani_staff = User.objects.get(email="lani.staff@scholarsync.test")
    started = AuditEvent.objects.filter(actor=lani_staff, action="application.review_started")
    assert started.count() == 2  # the one under review and the one approved
    client.force_login(lani_staff)
    waiting = client.get("/staff/lani/applications/")
    assert waiting.context["total"] == 3


@pytest.mark.django_db
def test_demo_has_lani_scholars_due_to_renew(demo_app, settings, frozen_today):
    settings.DEMO_ACTIVE = True
    loader.load()
    loader.load()
    awards = Award.objects.filter(profile__user__email__in=[s.email for s in LANI_SCHOLARS])
    assert awards.count() == 2
    term = application_term(timezone.localdate())
    for award in awards:
        assert renewal_for(award, term).status == RenewalStatus.DUE
    joshua = awards.get(profile__user__email="lani.scholar2@scholarsync.test")
    assert joshua.terms.get().gwa == Decimal("2.75")  # over LANI's 2.50 renewal mark


@pytest.mark.django_db
def test_sample_set_rolls_back_as_a_whole(demo_app, settings, frozen_today, stored, monkeypatch):
    settings.DEMO_ACTIVE = True
    real = loader._decide

    def refuse_withdrawals(application, state, staff, program):
        if state == "withdrawn":
            raise ValidationError("refused")
        real(application, state, staff, program)

    monkeypatch.setattr(loader, "_decide", refuse_withdrawals)
    loader.load()
    assert not User.objects.filter(email="applicant6@scholarsync.test").exists()
    assert User.objects.filter(email="lani.applicant1@scholarsync.test").exists()


@pytest.mark.django_db
def test_demo_has_lani_report_samples(demo_app, settings, frozen_today, stored):
    from apps.reports.models import Report
    from apps.workspace.models import Notification

    settings.DEMO_ACTIVE = True
    loader.load()
    loader.load()
    reports = {r.title: r for r in Report.objects.filter(program__slug="lani")}
    assert {title: r.status for title, r in reports.items()} == {
        "LANI applications summary": "accepted",
        "LANI school list update": "returned",
        "LANI tier breakdown": "submitted",
        "LANI scholar grade review": "with_head",
    }
    staff_report = reports["LANI applications summary"]
    assert staff_report.submitted_by.email == "lani.staff@scholarsync.test"
    sent_by = staff_report.sent_by
    assert sent_by is not None and sent_by.email == "lani.head@scholarsync.test"
    unread = Notification.objects.filter(read_at=None, kind__startswith="report")
    lani_head = unread.filter(recipient__email="lani.head@scholarsync.test")
    assert sorted(lani_head.values_list("kind", flat=True)) == [
        "report_for_head",
        "report_returned",
    ]
    assert not unread.filter(recipient__email="lani.staff@scholarsync.test").exists()
