import re
from pathlib import Path

import pytest
from django.conf import settings

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.activity import VERBS, describe, recent_activity
from apps.core.audit import record
from apps.programs.tests.factories import ProgramFactory

pytestmark = pytest.mark.django_db


def test_known_action_reads_as_a_sentence() -> None:
    actor = UserFactory.create(role=User.Role.STAFF, full_name="Krista Kelley")
    program = ProgramFactory.create(name="TCU CEAA")
    event = record(actor=actor, action="disbursement.approved", program=program)
    assert describe(event) == "Krista Kelley approved a payout (TCU CEAA)"


def test_unknown_action_falls_back() -> None:
    actor = UserFactory.create(role=User.Role.STAFF, full_name="Krista Kelley")
    event = record(actor=actor, action="file.viewed")
    assert describe(event) == "Krista Kelley: file.viewed"


def test_systemless_actor() -> None:
    event = record(actor=None, action="application.expired")
    assert describe(event).startswith("The system ")


def test_student_actor_is_not_named() -> None:
    student = UserFactory.create(full_name="Maria Santos")
    program = ProgramFactory.create(name="LANI")
    event = record(actor=student, action="application.submitted", program=program)
    assert describe(event) == "A student submitted an application (LANI)"


def test_every_verb_is_a_real_action() -> None:
    source = ""
    for path in Path(settings.BASE_DIR, "apps").rglob("*.py"):
        if "tests" in path.parts or path.name == "activity.py":
            continue
        source += path.read_text(encoding="utf-8")
    missing = [action for action in VERBS if not re.search(rf'"{re.escape(action)}"', source)]
    assert missing == []


def test_recent_activity_skips_actions_without_a_verb() -> None:
    actor = UserFactory.create(role=User.Role.STAFF, full_name="Krista Kelley")
    for _ in range(10):
        record(actor=actor, action="award.created")
    record(actor=actor, action="file.viewed")
    rows = recent_activity()
    assert len(rows) == 8
    assert all(event.action == "award.created" for event, _ in rows)
    assert rows[0][1] == "Krista Kelley added a scholar"
