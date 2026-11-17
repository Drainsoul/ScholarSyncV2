"""Scholar tables as files: read a CSV/XLSX upload into rows, write rows as CSV/XLSX.

Pure file handling with no models. Every problem a staff member can fix is a `TableError` whose
text is a sentence for them.
"""

import csv
import io
import zipfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime

import openpyxl
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font

from apps.files.policy import XLSX

MAX_ROWS = 500
MAX_COLUMNS = 30
MAX_CELL = 200
MAX_UNPACKED = 50 * 1024 * 1024

TOO_MANY_ROWS = f"This file has more than {MAX_ROWS} rows. Split it into smaller files."
TOO_MANY_COLUMNS = f"This file has more than {MAX_COLUMNS} columns. Use the template's columns."
LONG_CELL = "Row {line} has a value longer than " + f"{MAX_CELL} characters."
DUPLICATE_COLUMN = 'The column "{column}" appears twice.'
UNDECODABLE = "We couldn't read this file's text. Save it as CSV UTF-8 and try again."
BROKEN_CSV = "We couldn't read this CSV file. Save it again from your spreadsheet app."
TOO_LARGE = "This spreadsheet is too large to read. Save it as CSV and try again."
UNREADABLE = "We couldn't read this spreadsheet. Save it again as XLSX or CSV."

# Spreadsheet apps run a cell starting with one of these as a formula.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

Cell = str | date


class TableError(Exception):
    pass


@dataclass(frozen=True)
class Table:
    columns: list[str]
    rows: list[tuple[int, dict[str, Cell]]]  # (line in the file, the header is line 1; values)


def _header(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _cell(value: object) -> Cell:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))  # Excel keeps every number as a float: 2021001.0 is "2021001"
    return str(value).strip()


def _table(raw_rows: Iterable[Sequence[object]]) -> Table:
    """Build the table from raw rows (the first is the header), enforcing every limit."""
    rows_iter = iter(raw_rows)
    first = next(rows_iter, None)
    if first is None:
        return Table(columns=[], rows=[])
    headers = [_header(value) for value in first]
    while headers and not headers[-1]:
        headers.pop()
    if len(headers) > MAX_COLUMNS:
        raise TableError(TOO_MANY_COLUMNS)
    seen: set[str] = set()
    for column in headers:
        if column and column in seen:
            raise TableError(DUPLICATE_COLUMN.format(column=column))
        seen.add(column)
    rows: list[tuple[int, dict[str, Cell]]] = []
    for line, raw in enumerate(rows_iter, start=2):
        values: dict[str, Cell] = {}
        for column, value in zip(headers, raw, strict=False):
            if not column:
                continue
            cell = _cell(value)
            if isinstance(cell, str) and len(cell) > MAX_CELL:
                raise TableError(LONG_CELL.format(line=line))
            values[column] = cell
        if all(value == "" for value in values.values()):
            continue
        if len(rows) == MAX_ROWS:
            raise TableError(TOO_MANY_ROWS)
        rows.append((line, values))
    return Table(columns=[column for column in headers if column], rows=rows)


def _decode(body: bytes) -> str:
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return body.decode("cp1252")  # Excel's legacy "CSV (Comma delimited)" on Windows
    except UnicodeDecodeError:
        raise TableError(UNDECODABLE) from None


def _read_csv(body: bytes) -> Table:
    reader = csv.reader(io.StringIO(_decode(body), newline=""))
    try:
        return _table(reader)
    except csv.Error:
        raise TableError(BROKEN_CSV) from None


def _xlsx_rows(body: bytes) -> Iterator[tuple[object, ...]]:
    workbook = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        yield from sheet.iter_rows(values_only=True, max_col=MAX_COLUMNS + 1)
    finally:
        workbook.close()


def _read_xlsx(body: bytes) -> Table:
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            unpacked = sum(info.file_size for info in archive.infolist())
    except (zipfile.BadZipFile, ValueError):
        raise TableError(UNREADABLE) from None
    if unpacked > MAX_UNPACKED:
        raise TableError(TOO_LARGE)
    try:
        return _table(_xlsx_rows(body))
    except TableError:
        raise
    except Exception:  # openpyxl, zipfile and defusedxml raise many types for a bad file
        raise TableError(UNREADABLE) from None


def read_table(body: bytes, content_type: str) -> Table:
    """The rows of an import file. `content_type` is the file's sniffed type (CSV or XLSX)."""
    if content_type == XLSX:
        return _read_xlsx(body)
    return _read_csv(body)


def neutralise(value: str) -> str:
    """Text a spreadsheet app won't run as a formula."""
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return neutralise(value)
    return str(value)


def write_csv(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> bytes:
    """UTF-8 with a BOM, so Excel shows ñ correctly."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([_text(header) for header in headers])
    for row in rows:
        writer.writerow([_text(value) for value in row])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def write_xlsx(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> bytes:
    """Strings are typed as text (never formulas); numbers stay numbers."""
    workbook = openpyxl.Workbook(write_only=True)
    sheet = workbook.create_sheet()
    bold = Font(bold=True)
    header_cells = []
    for header in headers:
        cell = WriteOnlyCell(sheet, value=neutralise(header))
        cell.data_type = "s"
        cell.font = bold
        header_cells.append(cell)
    sheet.append(header_cells)
    for row in rows:
        cells: list[object] = []
        for value in row:
            if isinstance(value, str):
                cell = WriteOnlyCell(sheet, value=neutralise(value))
                cell.data_type = "s"
                cells.append(cell)
            else:
                cells.append(value)
        sheet.append(cells)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
