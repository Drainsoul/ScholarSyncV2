"""Double posts and account races never answer 500 (M12).

Each pre-check is a named helper so a test can make it miss, as a second request racing the first
would; the unique index then decides, and the service turns the clash into the form error."""

import threading
from decimal import Decimal
from typing import Any

import pytest
from allauth.account.models import EmailAddress
from django.core.exceptions import ValidationError
from django.db import connection

from apps.accounts import services as account_services
from apps.accounts.models import User
from apps.accounts.services import (
    EMAIL_TAKEN,
    KEEP_ONE_OFFICE,
    create_account,
    send_welcome,
    set_account_active,
)
from apps.accounts.tests.factories import UserFactory
from apps.programs import services as program_services
from apps.programs.models import BenefitTier, Program, School
from apps.programs.services import (
    SCHOOL_TAKEN,
    SLUG_TAKEN,
    TIER_CHANGED,
    change_tier_amounts,
    create_program,
    save_school,
)
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    ProgramFactory,
    SchoolFactory,
)
from apps.workspace.models import EmailOutbox


def _office() -> User:
    return UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)


def _messages(error: ValidationError) -> list[str]:
    return error.messages


@pytest.mark.django_db
def test_create_program_slug_race_is_a_form_error(monkeypatch: pytest.MonkeyPatch) -> None:
    office = _office()
    ProgramFactory.create(slug="arts-grant")
    monkeypatch.setattr(program_services, "_slug_taken", lambda slug: False)
    with pytest.raises(ValidationError) as caught:
        create_program(actor=office, slug="arts-grant", name="Arts", description="")
    assert _messages(caught.value) == [SLUG_TAKEN]
    assert Program.objects.filter(slug="arts-grant").count() == 1


@pytest.mark.django_db
def test_school_name_race_is_a_form_error(monkeypatch: pytest.MonkeyPatch) -> None:
    office = _office()
    SchoolFactory.create(name="Taguig High")
    monkeypatch.setattr(program_services, "_school_taken", lambda name, school: False)
    with pytest.raises(ValidationError) as caught:
        save_school(
            actor=office,
            school=None,
            name="Taguig High",
            type=School.Type.PUBLIC,
            grading_scale=School.Scale.PERCENT,
            is_in_taguig=True,
        )
    assert _messages(caught.value) == [SCHOOL_TAKEN]


@pytest.mark.django_db
def test_tier_change_race_is_a_form_error(monkeypatch: pytest.MonkeyPatch) -> None:
    office = _office()
    program = ProgramFactory.create()
    current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    later = AcademicTermFactory.create(school_year_start=2026, term=2)
    BenefitTierFactory.create(program=program, code="standard", effective_from=current)
    change_tier_amounts(
        actor=office,
        program=program,
        code="standard",
        base_amount=Decimal("6000.00"),
        merit_amount=Decimal("0.00"),
        effective_from=later,
    )
    real = program_services._tier_row_for

    def missed(program: Program, code: str, term: Any) -> Any:
        latest, _same = real(program, code, term)
        return latest, None  # a racing request that read before the first one's row existed

    monkeypatch.setattr(program_services, "_tier_row_for", missed)
    with pytest.raises(ValidationError) as caught:
        change_tier_amounts(
            actor=office,
            program=program,
            code="standard",
            base_amount=Decimal("6500.00"),
            merit_amount=Decimal("0.00"),
            effective_from=later,
        )
    assert _messages(caught.value) == [TIER_CHANGED]
    assert BenefitTier.objects.filter(program=program, effective_from=later).count() == 1


@pytest.mark.django_db
def test_account_email_race_is_a_form_error(monkeypatch: pytest.MonkeyPatch) -> None:
    office = _office()
    UserFactory.create(email="new.staff@scholarsync.test")
    monkeypatch.setattr(account_services, "_email_taken", lambda email: False)
    with pytest.raises(ValidationError) as caught:
        create_account(
            actor=office,
            email="new.staff@scholarsync.test",
            full_name="New Staff",
            role=User.Role.STAFF,
        )
    assert _messages(caught.value) == [EMAIL_TAKEN]


@pytest.mark.django_db
def test_email_of_another_users_address_refused() -> None:
    office = _office()
    owner = UserFactory.create(email="first@scholarsync.test")
    EmailAddress.objects.create(user=owner, email="second@scholarsync.test", verified=True)
    with pytest.raises(ValidationError) as caught:
        create_account(
            actor=office,
            email="SECOND@scholarsync.test",
            full_name="Someone",
            role=User.Role.STAFF,
        )
    assert _messages(caught.value) == [EMAIL_TAKEN]


@pytest.mark.django_db
def test_welcome_not_sent_to_deactivated_account() -> None:
    office = _office()
    account = create_account(
        actor=office, email="later@scholarsync.test", full_name="Later", role=User.Role.STAFF
    )
    set_account_active(actor=office, user=account, active=False)
    before = EmailOutbox.objects.filter(kind="staff_welcome").count()
    send_welcome(actor=office, user=User.objects.get(pk=account.pk))
    assert EmailOutbox.objects.filter(kind="staff_welcome").count() == before


def _race(monkeypatch: pytest.MonkeyPatch, module: Any, calls: list[Any]) -> list[str]:
    """Run `calls` in two threads that pause at a barrier inside their transaction (in `record`),
    so without a lock both would decide before either writes."""
    barrier = threading.Barrier(2, timeout=2)
    real_record = module.record

    def paused_record(**kwargs: Any) -> Any:
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        return real_record(**kwargs)

    monkeypatch.setattr(module, "record", paused_record)
    outcomes: list[str] = []

    def run(call: Any) -> None:
        try:
            call()
            outcomes.append("done")
        except ValidationError as error:
            outcomes.append(" ".join(error.messages))
        except Exception as error:  # noqa: BLE001 - any other error is the bug
            outcomes.append(type(error).__name__)
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return outcomes


@pytest.mark.django_db(transaction=True)
def test_two_offices_deactivating_each_other_leave_one(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = _office(), _office()
    outcomes = _race(
        monkeypatch,
        account_services,
        [
            lambda: set_account_active(
                actor=User.objects.get(pk=first.pk),
                user=User.objects.get(pk=second.pk),
                active=False,
            ),
            lambda: set_account_active(
                actor=User.objects.get(pk=second.pk),
                user=User.objects.get(pk=first.pk),
                active=False,
            ),
        ],
    )
    assert sorted(outcomes) == sorted(["done", KEEP_ONE_OFFICE])
    assert User.objects.filter(role=User.Role.SUPER_ADMIN, is_active=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_account_email_race_one_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    office = _office()
    barrier = threading.Barrier(2, timeout=2)
    real = account_services._email_taken

    def checked_together(email: str) -> bool:
        taken = real(email)
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        return taken

    monkeypatch.setattr(account_services, "_email_taken", checked_together)
    outcomes: list[str] = []

    def run() -> None:
        try:
            create_account(
                actor=User.objects.get(pk=office.pk),
                email="twice@scholarsync.test",
                full_name="Twice",
                role=User.Role.STAFF,
            )
            outcomes.append("done")
        except ValidationError as error:
            outcomes.append(" ".join(error.messages))
        except Exception as error:  # noqa: BLE001 - an IntegrityError here is the bug
            outcomes.append(type(error).__name__)
        finally:
            connection.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == sorted(["done", EMAIL_TAKEN])
    assert User.objects.filter(email__iexact="twice@scholarsync.test").count() == 1
