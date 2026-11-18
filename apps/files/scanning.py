"""Optional malware scanning with ClamAV (spec §10, M13; ASVS V5.4.3).

With `CLAMAV_HOST` set, upload confirm streams each file to clamd (`zINSTREAM`) before it is
marked ready. Unset, nothing is scanned. A clamd that can't be reached or answers with an error
fails closed: `ScannerUnavailable`, and the file stays pending.
"""

import socket
import struct
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from django.conf import settings

CHUNK = 64 * 1024
TIMEOUT = 30.0


class ScannerUnavailable(Exception):
    """clamd can't be reached or didn't give a verdict."""


@dataclass(frozen=True)
class ScanResult:
    infected: bool
    signature: str = ""


def enabled() -> bool:
    return bool(settings.CLAMAV_HOST)


def _pieces(chunks: Iterable[bytes]) -> Iterator[bytes]:
    for chunk in chunks:
        for start in range(0, len(chunk), CHUNK):
            yield chunk[start : start + CHUNK]


def scan(chunks: Iterable[bytes]) -> ScanResult:
    """Stream `chunks` to clamd and return its verdict."""
    try:
        with socket.create_connection(
            (settings.CLAMAV_HOST, settings.CLAMAV_PORT), timeout=TIMEOUT
        ) as conn:
            conn.sendall(b"zINSTREAM\0")
            for piece in _pieces(chunks):
                if piece:
                    conn.sendall(struct.pack("!L", len(piece)) + piece)
            conn.sendall(struct.pack("!L", 0))
            reply = b""
            while not reply.endswith(b"\0"):
                data = conn.recv(4096)
                if not data:
                    break
                reply += data
    except OSError as exc:
        raise ScannerUnavailable(str(exc)) from exc
    answer = reply.rstrip(b"\0").decode("utf-8", "replace").strip()
    # "stream: OK", "stream: <signature> FOUND", or "<message> ERROR" (e.g. the size limit).
    if answer.endswith(" FOUND"):
        signature = answer.removeprefix("stream:").removesuffix(" FOUND").strip()
        return ScanResult(infected=True, signature=signature)
    if answer.endswith("OK"):
        return ScanResult(infected=False)
    raise ScannerUnavailable(answer or "no answer")
