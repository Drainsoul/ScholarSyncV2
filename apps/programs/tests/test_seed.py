from django.core.management import call_command

from apps.programs.models import Program


def test_seed_creates_tcu_ceaa_and_lani(db):
    call_command("seed_programs")
    assert list(Program.objects.values_list("slug", "name")) == [
        ("lani", "LANI Scholarship Program"),
        ("tcu-ceaa", "TCU CEAA Scholarship"),
    ]


def test_seed_is_idempotent_and_keeps_edits(db):
    call_command("seed_programs")
    Program.objects.filter(slug="lani").update(description="Edited")
    call_command("seed_programs")
    assert Program.objects.count() == 2
    assert Program.objects.get(slug="lani").description == "Edited"
