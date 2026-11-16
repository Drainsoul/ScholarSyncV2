from datetime import date

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.models import AcademicTerm, ProgramMembership
from apps.programs.services import (
    BACKWARD,
    SAME_TERM,
    add_membership,
    add_school_year,
    set_current_term,
)
from apps.programs.tests.factories import AcademicTermFactory, ProgramFactory


def test_add_membership_audits_with_the_program(db):
    actor = UserFactory.create(role=User.Role.SUPER_ADMIN)
    user = UserFactory.create(role=User.Role.STAFF)
    program = ProgramFactory.create()
    membership = add_membership(
        actor=actor, user=user, program=program, level=ProgramMembership.Level.HEAD
    )
    assert membership.level == "head"
    event = AuditEvent.objects.get(action="membership.added")
    assert event.program == program
    assert event.actor == actor
    assert event.target_id == str(membership.pk)
    assert event.data == {"level": "head"}


def test_students_cannot_be_members(db):
    with pytest.raises(ValidationError):
        add_membership(
            actor=None,
            user=UserFactory.create(),
            program=ProgramFactory.create(),
            level=ProgramMembership.Level.STAFF,
        )
    assert not ProgramMembership.objects.exists()


@pytest.mark.parametrize(
    "actor_fields",
    [
        {"role": User.Role.STAFF},
        {"role": User.Role.STUDENT},
        {"role": User.Role.SUPER_ADMIN, "is_active": False},
    ],
)
def test_only_an_active_super_admin_adds_members(db, actor_fields):
    with pytest.raises(PermissionDenied):
        add_membership(
            actor=UserFactory.create(**actor_fields),
            user=UserFactory.create(role=User.Role.STAFF),
            program=ProgramFactory.create(),
            level=ProgramMembership.Level.STAFF,
        )
    assert not ProgramMembership.objects.exists()
    assert not AuditEvent.objects.filter(action="membership.added").exists()


# --- School years and the current term (M9) ---


def office_user() -> User:
    return UserFactory.create(role=User.Role.SUPER_ADMIN)


def test_add_school_year_creates_three_terms(db):
    AcademicTermFactory.create(school_year_start=2026, term=1)
    terms = add_school_year(actor=office_user(), start=2027)
    assert [(t.school_year_start, t.term) for t in terms] == [(2027, 1), (2027, 2), (2027, 3)]
    assert [(t.starts_on, t.ends_on) for t in terms] == [
        (date(2027, 8, 1), date(2027, 12, 31)),
        (date(2028, 1, 1), date(2028, 5, 31)),
        (date(2028, 6, 1), date(2028, 7, 31)),
    ]
    assert not any(t.is_current for t in terms)
    event = AuditEvent.objects.get(action="term.year_added")
    assert event.data == {"start": 2027}


def test_add_school_year_out_of_order_refused(db):
    AcademicTermFactory.create(school_year_start=2026, term=1)
    for start in (2026, 2028, 2025):
        with pytest.raises(ValidationError) as caught:
            add_school_year(actor=office_user(), start=start)
        assert caught.value.messages == ["Add school year 2027–2028 next."]
    assert AcademicTerm.objects.count() == 1


def test_add_school_year_first_ever(db):
    assert len(add_school_year(actor=office_user(), start=2030)) == 3


def test_add_school_year_staff_forbidden(db):
    with pytest.raises(PermissionDenied):
        add_school_year(actor=UserFactory.create(role=User.Role.STAFF), start=2030)


def test_set_current_moves_flag_without_integrity_error(db):
    old = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    new = AcademicTermFactory.create(school_year_start=2026, term=2)
    assert set_current_term(actor=office_user(), term=new) == old
    old.refresh_from_db()
    new.refresh_from_db()
    assert (old.is_current, new.is_current) == (False, True)
    event = AuditEvent.objects.get(action="term.made_current")
    assert event.data == {"from": old.pk}


def test_set_current_with_none_flagged(db):
    term = AcademicTermFactory.create(school_year_start=2026, term=1)
    assert set_current_term(actor=office_user(), term=term) is None
    assert AuditEvent.objects.get(action="term.made_current").data == {"from": None}


def test_set_current_same_refused(db):
    term = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    with pytest.raises(ValidationError) as caught:
        set_current_term(actor=office_user(), term=term)
    assert caught.value.messages == [SAME_TERM]


def test_set_current_backward_refused(db):
    earlier = AcademicTermFactory.create(school_year_start=2025, term=2)
    current = AcademicTermFactory.create(school_year_start=2026, term=1, is_current=True)
    with pytest.raises(ValidationError) as caught:
        set_current_term(actor=office_user(), term=earlier)
    assert caught.value.messages == [BACKWARD]
    current.refresh_from_db()
    assert current.is_current
    assert not AuditEvent.objects.filter(action="term.made_current").exists()


def test_set_current_staff_forbidden(db):
    term = AcademicTermFactory.create(school_year_start=2026, term=1)
    with pytest.raises(PermissionDenied):
        set_current_term(actor=UserFactory.create(role=User.Role.STAFF), term=term)
