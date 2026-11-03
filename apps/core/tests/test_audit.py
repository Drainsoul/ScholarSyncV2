import pytest

from apps.accounts.tests.factories import UserFactory
from apps.core.audit import client_ip, hash_ip, record
from apps.core.models import AuditEvent
from apps.programs.tests.factories import ProgramFactory


def test_record_stores_who_what_and_where(db, rf):
    actor = UserFactory.create()
    target = UserFactory.create()
    program = ProgramFactory.create()
    event = record(
        actor=actor,
        action="user.created",
        target=target,
        program=program,
        data={"role": "staff"},
        request=rf.get("/", REMOTE_ADDR="203.0.113.7"),
    )
    event.refresh_from_db()
    assert event.actor == actor
    assert event.program == program
    assert event.action == "user.created"
    assert event.target_type == "accounts.user"
    assert event.target_id == str(target.pk)
    assert event.data == {"role": "staff"}


def test_record_without_target_or_request(db):
    event = record(actor=None, action="x.y")
    assert event.target_type == ""
    assert event.target_id == ""
    assert event.ip_hash == ""
    assert event.data == {}


def test_ip_is_hashed_never_stored(db, rf):
    event = record(actor=None, action="x.y", request=rf.get("/", REMOTE_ADDR="203.0.113.7"))
    assert "203.0.113.7" not in event.ip_hash
    assert len(event.ip_hash) == 64
    assert event.ip_hash == hash_ip("203.0.113.7")


def test_hash_ip_is_empty_for_empty():
    assert hash_ip("") == ""


def test_client_ip_is_empty_without_a_request():
    assert client_ip(None) == ""


def test_client_ip_is_empty_when_the_address_is_unknown(rf):
    request = rf.get("/")
    request.META.pop("REMOTE_ADDR", None)
    assert client_ip(request) == ""


def test_audit_events_cannot_change_or_be_deleted(db):
    event = record(actor=None, action="x.y")
    event.action = "x.z"
    with pytest.raises(ValueError):
        event.save()
    with pytest.raises(ValueError):
        event.delete()
    assert AuditEvent.objects.get(pk=event.pk).action == "x.y"
