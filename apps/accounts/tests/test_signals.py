"""Sign-ins on the audit record (M12, spec §10)."""

from typing import Any

import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.core.activity import describe, recent_activity
from apps.core.audit import record
from apps.core.models import AuditEvent

pytestmark = pytest.mark.django_db

TYPED = "nobody-here@scholarsync.test"


def test_sign_in_and_out_are_audited(client: Any) -> None:
    user = UserFactory.create(email="ana@scholarsync.test", verified=True)
    response = client.post(
        "/accounts/login/",
        {"login": user.email, "password": DEFAULT_PASSWORD},
        REMOTE_ADDR="203.0.113.7",
    )
    assert response.status_code == 302
    signed_in = AuditEvent.objects.get(action="user.signed_in")
    assert signed_in.actor == user
    assert signed_in.ip_hash
    client.post("/accounts/logout/")
    signed_out = AuditEvent.objects.get(action="user.signed_out")
    assert signed_out.actor == user


def test_failed_sign_in_is_audited_without_the_email(client: Any) -> None:
    client.post("/accounts/login/", {"login": TYPED, "password": "wrong-password-1"})
    event = AuditEvent.objects.get(action="user.sign_in_failed")
    assert event.actor is None
    assert event.data == {}
    assert TYPED not in f"{event.target_type} {event.target_id} {event.data}"


def test_sign_in_actions_read_as_sentences() -> None:
    staff = UserFactory.create(role=User.Role.STAFF, full_name="Krista Kelley")
    assert describe(record(actor=staff, action="user.signed_in")) == "Krista Kelley signed in"
    assert describe(record(actor=staff, action="user.signed_out")) == "Krista Kelley signed out"
    assert describe(record(actor=None, action="user.sign_in_failed")) == (
        "Someone failed to sign in"
    )


def test_sign_ins_stay_out_of_the_overview_feed() -> None:
    staff = UserFactory.create(role=User.Role.STAFF)
    record(actor=staff, action="user.signed_in")
    record(actor=None, action="user.sign_in_failed")
    assert recent_activity() == []
