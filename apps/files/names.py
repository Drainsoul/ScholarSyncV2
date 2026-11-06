"""File-name helpers: clean what users send, and name what they download."""

import os
import re
import unicodedata
from urllib.parse import quote

from .policy import EXTENSIONS

MAX_NAME = 255
_UNSAFE_ASCII = re.compile(r"[^A-Za-z0-9._ -]")


def clean_filename(name: str) -> str:
    """Keep the last path segment, in NFC, without control characters or runs of whitespace."""
    name = re.split(r"[/\\]", name)[-1]
    name = unicodedata.normalize("NFC", name)
    name = "".join(ch for ch in name if not unicodedata.category(ch).startswith("C"))
    name = " ".join(name.split())
    if len(name) > MAX_NAME:
        stem, ext = os.path.splitext(name)
        if 0 < len(ext) < MAX_NAME:
            name = stem[: MAX_NAME - len(ext)] + ext
        else:
            name = name[:MAX_NAME]
    return name or "file"


def download_name(name: str, mime: str) -> str:
    """Append the sniffed type's extension unless the name already has one of its extensions."""
    extensions = EXTENSIONS.get(mime)
    if not extensions or name.lower().endswith(extensions):
        return name
    return name + extensions[0]


def content_disposition(name: str) -> str:
    """An attachment header with an ASCII fallback and the UTF-8 name (RFC 6266)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    ascii_name = _UNSAFE_ASCII.sub("_", ascii_name) or "file"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"
