from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from zoneinfo import ZoneInfo

import time_machine
from django.core.management import call_command

from apps.files.policy import MB
from apps.programs.models import AcademicTerm, BenefitTier, Program, School
from apps.programs.selectors import current_term, required_documents_for, tiers_in_force


def test_seed_creates_tcu_ceaa_and_lani(db):
    call_command("seed_programs")
    assert list(Program.objects.values_list("slug", "name")) == [
        ("lani", "LANI Scholarship Program"),
        ("tcu-ceaa", "TCU CEAA Scholarship"),
    ]


def test_seed_keeps_edited_description(db):
    call_command("seed_programs")
    Program.objects.filter(slug="lani").update(description="Edited")
    call_command("seed_programs")
    assert Program.objects.count() == 2
    assert Program.objects.get(slug="lani").description == "Edited"


@time_machine.travel(datetime(2026, 11, 8, 10, tzinfo=ZoneInfo("Asia/Manila")))
def test_seed_creates_terms_tiers_documents(db):
    call_command("seed_programs")
    term = current_term()
    assert term is not None
    assert str(term) == "1st semester, SY 2026–2027"
    lani = Program.objects.get(slug="lani")
    assert [t.code for t in tiers_in_force(lani, term)] == [
        "honors",
        "premier",
        "priority",
        "basic-plus",
        "basic",
        "suc-lcu",
        "review",
        "lead",
    ]
    assert lani.required_documents.count() == 14
    assert list(
        Program.objects.get(slug="tcu-ceaa").allowed_schools.values_list("name", flat=True)
    ) == ["Taguig City University"]


def test_seed_sets_rules_and_documents(db):
    call_command("seed_programs")
    ceaa = Program.objects.get(slug="tcu-ceaa")
    assert (ceaa.min_gwa_percent, ceaa.renewal_min_gwa_percent, ceaa.renewal_min_units) == (
        Decimal("80"),
        Decimal("80"),
        15,
    )
    lani = Program.objects.get(slug="lani")
    assert lani.renewal_max_gwa_one_to_five == Decimal("2.50")
    assert lani.renewal_no_failing_grades is True
    assert lani.allowed_schools.count() == 0
    assert [d.code for d in required_documents_for(lani, "new")] == [
        "photo-2x2",
        "jhs-certificate",
        "shs-diploma",
        "valid-id",
        "birth-certificate",
        "voters-certification",
        "form-137",
        "als-certificate",
        "parent-death-certificate",
        "ofw-parent-documents",
    ]
    photo = lani.required_documents.get(code="photo-2x2")
    assert photo.accepted_types == ["image/jpeg", "image/png"]
    assert photo.max_bytes == 10 * MB
    assert School.objects.get(name="Taguig City University").is_in_taguig


def test_seed_prints_counts(db):
    out = StringIO()
    call_command("seed_programs", stdout=out)
    assert out.getvalue().strip() == (
        "2 program(s), 9 tier(s), 28 document(s), 3 school(s), 3 term(s) created."
    )
    out = StringIO()
    call_command("seed_programs", stdout=out)
    assert out.getvalue().strip() == (
        "0 program(s), 0 tier(s), 0 document(s), 0 school(s), 0 term(s) created."
    )


def test_seed_keeps_edited_rules_and_tiers(db):
    call_command("seed_programs")
    Program.objects.filter(slug="lani").update(min_gwa_percent=Decimal("85.00"))
    BenefitTier.objects.filter(code="lead").update(base_amount=Decimal("1.00"))
    call_command("seed_programs")
    assert Program.objects.get(slug="lani").min_gwa_percent == Decimal("85.00")
    assert BenefitTier.objects.get(code="lead").base_amount == Decimal("1.00")
    assert BenefitTier.objects.count() == 9
    assert AcademicTerm.objects.count() == 3


def test_seed_matches_school_names_case_insensitively(db):
    School.objects.create(
        name="university of the philippines",
        type=School.Type.SUC,
        grading_scale=School.Scale.ONE_TO_FIVE,
    )
    call_command("seed_programs")
    assert School.objects.count() == 3


def test_seed_leaves_existing_terms_alone(db):
    term = AcademicTerm.objects.create(
        school_year_start=2020,
        term=1,
        starts_on=date(2020, 8, 1),
        ends_on=date(2020, 12, 31),
        is_current=True,
    )
    call_command("seed_programs")
    assert AcademicTerm.objects.count() == 1
    assert {t.effective_from_id for t in BenefitTier.objects.all()} == {term.pk}


def test_seed_allowed_school_uses_existing_row_with_different_case(db):
    existing = School.objects.create(
        name="taguig city university",
        type=School.Type.LCU,
        grading_scale=School.Scale.PERCENT,
        is_in_taguig=True,
    )
    call_command("seed_programs")
    ceaa = Program.objects.get(slug="tcu-ceaa")
    assert list(ceaa.allowed_schools.all()) == [existing]
