"""One place that masks personal data in free text: log lines, exceptions, Sentry events."""

import re

# Bounded repeats and dot-free domain labels keep matching linear on hostile input (no ReDoS).
EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@(?:[A-Za-z0-9-]{1,63}\.){1,8}[A-Za-z]{2,24}")
# PostgreSQL constraint details echo the offending values:
#   DETAIL:  Key (email)=(x@y.z) already exists.
CONSTRAINT_DETAIL = re.compile(r"DETAIL:.*", re.DOTALL)
MAX_CHARS = 20_000


def redact(text: str) -> str:
    """Mask emails and drop PostgreSQL DETAIL lines, keeping the rest debuggable."""
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + " [truncated]"
    text = CONSTRAINT_DETAIL.sub("DETAIL: [redacted]", text)
    return EMAIL.sub("[email]", text)
