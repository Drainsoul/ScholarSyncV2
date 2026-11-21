"""Import scholars from a CSV/XLSX file: the column contract, the row Form, the preview and the
all-or-nothing commit (spec §4.6, M9b)."""

import re
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.staff_forms import AcademicsForm
from apps.awards.models import Award, ScholarImport
from apps.awards.selectors import one_scholarship, pick_tier, program_profiles
from apps.awards.services import (
    FUTURE_TERM,
    NO_CURRENT_TERM,
    AwardData,
    TermData,
    already_holds,
    create_award,
)
from apps.awards.tabular import Cell, TableError, read_table, write_csv
from apps.core import audit
from apps.core.permissions import require_program_staff
from apps.files import storage
from apps.files.models import StoredFile
from apps.files.selectors import usable_file
from apps.programs.models import AcademicTerm, BenefitTier, Program, School
from apps.programs.selectors import current_term
from apps.students.models import StudentProfile
from apps.workspace.forms import MIN_BIRTH_DATE

COLUMNS: tuple[str, ...] = (
    "last_name",
    "first_name",
    "middle_name",
    "suffix",
    "birth_date",
    "student_number",
    "tier",
    "school_year",
    "term",
    "school",
    "school_type",
    "gwa_scale",
    "course",
    "year_level",
    "gwa",
    "units",
)
REQUIRED: frozenset[str] = frozenset({"last_name", "first_name", "birth_date", "tier", "school"})
TEMPLATE_CSV: bytes = write_csv(COLUMNS, [])

ALREADY_IMPORTED = "This file has already been imported."
NO_ROWS = "This file has no scholars in it."
MISSING_COLUMNS = "Add the missing columns: {columns}."
UNKNOWN_COLUMN = 'Unknown column "{column}". Use the template\'s columns.'
DUPLICATE_ROW = "This student is also on row {line}."
MANY_MATCHES = "More than one student matches this name and birth date. Add this scholar by hand."
NO_SUCH_TERM = (
    "There's no {label} in the app. Leave school year and term blank for the current term."
)
TERM_PAIR = "Fill in both school year and term, or leave both blank."
BAD_TERM = "Write the school year as 2026-2027 and the term as 1, 2 or summer."
BAD_DATE = "Write the birth date as YYYY-MM-DD, for example 2005-03-14."
TIER_CODES = "Use one of the tier codes in force for {term}: {codes}."

_TERM_WORDS = {
    "1": 1,
    "1st semester": 1,
    "first semester": 1,
    "2": 2,
    "2nd semester": 2,
    "second semester": 2,
    "3": 3,
    "summer": 3,
}
_SCHOOL_YEAR = re.compile(r"^(\d{4})(?:\s*[-–]\s*(\d{4}))?$")

Key = tuple[str, str, date]


def _fold(text: str) -> str:
    return " ".join(text.split()).casefold()


def match_key(first: str, last: str, birth_date: date) -> Key:
    return (_fold(first), _fold(last), birth_date)


def _choice_code(value: str, choices: Iterable[tuple[str, str]]) -> str:
    """A choice's value from its value or its label, case-insensitive; unknown text unchanged."""
    folded = _fold(value)
    for code, label in choices:
        if folded in (code.casefold(), _fold(label)):
            return code
    return value


@dataclass(frozen=True)
class Lookups:
    """Everything row validation needs, read once per file, so rows cost no queries."""

    program: Program
    current: AcademicTerm
    terms: dict[tuple[int, int], AcademicTerm]
    schools: dict[str, list[School]]
    tier_rows: list[BenefitTier]
    profiles: dict[Key, list[StudentProfile]]
    holders: set[int]
    # Profile id -> the refusal for an award held in another program (one at a time, §4.5).
    elsewhere: dict[int, str]

    def tier(self, code: str, term: AcademicTerm) -> BenefitTier | None:
        return pick_tier([row for row in self.tier_rows if row.code == code], term)

    def codes(self, term: AcademicTerm) -> list[str]:
        codes = sorted({row.code for row in self.tier_rows})
        return [code for code in codes if self.tier(code, term) is not None]


class _PassThrough(forms.Field):
    """A field whose value was resolved before the form ran (a listed School, or None)."""


