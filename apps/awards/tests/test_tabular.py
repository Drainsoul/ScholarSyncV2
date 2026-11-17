import csv
import io
import zipfile
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

import openpyxl
import pytest

from apps.awards import tabular
from apps.awards.tabular import TableError, neutralise, read_table, write_csv, write_xlsx
from apps.files.policy import CSV, XLSX

UNREADABLE = "We couldn't read this spreadsheet. Save it again as XLSX or CSV."


def xlsx(*rows: Sequence[object]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(list(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_csv_utf8_bom_header():
    body = "﻿last_name,First Name\nPeña,Ana\n".encode()
    table = read_table(body, CSV)
    assert table.columns == ["last_name", "first_name"]
    assert table.rows == [(2, {"last_name": "Peña", "first_name": "Ana"})]


def test_csv_cp1252_fallback():
    table = read_table("last_name\nPeña\n".encode("cp1252"), CSV)
    assert table.rows == [(2, {"last_name": "Peña"})]


def test_blank_rows_skipped_and_lines_kept():
    table = read_table(b"last_name\nCruz\n,\n\nReyes\n", CSV)
    assert [line for line, _ in table.rows] == [2, 5]


def test_cells_are_stripped():
    table = read_table(b"last_name\n  Cruz  \n", CSV)
    assert table.rows[0][1]["last_name"] == "Cruz"


def test_xlsx_numbers_and_dates():
    body = xlsx(["student_number", "gwa", "birth_date"], [2021001.0, 1.75, datetime(2005, 3, 14)])
    table = read_table(body, XLSX)
    assert table.rows == [
        (2, {"student_number": "2021001", "gwa": "1.75", "birth_date": date(2005, 3, 14)})
    ]


def test_xlsx_formula_without_cache_is_blank():
    table = read_table(xlsx(["last_name", "units"], ["Cruz", "=1+1"]), XLSX)
    assert table.rows == [(2, {"last_name": "Cruz", "units": ""})]


def test_too_many_rows():
    body = ("last_name\n" + "Cruz\n" * 501).encode()
    with pytest.raises(TableError) as excinfo:
        read_table(body, CSV)
    assert str(excinfo.value) == "This file has more than 500 rows. Split it into smaller files."


def test_500_rows_is_fine():
    body = ("last_name\n" + "Cruz\n" * 500).encode()
    assert len(read_table(body, CSV).rows) == 500


def test_too_many_columns():
    body = (",".join(f"c{n}" for n in range(31)) + "\n").encode()
    with pytest.raises(TableError) as excinfo:
        read_table(body, CSV)
    assert str(excinfo.value) == "This file has more than 30 columns. Use the template's columns."


def test_too_many_columns_xlsx():
    with pytest.raises(TableError) as excinfo:
        read_table(xlsx([f"c{n}" for n in range(31)]), XLSX)
    assert str(excinfo.value) == "This file has more than 30 columns. Use the template's columns."


def test_long_cell():
    body = ("last_name\n" + "x" * 201 + "\n").encode()
    with pytest.raises(TableError) as excinfo:
        read_table(body, CSV)
    assert str(excinfo.value) == "Row 2 has a value longer than 200 characters."


def test_duplicate_header():
    with pytest.raises(TableError) as excinfo:
        read_table(b"last_name,Last Name\nA,B\n", CSV)
    assert str(excinfo.value) == 'The column "last_name" appears twice.'


def test_undecodable_csv():
    with pytest.raises(TableError) as excinfo:
        read_table(b"last_name\n\x81\x8d\n", CSV)
    assert str(excinfo.value) == (
        "We couldn't read this file's text. Save it as CSV UTF-8 and try again."
    )


def test_broken_csv(monkeypatch):
    limit = csv.field_size_limit()
    csv.field_size_limit(10)
    try:
        with pytest.raises(TableError) as excinfo:
            read_table(b'last_name\n"' + b"x" * 50 + b'"\n', CSV)
    finally:
        csv.field_size_limit(limit)
    assert str(excinfo.value) == (
        "We couldn't read this CSV file. Save it again from your spreadsheet app."
    )


def test_unpacked_too_large(monkeypatch):
    monkeypatch.setattr(tabular, "MAX_UNPACKED", 10)
    with pytest.raises(TableError) as excinfo:
        read_table(xlsx(["last_name"], ["Cruz"]), XLSX)
    assert str(excinfo.value) == (
        "This spreadsheet is too large to read. Save it as CSV and try again."
    )


def test_unreadable_xlsx():
    with pytest.raises(TableError) as excinfo:
        read_table(b"PK\x03\x04garbage", XLSX)
    assert str(excinfo.value) == UNREADABLE


def test_xlsx_entity_refused():
    source = zipfile.ZipFile(io.BytesIO(xlsx(["last_name"], ["Cruz"])))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                data = data.replace(
                    b"<worksheet",
                    b'<!DOCTYPE worksheet [<!ENTITY boom "BOOM">]><worksheet',
                    1,
                )
            target.writestr(info, data)
    with pytest.raises(TableError) as excinfo:
        read_table(out.getvalue(), XLSX)
    assert str(excinfo.value) == UNREADABLE


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_neutralise(prefix):
    assert neutralise(f"{prefix}1+1") == f"'{prefix}1+1"


def test_neutralise_leaves_plain_text():
    assert neutralise("Ana") == "Ana"
    assert neutralise("") == ""


def test_write_csv_bom_and_neutralised():
    body = write_csv(["Name", "GWA"], [['=HYPERLINK("http://x","y")', Decimal("1.75")], [None, 2]])
    assert body.startswith(b"\xef\xbb\xbf")
    text = body.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows == [["Name", "GWA"], ['\'=HYPERLINK("http://x","y")', "1.75"], ["", "2"]]


def test_write_xlsx_types():
    body = write_xlsx(["A", "B"], [["=x", Decimal("1.75")]])
    sheet = openpyxl.load_workbook(io.BytesIO(body)).active
    assert sheet is not None
    assert sheet["A1"].value == "A"
    assert sheet["A1"].font.b is True
    assert sheet["A2"].data_type == "s"
    assert sheet["A2"].value == "'=x"
    assert sheet["B2"].data_type == "n"
    assert sheet["B2"].value == 1.75


def test_blank_rows_count_toward_a_hard_limit():
    body = ("last_name\nCruz\n" + ",\n" * tabular.MAX_SCANNED).encode()
    with pytest.raises(TableError) as excinfo:
        read_table(body, CSV)
    assert str(excinfo.value) == (
        "This file has too many rows, counting empty ones. Delete the empty rows and try again."
    )


def test_blank_rows_count_toward_a_hard_limit_xlsx(monkeypatch):
    monkeypatch.setattr(tabular, "MAX_SCANNED", 5)
    body = xlsx(["last_name"], ["Cruz"], *[[None, "x"] for _ in range(6)])
    with pytest.raises(TableError) as excinfo:
        read_table(body, XLSX)
    assert "too many rows, counting empty ones" in str(excinfo.value)
