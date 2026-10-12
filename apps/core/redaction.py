"""One place that masks personal data in free text: log lines, exceptions, Sentry events."""

import re
import string

# PostgreSQL error trailers echo row values:
#   DETAIL:  Key (email)=(x@y.z) already exists.
#   CONTEXT:  COPY scholars, line 3: "Juan Dela Cruz,..."
# Everything from the first such trailer to the end of the message is dropped.
SERVER_TRAILER = re.compile(r"(?:DETAIL|CONTEXT):.*", re.DOTALL)
MAX_CHARS = 20_000

_LOCAL = frozenset(string.ascii_letters + string.digits + "._%+-")
_DOMAIN = frozenset(string.ascii_letters + string.digits + ".-")


def _mask_emails(text: str) -> str:
    """Replace every whole email address with "[email]".

    A hand-written scan instead of a regex: each character is visited a bounded number of times
    (left/right expansion stops at the previous match or the next "@"), so hostile input stays
    linear, and there is no length cap that could leave part of a long address unmasked.
    """
    pieces: list[str] = []
    last = 0
    at = text.find("@")
    while at != -1:
        start = at
        while start > last and text[start - 1] in _LOCAL:
            start -= 1
        end = at + 1
        while end < len(text) and text[end] in _DOMAIN:
            end += 1
        domain = text[at + 1 : end].rstrip(".-")
        end = at + 1 + len(domain)
        labels = domain.split(".")
        tld = labels[-1]
        if start < at and len(labels) >= 2 and all(labels) and tld.isascii() and tld.isalpha():
            pieces.append(text[last:start])
            pieces.append("[email]")
            last = end
            at = text.find("@", end)
        else:
            at = text.find("@", at + 1)
    pieces.append(text[last:])
    return "".join(pieces)


def redact(text: str) -> str:
    """Drop PostgreSQL DETAIL/CONTEXT trailers and mask emails, then cap the length.

    Redaction runs on the full text *before* truncating, so the cut can never split an address
    into an unrecognisable (and unmasked) fragment.
    """
    text = _mask_emails(SERVER_TRAILER.sub("DETAIL: [redacted]", text))
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + " [truncated]"
    return text
