"""Builders for scholar tests: an award with its term records, written straight to the database."""

from decimal import Decimal
from typing import Any

from apps.awards.models import Award, ScholarTerm
from apps.awards.tests.factories import AwardFactory, ScholarTermFactory
from apps.programs.models import AcademicTerm, BenefitTier, Program
from apps.students.models import StudentProfile
from apps.students.tests.factories import FullProfileFactory


def make_scholar(
    program: Program,
    tier: BenefitTier,
    terms: list[AcademicTerm],
    *,
    profile: StudentProfile | None = None,
    status: str = Award.Status.ACTIVE,
    gwa: Decimal | None = Decimal("88.00"),
    gwa_scale: str = "percent",
    units: int | None = 18,
    **award_fields: Any,
) -> Award:
    """A manual award started in the first of `terms`, with one term record per term."""
    award = AwardFactory.create(
        profile=profile or FullProfileFactory.create(),
        program=program,
        tier=tier,
        started_term=terms[0],
        source=Award.Source.MANUAL,
        source_application=None,
        status=status,
        **award_fields,
    )
    for term in terms:
        add_record(award, term, gwa=gwa, gwa_scale=gwa_scale, units=units)
    return award


def add_record(award: Award, term: AcademicTerm, **fields: Any) -> ScholarTerm:
    values: dict[str, Any] = {
        "award": award,
        "term": term,
        "tier": award.tier,
        "school_name": "Factory College",
        "school_type": "private",
        "gwa": Decimal("88.00"),
        "gwa_scale": "percent",
        "units": 18,
        "year_level": 2,
    }
    values.update(fields)
    return ScholarTermFactory.create(**values)
