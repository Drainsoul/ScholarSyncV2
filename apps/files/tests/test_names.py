import pytest

from apps.files.names import clean_filename, content_disposition, download_name


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Peñafrancia – grades.PDF", "Peñafrancia – grades.PDF"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\ana\\id.png", "id.png"),
        ("bad\nname\x00.pdf", "badname.pdf"),
        ("   ", "file"),
        ("a" * 300 + ".pdf", "a" * 251 + ".pdf"),
    ],
)
def test_clean_filename(raw, clean):
    assert clean_filename(raw) == clean


def test_clean_filename_composes_to_nfc():
    assert clean_filename("Pen\u0303a.pdf") == "Peña.pdf"


def test_clean_filename_collapses_whitespace():
    assert clean_filename("  my    grades .pdf ") == "my grades .pdf"
    assert clean_filename("tab\tin.pdf") == "tabin.pdf"


def test_clean_filename_long_name_without_extension():
    assert clean_filename("b" * 300) == "b" * 255


def test_download_name_fixes_the_extension():
    assert download_name("grades", "application/pdf") == "grades.pdf"
    assert download_name("photo.JPEG", "image/jpeg") == "photo.JPEG"
    assert download_name("scan.png", "application/pdf") == "scan.png.pdf"


def test_content_disposition_has_ascii_fallback_and_utf8():
    assert content_disposition('Peña "ID".pdf') == (
        "attachment; filename=\"Pena _ID_.pdf\"; filename*=UTF-8''Pe%C3%B1a%20%22ID%22.pdf"
    )
