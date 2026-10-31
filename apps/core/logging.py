import json
import logging
from datetime import UTC, datetime
from types import TracebackType

from apps.core.redaction import redact

type ExcInfo = (
    tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]
)


class JsonFormatter(logging.Formatter):
    """One JSON object per line for any log collector reading stdout.

    Messages and tracebacks pass through `redact()`, but never put names, emails or document
    contents into log arguments or `extra` in the first place.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

    def formatException(self, ei: ExcInfo) -> str:  # noqa: N802 (logging API name)
        return redact(super().formatException(ei))
