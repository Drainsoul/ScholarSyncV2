"""The demo's sample PDF must open in a PDF viewer: a page tree and a correct xref table."""

import re

from apps.demo.samples import SAMPLE_PDF


def test_sample_pdf_has_a_page() -> None:
    assert SAMPLE_PDF.startswith(b"%PDF-1.4\n")
    assert SAMPLE_PDF.endswith(b"%%EOF\n")
    assert b"/Type /Pages /Kids [3 0 R] /Count 1" in SAMPLE_PDF
    assert b"/Type /Page " in SAMPLE_PDF


def test_sample_pdf_xref_points_at_each_object() -> None:
    startxref = int(re.search(rb"startxref\n(\d+)\n", SAMPLE_PDF).group(1))  # type: ignore[union-attr]
    assert SAMPLE_PDF[startxref:].startswith(b"xref\n0 6\n")
    offsets = re.findall(rb"(\d{10}) 00000 n \n", SAMPLE_PDF)
    assert len(offsets) == 5
    for number, offset in enumerate(offsets, start=1):
        assert SAMPLE_PDF[int(offset) :].startswith(f"{number} 0 obj\n".encode())


def test_sample_pdf_stream_length_is_exact() -> None:
    length = int(re.search(rb"/Length (\d+) >>\nstream\n", SAMPLE_PDF).group(1))  # type: ignore[union-attr]
    start = SAMPLE_PDF.index(b"stream\n") + len(b"stream\n")
    assert SAMPLE_PDF[start + length :].startswith(b"\nendstream")
