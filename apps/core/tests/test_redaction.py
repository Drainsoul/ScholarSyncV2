import json
import logging
import sys

import pytest

from apps.core.logging import JsonFormatter
from apps.core.redaction import redact, redact_secret_paths
from apps.core.sentry import scrub_event

PSYCOPG_MESSAGE = (
    'duplicate key value violates unique constraint "accounts_user_email_key"\n'
    "DETAIL:  Key (email)=(juan@example.com) already exists."
)


def test_redact_masks_emails_and_constraint_details():
    text = redact(PSYCOPG_MESSAGE)
    assert "juan@example.com" not in text
    assert "accounts_user_email_key" in text  # the constraint name stays: it's debuggable, not PII
    assert "Key (email)=(" not in text


def test_redact_leaves_plain_text_alone():
    assert redact("connection refused") == "connection refused"


def test_json_formatter_redacts_exception_text_and_message():
    try:
        raise ValueError(PSYCOPG_MESSAGE)
    except ValueError:
        record = logging.LogRecord(
            "apps.test",
            logging.ERROR,
            __file__,
            1,
            "save failed for %s",
            ("ana@example.com",),
            sys.exc_info(),
        )
    payload = json.loads(JsonFormatter().format(record))
    assert "juan@example.com" not in payload["exc"]
    assert "ana@example.com" not in payload["msg"]


def test_scrub_event_redacts_exception_values_logentry_extra_threads_and_breadcrumbs():
    event = {
        "exception": {"values": [{"type": "IntegrityError", "value": PSYCOPG_MESSAGE}]},
        "logentry": {"message": "save failed for %s", "params": ["ana@example.com"]},
        "extra": {"email": "ana@example.com"},
        "threads": {"values": [{"stacktrace": {"frames": [{"vars": {"pw": "secret"}}]}}]},
        "breadcrumbs": {"values": [{"message": "saved ana@example.com", "category": "log"}]},
    }
    scrubbed = scrub_event(event, {})
    assert "juan@example.com" not in scrubbed["exception"]["values"][0]["value"]
    assert "params" not in scrubbed["logentry"]
    assert "extra" not in scrubbed
    assert "vars" not in scrubbed["threads"]["values"][0]["stacktrace"]["frames"][0]
    assert "ana@example.com" not in scrubbed["breadcrumbs"]["values"][0]["message"]


def test_scrub_event_keeps_only_the_path_of_the_referer():
    event = {
        "request": {
            "headers": {
                "Referer": "https://scholarsync.example/staff/lani/scholars/?q=Juan+Dela+Cruz#x"
            }
        }
    }
    assert scrub_event(event, {})["request"]["headers"] == {
        "Referer": "https://scholarsync.example/staff/lani/scholars/"
    }


def test_redact_is_linear_on_hostile_input():
    """Exception text can contain user input; the patterns must not backtrack catastrophically."""
    import time

    hostile = [
        "a" * 50_000,
        "a@" + "a." * 25_000,
        ("x" * 60 + "@") * 1_000,
        "DETAIL:" + "z" * 50_000,
    ]
    for text in hostile:
        started = time.perf_counter()
        redact(text)
        assert time.perf_counter() - started < 0.5, text[:20]


def test_redact_masks_every_character_of_a_long_local_part():
    local = "juan.dela.cruz.scholarship.applicant.from.barangay.western.bicutan.2026"
    assert len(local) > 64
    text = redact(f"failed for {local}@gmail.com today")
    assert text == "failed for [email] today"


def test_redact_masks_emails_with_many_labels_or_long_tlds():
    for address in ("a@b.c.d.e.f.g.h.i.j.example.com", "ana@example.internationalconference"):
        assert redact(f"to {address}.") == "to [email]."


def test_redact_never_leaks_an_email_split_by_truncation():
    from apps.core.redaction import MAX_CHARS

    text = "x" * (MAX_CHARS - 12) + " juan.dela.cruz@example.com tail"
    result = redact(text)
    assert "juan.dela" not in result
    assert "example.com" not in result


def test_redact_drops_postgres_context_lines():
    message = 'invalid input syntax\nCONTEXT:  COPY scholars, line 3: "Juan Dela Cruz,2001-02-03"'
    assert "Juan" not in redact(message)


def test_redact_fails_closed_on_addresses_with_odd_endings():
    for address in ("juan@example.com2026", "juan@example.com-foo", "juan@localhost"):
        assert redact(f"user {address} x") == "user [email] x", address


def test_redact_masks_non_ascii_names_entirely():
    for address in ("juán.dela.cruz@example.com", "ana@exämple.ph"):
        result = redact(f"for {address} now")
        assert result == "for [email] now", address


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/accounts/claim/AbC-123_x/", "/accounts/claim/[redacted]/"),
        ("/accounts/confirm-email/MQ:1v:abc-d_e/", "/accounts/confirm-email/[redacted]/"),
        ("/accounts/password/reset/key/1a-c3x-9f2/", "/accounts/password/reset/key/[redacted]/"),
        (
            "https://host.example/accounts/claim/tok3n/?next=/me/",
            "https://host.example/accounts/claim/[redacted]/?next=/me/",
        ),
        ("Not Found: /accounts/claim/zzz/", "Not Found: /accounts/claim/[redacted]/"),
        ("GET /accounts/claim/abc/ HTTP/1.1", "GET /accounts/claim/[redacted]/ HTTP/1.1"),
        ("/accounts/claim/", "/accounts/claim/"),
        ("/accounts/password/reset/", "/accounts/password/reset/"),
        ("/accounts/password/reset/done/", "/accounts/password/reset/done/"),
        ("/me/applications/12/", "/me/applications/12/"),
    ],
)
def test_redact_secret_paths(text: str, expected: str) -> None:
    assert redact_secret_paths(text) == expected


def test_redact_includes_secret_paths() -> None:
    from apps.core.redaction import redact

    assert redact("Forbidden (CSRF token missing.): /accounts/claim/s3cret/") == (
        "Forbidden (CSRF token missing.): /accounts/claim/[redacted]/"
    )
