"""The audit log for the office (every event) and program heads (own program) — M11c."""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.activity import FEED_ACTIONS, VERBS, recent_activity
from apps.core.audit import record
from apps.core.models import AuditEvent
from apps.programs.models import Program, ProgramMembership
from apps.programs.tests.factories import MembershipFactory, ProgramFactory

pytestmark = pytest.mark.django_db

TZ = timezone.get_default_timezone()
OFFICE_URL = "/office/audit/"


def _office(client: Any) -> User:
    user = UserFactory.create(role=User.Role.SUPER_ADMIN)
    client.force_login(user)
    return user


def _head(client: Any, program: Program) -> User:
    user = MembershipFactory.create(program=program, level=ProgramMembership.Level.HEAD).user
    client.force_login(user)
    return user


def _staff_actor(name: str = "Krista Kelley") -> User:
    return UserFactory.create(role=User.Role.STAFF, full_name=name)


def _at(event: AuditEvent, moment: datetime) -> None:
    """Back-date an event. The model is append-only, so this goes around it in SQL."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("UPDATE core_auditevent SET at = %s WHERE id = %s", [moment, event.pk])


def _head_url(program: Program) -> str:
    return reverse("audit:program", kwargs={"program": program.slug})


def test_office_sees_all_events_newest_first_50_a_page(client: Any) -> None:
    _office(client)
    actor = _staff_actor()
    program = ProgramFactory.create(name="LANI")
    now = timezone.now()
    for n in range(55):
        event = record(actor=actor, action="award.created", program=program, data={"n": n})
        _at(event, now - timedelta(minutes=n))
    # The office's own sign-in is an event too (M12); the Scholars group holds only these.
    html = client.get(OFFICE_URL + "?group=scholars").content.decode()
    assert html.count("Added a scholar") == 50
    assert html.index("n: 0<") < html.index("n: 1<")
    assert "n: 50<" not in html
    assert "n: 50<" in client.get(OFFICE_URL + "?group=scholars&page=2").content.decode()


def test_filters_group_dates_who_program(client: Any) -> None:
    _office(client)
    tcu = ProgramFactory.create(name="TCU CEAA")
    lani = ProgramFactory.create(name="LANI")
    first, second = _staff_actor("Krista Kelley"), _staff_actor("Shannon Briggs")
    late = record(actor=first, action="disbursement.approved", program=tcu, data={"tag": "late"})
    _at(late, datetime(2026, 11, 10, 23, 59, tzinfo=TZ))
    early = record(actor=first, action="award.created", program=tcu, data={"tag": "early"})
    _at(early, datetime(2026, 11, 9, 8, 0, tzinfo=TZ))
    other = record(actor=second, action="disbursement.approved", program=lani, data={"tag": "lani"})
    _at(other, datetime(2026, 11, 10, 9, 0, tzinfo=TZ))
    loose = record(actor=None, action="user.created", data={"tag": "loose"})
    _at(loose, datetime(2026, 11, 10, 9, 0, tzinfo=TZ))

    def tags(query: str) -> set[str]:
        html = client.get(OFFICE_URL + query).content.decode()
        return {tag for tag in ("late", "early", "lani", "loose") if f"tag: {tag}<" in html}

    assert tags("") == {"late", "early", "lani", "loose"}
    assert tags("?group=money") == {"late", "lani"}
    assert tags("?start=2026-11-10&end=2026-11-10") == {"late", "lani", "loose"}
    assert tags(f"?who={first.pk}") == {"late", "early"}
    assert tags(f"?program={tcu.pk}") == {"late", "early"}
    assert tags("?program=none") == {"loose"}
    assert "Showing one person" in client.get(OFFICE_URL + f"?who={first.pk}").content.decode()


def test_bad_filter_values_fall_back(client: Any) -> None:
    _office(client)
    record(actor=_staff_actor(), action="award.created", data={"tag": "x"})
    for query in (
        "?group=nope",
        "?start=2026-13-01&end=abc",
        "?who=-4",
        "?program=999999",
        "?program=abc",
        "?page=zz",
    ):
        response = client.get(OFFICE_URL + query)
        assert response.status_code == 200
        assert "tag: x<" in response.content.decode()


def test_head_sees_only_own_program(client: Any) -> None:
    tcu = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    lani = ProgramFactory.create(slug="lani", name="LANI")
    _head(client, tcu)
    lani_staff = _staff_actor("Shannon Briggs")
    record(actor=_staff_actor(), action="award.created", program=tcu, data={"tag": "tcu"})
    record(actor=lani_staff, action="award.created", program=lani, data={"tag": "lani"})
    record(actor=lani_staff, action="award.created", program=tcu, data={"tag": "visit"})
    record(actor=None, action="user.created", data={"tag": "loose"})
    html = client.get(_head_url(tcu) + f"?program={lani.pk}").content.decode()
    assert "tag: tcu<" in html and "tag: visit<" in html
    assert "tag: lani<" not in html and "tag: loose<" not in html
    assert 'name="program"' not in html  # no program filter for heads
    html = client.get(_head_url(tcu) + f"?who={lani_staff.pk}").content.decode()
    assert "tag: visit<" in html and "tag: lani<" not in html and "tag: tcu<" not in html
    html = client.get(_head_url(tcu) + "?program=none").content.decode()
    assert "tag: loose<" not in html


def test_staff_member_403(client: Any) -> None:
    program = ProgramFactory.create(slug="tcu-ceaa")
    client.force_login(MembershipFactory.create(program=program).user)
    assert client.get(_head_url(program)).status_code == 403


def test_head_and_office_get_audit_link_staff_do_not(client: Any) -> None:
    program = ProgramFactory.create(slug="tcu-ceaa")
    dashboard = reverse("workspace:dashboard", kwargs={"program": program.slug})
    client.force_login(MembershipFactory.create(program=program).user)
    assert _head_url(program).encode() not in client.get(dashboard).content
    _head(client, program)
    labels = [item["label"] for item in client.get(dashboard).context["nav_secondary"]]
    assert labels == ["Settings", "Audit log"]
    _office(client)
    nav = client.get(reverse("office:home")).context["nav_items"]
    item = next(item for item in nav if item["label"] == "Audit log")
    assert (item["url"], item["icon"]) == (OFFICE_URL, "shield")


def test_student_actor_reads_a_student_without_filter_link(client: Any) -> None:
    _office(client)
    student = UserFactory.create(full_name="Maria Santos")
    record(actor=student, action="application.submitted")
    html = client.get(OFFICE_URL).content.decode()
    assert "A student" in html
    assert "Maria Santos" not in html
    assert f"who={student.pk}" not in html


def test_ip_hash_never_rendered(client: Any, rf: Any) -> None:
    _office(client)
    request = rf.get("/", REMOTE_ADDR="203.0.113.9")
    event = record(actor=_staff_actor(), action="award.created", request=request)
    assert event.ip_hash
    html = client.get(OFFICE_URL).content.decode()
    assert event.ip_hash not in html
    assert "203.0.113.9" not in html


def test_query_count_with_50_events(client: Any, django_assert_max_num_queries: Any) -> None:
    _office(client)
    programs = ProgramFactory.create_batch(3)
    actors = [_staff_actor() for _ in range(5)]
    for n in range(50):
        record(actor=actors[n % 5], action="award.created", program=programs[n % 3])
    with django_assert_max_num_queries(14):
        assert client.get(OFFICE_URL).status_code == 200


def test_feed_ignores_settings_actions() -> None:
    actor = _staff_actor()
    record(actor=actor, action="program.rules_changed")
    record(actor=actor, action="report.submitted")
    assert [event.action for event, _ in recent_activity()] == ["report.submitted"]
    assert "program.rules_changed" in VERBS
    assert "program.rules_changed" not in FEED_ACTIONS
    assert FEED_ACTIONS <= set(VERBS)


def test_every_recorded_action_has_a_sentence() -> None:
    source = ""
    for path in Path(settings.BASE_DIR, "apps").rglob("*.py"):
        if "tests" in path.parts or "demo" in path.parts:
            continue
        source += path.read_text(encoding="utf-8")
    actions = set(re.findall(r'action=\s*"([a-z_]+\.[a-z_]+)"', source))
    for pair in re.findall(r'"([a-z_]+\.[a-z_]+)" if \w+ else "([a-z_]+\.[a-z_]+)"', source):
        actions |= set(pair)
    assert len(actions) > 60
    missing = sorted(action for action in actions if action not in VERBS)
    assert missing == []


def test_head_who_filter_never_names_an_outsider(client: Any) -> None:
    """A head can't learn another program's staff names by guessing account ids."""
    tcu = ProgramFactory.create(slug="tcu-ceaa", name="TCU CEAA")
    lani = ProgramFactory.create(slug="lani", name="LANI")
    _head(client, tcu)
    outsider = _staff_actor("Shannon Briggs")
    record(actor=outsider, action="award.created", program=lani)
    html = client.get(_head_url(tcu) + f"?who={outsider.pk}").content.decode()
    assert "Shannon Briggs" not in html
    assert "Showing one person's actions: this person." in html


def test_extreme_dates_fall_back(client: Any) -> None:
    _office(client)
    record(actor=_staff_actor(), action="award.created", data={"tag": "x"})
    for query in ("?end=9999-12-31", "?start=0001-01-01", "?start=9999-12-31&end=9999-12-31"):
        response = client.get(OFFICE_URL + query)
        assert response.status_code == 200
        assert "tag: x<" in response.content.decode()
