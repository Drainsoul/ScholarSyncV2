from datetime import timedelta
from io import StringIO
from typing import Any

import pytest
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.utils import timezone


def test_prepare_is_idempotent(db: Any) -> None:
    for _ in range(2):
        out = StringIO()
        call_command("prepare", stdout=out)
        assert "ScholarSync is ready." in out.getvalue()


@pytest.mark.parametrize("active", [True, False])
def test_prepare_loads_the_demo_only_when_active(
    settings: Any, monkeypatch: pytest.MonkeyPatch, active: bool
) -> None:
    settings.DEMO_ACTIVE = active
    called: list[str] = []
    monkeypatch.setattr(
        "apps.core.management.commands.prepare.call_command",
        lambda name, *args, **kwargs: called.append(name),
    )
    call_command("prepare", stdout=StringIO())
    assert called[:2] == ["migrate", "createcachetable"]
    assert ("load_demo" in called) is active


def test_cleanup_clears_expired_sessions(db: Any) -> None:
    now = timezone.now()
    Session.objects.create(session_key="old", session_data="x", expire_date=now - timedelta(days=1))
    Session.objects.create(
        session_key="live", session_data="x", expire_date=now + timedelta(days=1)
    )
    call_command("cleanup")
    assert list(Session.objects.values_list("session_key", flat=True)) == ["live"]


def test_run_worker_once_runs_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        "apps.core.management.commands.run_worker.call_command",
        lambda name, *args, **kwargs: called.append(name),
    )
    call_command("run_worker", "--once", stdout=StringIO())
    assert called == ["cleanup"]
