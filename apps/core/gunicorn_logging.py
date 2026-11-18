"""The gunicorn access logger with secret URLs redacted (spec §10, M12).

The Dockerfile runs gunicorn with `--logger-class apps.core.gunicorn_logging.RedactingLogger`.
A page opened from a claim link sends the token in its Referer, so every string atom (request
line, path, query, Referer, request and response headers) is redacted, not only the path."""

from datetime import timedelta
from typing import Any

from apps.core.redaction import redact_secret_paths


def redact_atoms(atoms: dict[str, Any]) -> dict[str, Any]:
    return {
        key: redact_secret_paths(value) if isinstance(value, str) else value
        for key, value in atoms.items()
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
