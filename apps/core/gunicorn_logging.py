"""The gunicorn access logger with secret URLs redacted (spec §10, M12).

The Dockerfile runs gunicorn with `--logger-class apps.core.gunicorn_logging.RedactingLogger`.
A page opened from a claim link sends the token in its Referer, so every string atom (request
line, path, query, Referer, request and response headers) is redacted, not only the path."""

import re
from datetime import timedelta
from typing import Any

from apps.core.redaction import redact_secret_paths

# A name search is personal data (ASVS V14.2.1, V16.2.5): keep that it happened, not what.
NAME_SEARCH = re.compile(r"(^|[?&])q=[^&\s]*")


def _redact(text: str) -> str:
    return NAME_SEARCH.sub(r"\1q=[redacted]", redact_secret_paths(text))


def redact_message(msg: object, args: tuple[Any, ...]) -> tuple[object, tuple[Any, ...]]:
    """An error line and its arguments with secret URLs redacted (a failing request's path
    can carry a claim token)."""
    text = _redact(msg) if isinstance(msg, str) else msg
    return text, tuple(_redact(arg) if isinstance(arg, str) else arg for arg in args)


def redact_atoms(atoms: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _redact(value) if isinstance(value, str) else value for key, value in atoms.items()
    }


try:
    from gunicorn.glogging import Logger
except ImportError:  # gunicorn needs Unix modules (grp, pwd); it only runs on Linux.
    pass
else:

    class RedactingLogger(Logger):  # type: ignore[misc]
        def atoms(
            self, resp: Any, req: Any, environ: dict[str, Any], request_time: timedelta
        ) -> dict[str, Any]:
            return redact_atoms(super().atoms(resp, req, environ, request_time))

        def error(self, msg: object, *args: Any, **kwargs: Any) -> None:
            msg, args = redact_message(msg, args)
            super().error(msg, *args, **kwargs)

        def exception(self, msg: object, *args: Any, **kwargs: Any) -> None:
            msg, args = redact_message(msg, args)
            super().exception(msg, *args, **kwargs)
