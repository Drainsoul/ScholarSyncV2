"""One place that masks personal data in free text: log lines, exceptions, Sentry events."""

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# PostgreSQL constraint details echo the offending values:
#   DETAIL:  Key (email)=(x@y.z) already exists.
CONSTRAINT_DETAIL = re.compile(r"DETAIL:.*", re.DOTALL)


def redact(text: str) -> str:
    """Mask emails and drop PostgreSQL DETAIL lines, keeping the rest debuggable."""
    text = CONSTRAINT_DETAIL.sub("DETAIL: [redacted]", text)
    return EMAIL.sub("[email]", text)
