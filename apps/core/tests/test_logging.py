import json
import logging

from apps.core.logging import JsonFormatter


def make_record(msg: str, exc_info=None) -> logging.LogRecord:
    return logging.LogRecord("apps.test", logging.WARNING, __file__, 1, msg, None, exc_info)


def test_json_formatter_emits_one_json_object():
    line = JsonFormatter().format(make_record("disk almost full"))
    payload = json.loads(line)
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "apps.test"
    assert payload["msg"] == "disk almost full"
    assert "ts" in payload and "\n" not in line


def test_json_formatter_includes_exception_text():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        line = JsonFormatter().format(make_record("failed", sys.exc_info()))
    assert "ValueError: boom" in json.loads(line)["exc"]
