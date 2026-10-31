from datetime import timedelta
from io import StringIO
from typing import Any

import pytest
from django.contrib.sessions.models import Session
from django.core.management import call_command, get_commands
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
    if active and "load_demo" not in get_commands():
        pytest.skip("the demo app has been deleted")
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


def test_run_worker_stops_on_sigterm_after_current_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import signal

    called: list[str] = []

    def fake(name: str, *args: Any, **kwargs: Any) -> None:
        called.append(name)
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM, None)

    monkeypatch.setattr("apps.core.management.commands.run_worker.call_command", fake)
    out = StringIO()
    call_command("run_worker", "--interval", "60", stdout=out)
    assert called == ["cleanup"]
    assert "Worker stopped." in out.getvalue()


def test_run_worker_survives_a_failing_cycle(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import signal

    called: list[str] = []

    def fake(name: str, *args: Any, **kwargs: Any) -> None:
        called.append(name)
        if len(called) == 1:
            raise RuntimeError("db restarting")
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM, None)

    monkeypatch.setattr("apps.core.management.commands.run_worker.call_command", fake)
    monkeypatch.setattr(
        "apps.core.management.commands.run_worker.threading.Event.wait",
        lambda self, timeout=None: False,
    )
    call_command("run_worker", "--interval", "1", stdout=StringIO())
    assert called == ["cleanup", "cleanup"]
    assert "Worker cycle failed" in caplog.text


@pytest.fixture(autouse=True)
def _no_connection_cleanup(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if "db" not in request.fixturenames:
        monkeypatch.setattr(
            "apps.core.management.commands.run_worker.close_old_connections", lambda: None
        )
