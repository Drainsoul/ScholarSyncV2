from decimal import Decimal
from typing import Any

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.awards.tests.factories import AwardFactory, ScholarTermFactory
from apps.core.models import AuditEvent
from apps.core.tests.auth import reauthenticated, replay_after_password, signed_in_long_ago
from apps.money.selectors import amount_for
from apps.programs.models import AcademicTerm, BenefitTier, Program, ProgramMembership
from apps.programs.selectors import tiers_in_force
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    MembershipFactory,
    ProgramFactory,
)

pytestmark = pytest.mark.django_db

IN_USE = "Records already use the {term} amounts for {tier}. Pick a later term."
PAST = "Pick the current term or a later one."


@pytest.fixture
def terms() -> tuple[AcademicTerm, AcademicTerm, AcademicTerm]:
    past = AcademicTermFactory.create(school_year_start=2025, term=2)
    current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    later = AcademicTermFactory.create(school_year_start=2026, term=2)
    return past, current, later


@pytest.fixture
def program() -> Program:
    return ProgramFactory.create(slug="tcu-ceaa")


def _head(program: Program) -> User:
    return MembershipFactory.create(
        program=program, level=ProgramMembership.Level.HEAD, user__verified=True
    ).user


def _url(name: str, program: Program, **kwargs: object) -> str:
    return reverse(f"settings:{name}", kwargs={"program": program.slug, **kwargs})


def _change(code: str, term: AcademicTerm, **data: str) -> dict[str, str]:
    return {"action": "change", "effective_from": str(term.pk), **data}


def _standard(program: Program, term: AcademicTerm) -> BenefitTier:
    return BenefitTierFactory.create(
        program=program,
        code="standard",
        name="Standard",
        effective_from=term,
        base_amount=Decimal("5000.00"),
        merit_amount=Decimal("10000.00"),
    )


def test_add_tier_from_current_term(client: Any, terms: Any, program: Program) -> None:
    _, current, _ = terms
    reauthenticated(client, _head(program))
    response = client.post(
        _url("tier-new", program),
        {
            "code": "honors",
            "name": "Honors",
            "base_amount": "7500.00",
            "merit_amount": "12500.00",
            "effective_from": str(current.pk),
            "sort_order": "1",
        },
    )
    assert response.status_code == 302
    tier = BenefitTier.objects.get(program=program, code="honors")
    assert (tier.base_amount, tier.effective_from) == (Decimal("7500.00"), current)
    event = AuditEvent.objects.get(action="tier.added")
    assert event.data == {
        "code": "honors",
        "term": current.pk,
        "base_amount": "7500.00",
        "merit_amount": "12500.00",
    }


def test_code_taken_refused(client: Any, terms: Any, program: Program) -> None:
    _, current, _ = terms
    _standard(program, current)
    reauthenticated(client, _head(program))
    response = client.post(
        _url("tier-new", program),
        {
            "code": "standard",
            "name": "Again",
            "base_amount": "1.00",
            "merit_amount": "0",
            "effective_from": str(current.pk),
            "sort_order": "0",
        },
    )
    assert "That tier code is taken." in response.content.decode()
    assert BenefitTier.objects.filter(program=program).count() == 1


def test_change_refused_when_current_row_in_use(client: Any, terms: Any, program: Program) -> None:
    _, current, _ = terms
    tier = _standard(program, current)
    award = AwardFactory.create(source_application__program=program, tier=tier)
    ScholarTermFactory.create(award=award, term=current, tier=tier)
    reauthenticated(client, _head(program))
    response = client.post(
        _url("tier-change", program, code="standard"),
        _change("standard", current, base_amount="6000.00", merit_amount="11000.00"),
    )
    assert IN_USE.format(term=current, tier="Standard") in response.content.decode().replace(
        "&#x27;", "'"
    )
    tier.refresh_from_db()
    assert tier.base_amount == Decimal("5000.00")


