import json
import logging
import sys

from apps.core.logging import JsonFormatter
from apps.core.redaction import redact
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
