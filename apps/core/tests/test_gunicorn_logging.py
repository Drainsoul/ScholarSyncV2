"""The access log never records a claim token or a reset key (M12).

`redact_atoms` is plain Python and runs everywhere. gunicorn itself imports Unix-only modules
(`grp`, `pwd`), so the logger-class tests run on Linux (CI and the Docker image) only."""

import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.core.gunicorn_logging import redact_atoms

ROOT = Path(__file__).resolve().parents[3]
TOKEN = "S3cr3t-T0k3n"
CLAIM = f"/accounts/claim/{TOKEN}/"
RESET_REFERER = f"https://scholarsync.example/accounts/password/reset/key/1a-{TOKEN}/"


def _raw_atoms(path: str, referer: str) -> dict[str, object]:
    return {
        "r": f"GET {path}?next=/me/ HTTP/1.1",
        "U": path,
        "q": "next=/me/",
        "f": referer,
        "{referer}i": referer,
        "{location}o": path,
        "s": 200,
        "B": 10,
    }


def test_redact_atoms_covers_request_line_path_referer_and_headers() -> None:
    atoms = redact_atoms(_raw_atoms(CLAIM, RESET_REFERER))
    assert not [key for key, value in atoms.items() if TOKEN in str(value)]
    assert atoms["U"] == "/accounts/claim/[redacted]/"
    assert atoms["r"] == "GET /accounts/claim/[redacted]/?next=/me/ HTTP/1.1"
    assert atoms["f"] == "https://scholarsync.example/accounts/password/reset/key/[redacted]/"
    assert atoms["s"] == 200 and atoms["B"] == 10


def test_redact_atoms_keeps_ordinary_paths() -> None:
    atoms = redact_atoms(_raw_atoms("/me/applications/", "https://scholarsync.example/me/"))
    assert atoms["U"] == "/me/applications/"
    assert atoms["f"] == "https://scholarsync.example/me/"


def test_dockerfile_uses_the_redacting_logger() -> None:
    assert "apps.core.gunicorn_logging.RedactingLogger" in (ROOT / "Dockerfile").read_text()


def test_logger_class_redacts_atoms() -> None:
    pytest.importorskip("grp", reason="gunicorn needs Unix modules")
    from gunicorn.config import Config
    from gunicorn.util import load_class

    logger_class = load_class("apps.core.gunicorn_logging.RedactingLogger")
    logger = logger_class(Config())
    environ = {
        "REQUEST_METHOD": "GET",
        "RAW_URI": f"{CLAIM}?next=/me/",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "PATH_INFO": CLAIM,
        "QUERY_STRING": "next=/me/",
        "HTTP_REFERER": RESET_REFERER,
        "REMOTE_ADDR": "203.0.113.9",
    }
    request = SimpleNamespace(headers=[("REFERER", RESET_REFERER)])
    response = SimpleNamespace(status="200 OK", sent=10, headers=[("Location", CLAIM)])
    atoms = logger.atoms(response, request, environ, datetime.timedelta(seconds=1))
    assert not [key for key, value in atoms.items() if TOKEN in str(value)]