def test_change_from_next_term_adds_row_and_keeps_amount_for(
    client: Any, terms: Any, program: Program
) -> None:
    _, current, later = terms
    tier = _standard(program, current)
    award = AwardFactory.create(source_application__program=program, tier=tier)
    record = ScholarTermFactory.create(award=award, term=current, tier=tier)
    reauthenticated(client, _head(program))
    client.post(
        _url("tier-change", program, code="standard"),
        _change("standard", later, base_amount="5500.00", merit_amount="11000.00"),
    )
    new = BenefitTier.objects.get(program=program, code="standard", effective_from=later)
    assert (new.name, new.base_amount, new.merit_amount) == (
        "Standard",
        Decimal("5500.00"),
        Decimal("11000.00"),
    )
    record.refresh_from_db()
    assert amount_for(record) == (Decimal("5000.00"), False)
    assert tiers_in_force(program, later) == [new]
    assert AuditEvent.objects.filter(action="tier.changed").count() == 1


def test_change_unused_same_term_row_updates_in_place(
    client: Any, terms: Any, program: Program
) -> None:
    _, current, _ = terms
    tier = _standard(program, current)
    reauthenticated(client, _head(program))
    client.post(
        _url("tier-change", program, code="standard"),
        _change("standard", current, base_amount="6000.00", merit_amount="0"),
    )
    tier.refresh_from_db()
    assert (tier.base_amount, tier.merit_amount) == (Decimal("6000.00"), Decimal("0.00"))
    assert BenefitTier.objects.filter(program=program).count() == 1


def test_past_term_refused(client: Any, terms: Any, program: Program) -> None:
    past, current, _ = terms
    _standard(program, current)
    reauthenticated(client, _head(program))
    response = client.post(
        _url("tier-change", program, code="standard"),
        _change("standard", past, base_amount="1.00", merit_amount="0"),
    )
    assert PAST in response.content.decode()
    assert BenefitTier.objects.filter(program=program).count() == 1


def test_stop_tier_ends_it_in_tiers_in_force(client: Any, terms: Any, program: Program) -> None:
    _, current, later = terms
    _standard(program, current)
    reauthenticated(client, _head(program))
    client.post(
        _url("tier-change", program, code="standard"),
        {"action": "stop", "effective_from": str(later.pk)},
    )
    assert len(tiers_in_force(program, current)) == 1
    assert tiers_in_force(program, later) == []
    assert AuditEvent.objects.filter(action="tier.stopped").count() == 1


def test_tier_change_needs_reauthentication(client: Any, terms: Any, program: Program) -> None:
    _, current, later = terms
    _standard(program, current)
    signed_in_long_ago(client, _head(program))
    response = client.post(
        _url("tier-change", program, code="standard"),
        _change("standard", later, base_amount="5500.00", merit_amount="0"),
    )
    assert response.status_code == 302
    assert response.url.startswith(reverse("account_reauthenticate"))
    assert BenefitTier.objects.filter(program=program).count() == 1


def test_tier_change_replays_after_password(client: Any, terms: Any, program: Program) -> None:
    _, current, later = terms
    _standard(program, current)
    signed_in_long_ago(client, _head(program))
    response = client.post(
        _url("tier-change", program, code="standard"),
        _change("standard", later, base_amount="5500.00", merit_amount="0"),
    )
    replayed = replay_after_password(client, response)
    assert replayed.status_code == 302
    assert replayed.url == _url("tiers", program)
    assert BenefitTier.objects.filter(program=program, effective_from=later).count() == 1


def test_unknown_code_404(client: Any, terms: Any, program: Program) -> None:
    reauthenticated(client, _head(program))
    assert client.get(_url("tier-change", program, code="nope")).status_code == 404


def test_tiers_page_lists_current_and_upcoming(client: Any, terms: Any, program: Program) -> None:
    _, current, later = terms
    _standard(program, current)
    BenefitTierFactory.create(
        program=program,
        code="standard",
        name="Standard",
        effective_from=later,
        base_amount=Decimal("5500.00"),
    )
    reauthenticated(client, _head(program))
    html = client.get(_url("tiers", program)).content.decode()
    assert "₱5,000.00" in html and "₱10,000.00" in html
    assert f"₱5,500.00 from {later}" in html


def test_tiers_page_query_count(
    client: Any, terms: Any, program: Program, django_assert_max_num_queries: Any
) -> None:
    _, current, _ = terms
    for n in range(50):
        BenefitTierFactory.create(program=program, code=f"t{n}", effective_from=current)
    reauthenticated(client, _head(program))
    with django_assert_max_num_queries(14):
        assert client.get(_url("tiers", program)).status_code == 200
