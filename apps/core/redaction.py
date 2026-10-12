"""One place that masks personal data in free text: log lines, exceptions, Sentry events."""

import re

# PostgreSQL error trailers echo row values:
#   DETAIL:  Key (email)=(x@y.z) already exists.
#   CONTEXT:  COPY scholars, line 3: "Juan Dela Cruz,..."
# Everything from the first such trailer to the end of the message is dropped.
SERVER_TRAILER = re.compile(r"(?:DETAIL|CONTEXT):.*", re.DOTALL)
MAX_CHARS = 20_000

_LOCAL_PUNCTUATION = frozenset("._%+-")
_DOMAIN_PUNCTUATION = frozenset(".-")


def _is_local(char: str) -> bool:
    return char.isalnum() or char in _LOCAL_PUNCTUATION  # isalnum: any script, so "juán" is whole


def _is_domain(char: str) -> bool:
    return char.isalnum() or char in _DOMAIN_PUNCTUATION


def _mask_emails(text: str) -> str:
    """Replace every `something@something` run with "[email]". Fails closed.

    Anything with at least one local character before the "@" and one domain character after it
    is masked whole, so odd endings ("x@gmail.com2026"), local hosts and non-ASCII names never slip
    through a stricter validity check. Over-masking a log line is the accepted cost.

    A hand-written scan instead of a regex: left/right expansion stops at the previous match or
    the next "@", so each character is visited a bounded number of times and hostile input stays
    linear, with no length cap that could leave part of a long address unmasked.
    """
    pieces: list[str] = []
    last = 0
    at = text.find("@")
    while at != -1:
        start = at
        while start > last and _is_local(text[start - 1]):
            start -= 1
        end = at + 1
        while end < len(text) and _is_domain(text[end]):
            end += 1
        while end > at + 1 and text[end - 1] in _DOMAIN_PUNCTUATION:
            end -= 1  # sentence punctuation after an address ("… juan@x.com.") stays outside
        if start < at and end > at + 1:
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