class ImportRowForm(AcademicsForm):
    """One import row; `row_data` has already mapped the raw cells to these fields."""

    school = _PassThrough(label="School", required=False)  # type: ignore[assignment]
    last_name = forms.CharField(label="Last name", max_length=100)
    first_name = forms.CharField(label="First name", max_length=100)
    middle_name = forms.CharField(label="Middle name", max_length=100, required=False)
    suffix = forms.CharField(label="Suffix", max_length=20, required=False)
    birth_date = forms.DateField(
        label="Birth date",
        input_formats=["%Y-%m-%d", "%m/%d/%Y"],
        error_messages={"invalid": BAD_DATE},
    )
    student_number = forms.CharField(label="Student number", max_length=50, required=False)
    tier = forms.CharField(label="Tier", max_length=40)
    school_year = forms.CharField(label="School year", required=False)
    term = forms.CharField(label="Term", required=False)

    def __init__(self, *args: Any, lookups: Lookups, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.lookups = lookups

    def clean_birth_date(self) -> date:
        """The rules the staff profile form applies (apps/workspace/forms.py)."""
        born: date = self.cleaned_data["birth_date"]
        if born > timezone.localdate():
            raise ValidationError("The birth date can't be in the future.")
        if born < MIN_BIRTH_DATE:
            raise ValidationError("Enter a birth date from 1900 onward.")
        return born

    def _start_term(self, year_text: str, term_text: str) -> AcademicTerm | None:
        if not year_text and not term_text:
            return self.lookups.current
        if not year_text or not term_text:
            raise ValidationError(TERM_PAIR)
        match = _SCHOOL_YEAR.match(year_text)
        number = _TERM_WORDS.get(_fold(term_text))
        if match is None or number is None:
            raise ValidationError(BAD_TERM)
        start = int(match.group(1))
        if match.group(2) is not None and int(match.group(2)) != start + 1:
            raise ValidationError(BAD_TERM)
        term = self.lookups.terms.get((start, number))
        if term is None:
            label = str(AcademicTerm(school_year_start=start, term=number))
            raise ValidationError(NO_SUCH_TERM.format(label=label))
        if term.sort_key > self.lookups.current.sort_key:
            raise ValidationError(FUTURE_TERM)
        return term

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        try:
            term = self._start_term(
                (cleaned.get("school_year") or "").strip(), (cleaned.get("term") or "").strip()
            )
        except ValidationError as error:
            self.add_error(None, error)
            return cleaned
        cleaned["start_term"] = term
        code = (cleaned.get("tier") or "").strip()
        if code and term is not None:
            tier = self.lookups.tier(code, term)
            if tier is None:
                codes = ", ".join(self.lookups.codes(term))
                self.add_error("tier", TIER_CODES.format(term=term, codes=codes))
        return cleaned


def row_data(raw: dict[str, Cell], lookups: Lookups) -> dict[str, object]:
    """Map a row's cells to `ImportRowForm` data: names to choice codes, a school name to the
    listed school it names (exactly one, case-insensitive), else a typed name."""
    data: dict[str, object] = {column: raw.get(column, "") for column in COLUMNS}
    school_text = str(raw.get("school", "") or "")
    listed = lookups.schools.get(_fold(school_text), [])
    if len(listed) == 1:
        data["school"] = listed[0]
        data["school_name"] = ""
    else:
        data["school"] = None
        data["school_name"] = school_text
    data["school_type"] = _choice_code(str(raw.get("school_type", "")), School.Type.choices)
    data["gwa_scale"] = _choice_code(str(raw.get("gwa_scale", "")), School.Scale.choices)
    return data


@dataclass
class RowResult:
    line: int
    name: str
    birth_date: date | None
    term_label: str
    tier_code: str
    school: str
    profile: StudentProfile | None = None
    data: AwardData | None = None
    errors: list[str] = field(default_factory=list)
    # The cleaned name parts, for a new profile (first_name, middle_name, last_name, suffix).
    person: dict[str, str] = field(default_factory=dict)

    @property
    def is_new(self) -> bool:
        return self.profile is None


@dataclass
class ImportPreview:
    rows: list[RowResult]
    problem: str = ""

    @property
    def ok(self) -> bool:
        return not self.problem and bool(self.rows) and not any(row.errors for row in self.rows)

    @property
    def new_count(self) -> int:
        return sum(1 for row in self.rows if row.is_new)

    @property
    def matched_count(self) -> int:
        return sum(1 for row in self.rows if not row.is_new)


class ImportRejected(Exception):
    def __init__(self, preview: ImportPreview) -> None:
        super().__init__("The import has rows with problems.")
        self.preview = preview


def _form_errors(form: ImportRowForm) -> list[str]:
    errors: list[str] = []
    for name, messages in form.errors.items():
        for message in messages:
            if name == "__all__":
                errors.append(str(message))
            else:
                errors.append(f"{form.fields[name].label}: {message}")
    return errors


def _lookups(program: Program, current: AcademicTerm, rows: list[dict[str, Cell]]) -> Lookups:
    terms = {(t.school_year_start, t.term): t for t in AcademicTerm.objects.all()}
    schools: dict[str, list[School]] = defaultdict(list)
    for school in School.objects.all():
        schools[_fold(school.name)].append(school)
    tier_rows = list(BenefitTier.objects.filter(program=program).select_related("effective_from"))
    births = {cell for raw in rows if isinstance(cell := raw.get("birth_date"), date)}
    births |= {
        parsed
        for raw in rows
        if isinstance(text := raw.get("birth_date"), str)
        and (parsed := _parse_date(text)) is not None
    }
    profiles: dict[Key, list[StudentProfile]] = defaultdict(list)
    for profile in program_profiles(program).filter(birth_date__in=births):
        assert profile.birth_date is not None
        key = match_key(profile.first_name, profile.last_name, profile.birth_date)
        profiles[key].append(profile)
    holders: set[int] = set()
    elsewhere: dict[int, str] = {}
    held = (
        Award.objects.filter(
            status__in=Award.HELD_STATUSES,
            profile_id__in=[p.pk for found in profiles.values() for p in found],
        )
        .select_related("program")
        .order_by("started_term__sort_key", "pk")  # as held_award_elsewhere picks
    )
    for award in held:
        if award.program_id == program.pk:
            holders.add(award.profile_id)
        else:
            elsewhere.setdefault(award.profile_id, one_scholarship(award, staff=True))
    return Lookups(
        program=program,
        current=current,
        terms=terms,
        schools=dict(schools),
        tier_rows=tier_rows,
        profiles=dict(profiles),
        holders=holders,
        elsewhere=elsewhere,
    )


def _parse_date(text: str) -> date | None:
    field_ = forms.DateField(input_formats=["%Y-%m-%d", "%m/%d/%Y"])
    try:
        value = field_.clean(text.strip())
    except ValidationError:
        return None
    return value if isinstance(value, date) else None


def _validate(program: Program, rows: list[tuple[int, dict[str, Cell]]]) -> ImportPreview:
    current = current_term()
    if current is None:
        return ImportPreview(rows=[], problem=NO_CURRENT_TERM)
    lookups = _lookups(program, current, [raw for _, raw in rows])
    results: list[RowResult] = []
    seen: dict[Key, int] = {}
    for line, raw in rows:
        form = ImportRowForm(row_data(raw, lookups), lookups=lookups)
        valid = form.is_valid()
        cleaned = form.cleaned_data
        start: AcademicTerm | None = cleaned.get("start_term")
        result = RowResult(
            line=line,
            name=" ".join(
                part
                for part in (str(raw.get("first_name", "")), str(raw.get("last_name", "")))
                if part
            ),
            birth_date=cleaned.get("birth_date"),
            term_label=str(start) if start is not None else "",
            tier_code=str(raw.get("tier", "")),
            school=str(raw.get("school", "")),
            errors=_form_errors(form),
        )
        results.append(result)
        if not valid or start is None:
            continue
        key = match_key(cleaned["first_name"], cleaned["last_name"], cleaned["birth_date"])
        if key in seen:
            result.errors.append(DUPLICATE_ROW.format(line=seen[key]))
            continue
        seen[key] = line
        result.person = {
            name: " ".join((cleaned.get(name) or "").split())
            for name in ("first_name", "middle_name", "last_name", "suffix")
        }
        matches = lookups.profiles.get(key, [])
        if len(matches) > 1:
            result.errors.append(MANY_MATCHES)
            continue
        if matches:
            result.profile = matches[0]
            if result.profile.pk in lookups.holders:
                result.errors.append(already_holds(program))
                continue
            if result.profile.pk in lookups.elsewhere:
                result.errors.append(lookups.elsewhere[result.profile.pk])
                continue
        result.data = AwardData(
            tier_code=cleaned["tier"].strip(),
            student_number=(cleaned.get("student_number") or "").strip(),
            notes="",
            record=TermData(
                term=start,
                school=cleaned.get("school"),
                school_name=cleaned.get("school_name", ""),
                school_type=cleaned.get("school_type") or "",
                gwa_scale=cleaned.get("gwa_scale") or "",
                course=(cleaned.get("course") or "").strip(),
                year_level=cleaned.get("year_level"),
                gwa=cleaned.get("gwa"),
                units=cleaned.get("units"),
                compliance_checked=False,
            ),
        )
    return ImportPreview(rows=results)


def check_import(program: Program, file: StoredFile) -> ImportPreview:
    """Read and check every row of an import file. A read only: nothing is locked or written.

    Storage errors propagate (`storage.StorageUnavailable`)."""
    body = storage.read_all(file.key)
    try:
        table = read_table(body, file.sniffed_type)
    except TableError as error:
        return ImportPreview(rows=[], problem=str(error))
    unknown = [column for column in table.columns if column not in COLUMNS]
    if unknown:
        return ImportPreview(rows=[], problem=UNKNOWN_COLUMN.format(column=unknown[0]))
    missing = [c for c in COLUMNS if c in REQUIRED and c not in table.columns]
    if missing:
        return ImportPreview(rows=[], problem=MISSING_COLUMNS.format(columns=", ".join(missing)))
    if not table.rows:
        return ImportPreview(rows=[], problem=NO_ROWS)
    return _validate(program, table.rows)


@transaction.atomic
def import_scholars(
    *,
    actor: User,
    program: Program,
    file_id: uuid.UUID,
    request: HttpRequest | None = None,
) -> ScholarImport:
    """Import every row of the file, or nothing. Raises ImportRejected with the fresh preview.

    Lock order: program, then file, then matched profiles in pk order (then create_award's own
    locks). The program lock serialises every import into the program, so two files naming the
    same new person can't both create them."""
    active = Program.objects.select_for_update().filter(pk=program.pk, is_active=True).first()
    if active is None:
        raise Http404("No such program.")
    require_program_staff(actor, active)
    found = usable_file(actor, file_id, StoredFile.Purpose.IMPORT)
    if found is None:
        raise Http404("No such file.")
    file = StoredFile.objects.select_for_update().get(pk=found.pk)
    if ScholarImport.objects.filter(file=file).exists():
        raise ValidationError(ALREADY_IMPORTED)
    preview = check_import(active, file)
    if not preview.ok:
        raise ImportRejected(preview)
    matched = sorted(row.profile.pk for row in preview.rows if row.profile is not None)
    list(StudentProfile.objects.select_for_update().filter(pk__in=matched).order_by("pk"))
    try:
        with transaction.atomic():  # a savepoint, so the outer transaction survives the error
            batch = ScholarImport.objects.create(
                program=active, file=file, imported_by=actor, row_count=len(preview.rows)
            )
    except IntegrityError:
        raise ValidationError(ALREADY_IMPORTED) from None
    new_profiles = 0
    for row in preview.rows:
        assert row.data is not None and row.birth_date is not None  # preview.ok
        profile = row.profile
        if profile is None:
            profile = _create_profile(actor, active, row, request)
            new_profiles += 1
        try:
            create_award(
                actor=actor,
                program=active,
                profile_id=profile.pk,
                data=row.data,
                source=Award.Source.IMPORTED,
                batch=batch,
                request=request,
            )
        except ValidationError as error:
            row.errors.extend(error.messages)
            raise ImportRejected(preview) from None
    audit.record(
        actor=actor,
        action="scholars.imported",
        target=batch,
        program=active,
        request=request,
        data={"file": str(file.pk), "rows": len(preview.rows), "new_profiles": new_profiles},
    )
    return batch


def _create_profile(
    actor: User, program: Program, row: RowResult, request: HttpRequest | None
) -> StudentProfile:
    """An unclaimed profile for an unmatched row. No invite: staff invite from Students."""
    profile = StudentProfile.objects.create(
        first_name=row.person["first_name"],
        middle_name=row.person["middle_name"],
        last_name=row.person["last_name"],
        suffix=row.person["suffix"],
        birth_date=row.birth_date,
        created_by=actor,
        created_for=program,
    )
    audit.record(
        actor=actor,
        action="profile.imported",
        target=profile,
        program=program,
        request=request,
        data={},
    )
    return profile
