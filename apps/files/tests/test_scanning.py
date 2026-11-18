"""Optional malware scanning with ClamAV (M13; ASVS V5.4.3)."""

import socket
import socketserver
import struct
import threading
from collections.abc import Iterator
from typing import Any

import pytest
import requests
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.files import scanning, services
from apps.files.models import StoredFile

from .conftest import pdf_bytes, png_bytes
from .test_services import objects, start, upload

pytestmark = pytest.mark.django_db

EICAR_SIGNATURE = "Eicar-Test-Signature"


class _FakeClamd(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    infected = False
    received: list[bytes]


class _Handler(socketserver.StreamRequestHandler):
    server: _FakeClamd

    def handle(self) -> None:
        command = b""
        while not command.endswith(b"\0"):
            command += self.rfile.read(1)
        assert command == b"zINSTREAM\0"
        body = b""
        while True:
            (length,) = struct.unpack("!L", self.rfile.read(4))
            if length == 0:
                break
            assert length <= scanning.CHUNK
            body += self.rfile.read(length)
        self.server.received.append(body)
        answer = f"stream: {EICAR_SIGNATURE} FOUND" if self.server.infected else "stream: OK"
        self.wfile.write(answer.encode() + b"\0")


@pytest.fixture
def clamd(settings: Any) -> Iterator[_FakeClamd]:
    server = _FakeClamd(("127.0.0.1", 0), _Handler)
    server.received = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings.CLAMAV_HOST, settings.CLAMAV_PORT = server.server_address[:2]
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def student() -> Any:
    return UserFactory.create(verified=True)


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_clean_file_becomes_ready(s3: Any, student: Any, clamd: _FakeClamd) -> None:
    body = pdf_bytes()
    intent = start(student, body)
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.READY
    assert clamd.received == [body]


def test_large_file_is_sent_in_64_kb_chunks(s3: Any, student: Any, clamd: _FakeClamd) -> None:
    body = pdf_bytes() + b"\0" * (200 * 1024)
    intent = start(student, body)
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.READY
    assert clamd.received == [body]  # the fake asserts every chunk is at most 64 KB


def test_infected_file_is_rejected_with_malware_reason(
    s3: Any, student: Any, clamd: _FakeClamd
) -> None:
    clamd.infected = True
    body = pdf_bytes()
    intent = start(student, body)
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.REJECTED
    assert file.rejected_reason == "malware"
    assert (
        services.rejection_message(file) == "This file can't be accepted. Upload a different one."
    )
    assert objects(s3) == set()
    event = AuditEvent.objects.get(action="file.rejected")
    assert event.data == {"reason": "malware"}  # never the signature


def test_clamd_down_answers_503_and_leaves_pending(
    client: Any, s3: Any, student: Any, settings: Any
) -> None:
    settings.CLAMAV_HOST, settings.CLAMAV_PORT = "127.0.0.1", _closed_port()
    client.force_login(student)
    body = pdf_bytes()
    intent = client.post(
        reverse("files:upload-intent"),
        {"purpose": "document", "name": "grades.pdf", "type": "application/pdf", "size": len(body)},
        content_type="application/json",
    ).json()
    requests.put(intent["url"], data=body, headers=intent["headers"], timeout=10).raise_for_status()
    response = client.post(intent["confirm_url"])
    assert response.status_code == 503
    assert response.json() == {
        "error": "Files can't be checked right now. Try again in a few minutes."
    }
    file = StoredFile.objects.get(pk=intent["id"])
    assert file.status == StoredFile.Status.PENDING
    assert not AuditEvent.objects.filter(action__in=["file.uploaded", "file.rejected"]).exists()


def test_clamd_back_up_lets_the_same_upload_finish(
    s3: Any, student: Any, clamd: _FakeClamd, settings: Any
) -> None:
    body = pdf_bytes()
    intent = start(student, body)
    upload(intent, body)
    port = settings.CLAMAV_PORT
    settings.CLAMAV_PORT = _closed_port()
    with pytest.raises(scanning.ScannerUnavailable):
        services.confirm_upload(user=student, file_id=intent.file.id)
    settings.CLAMAV_PORT = port
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.READY
    assert clamd.received == [body]


def test_clamd_error_answer_fails_closed(settings: Any) -> None:
    class Erroring(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            self.rfile.read(len(b"zINSTREAM\0") + 4)
            self.wfile.write(b"INSTREAM size limit exceeded. ERROR\0")

    server = socketserver.TCPServer(("127.0.0.1", 0), Erroring)
    threading.Thread(target=server.handle_request, daemon=True).start()
    settings.CLAMAV_HOST, settings.CLAMAV_PORT = server.server_address[:2]
    try:
        with pytest.raises(scanning.ScannerUnavailable):
            scanning.scan([b""])
    finally:
        server.server_close()


def test_unset_skips_scanning(s3: Any, student: Any, settings: Any, monkeypatch: Any) -> None:
    settings.CLAMAV_HOST = ""

    def never(chunks: Any) -> None:
        raise AssertionError("scanned without a host")

    monkeypatch.setattr(scanning, "scan", never)
    body = pdf_bytes()
    intent = start(student, body)
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.READY


def test_photos_are_scanned_before_reencoding(s3: Any, student: Any, clamd: _FakeClamd) -> None:
    body = png_bytes()
    intent = start(student, body, purpose="photo", content_type="image/png")
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.status == StoredFile.Status.READY
    assert clamd.received == [body]  # the bytes as sent, not the re-encoded copy


def test_infected_photo_is_rejected_and_removed(s3: Any, student: Any, clamd: _FakeClamd) -> None:
    clamd.infected = True
    body = png_bytes()
    intent = start(student, body, purpose="photo", content_type="image/png")
    upload(intent, body)
    file = services.confirm_upload(user=student, file_id=intent.file.id)
    assert file.rejected_reason == "malware"
    assert objects(s3) == set()
