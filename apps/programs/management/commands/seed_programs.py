from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.programs.models import (
    AcademicTerm,
    BenefitTier,
    Program,
    RequiredDocument,
    School,
)
from apps.programs.seed_data import (
    MAX_BYTES,
    STARTER_DOCUMENTS,
    STARTER_PROGRAMS,
    STARTER_SCHOOLS,
)
from apps.programs.terms import school_year_terms


class Command(BaseCommand):
    help = (
        "Create the starter schools, academic terms, and the Taguig programs (TCU CEAA and "
        "LANI) with their tiers and documents, if they are missing. Never overwrites edits."
    )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        schools = self._seed_schools()
        terms = self._seed_terms()
        first_term = AcademicTerm.objects.order_by("sort_key").first()
        assert first_term is not None
        programs = tiers = documents = 0
        for entry in STARTER_PROGRAMS:
            program, was_created = Program.objects.get_or_create(
                slug=entry["slug"],
                defaults={
                    "name": entry["name"],
                    "description": entry["description"],
                    **entry["rules"],
                },
            )
            programs += was_created
            if was_created and entry["school_names"]:
                allowed = [
                    school
                    for name in entry["school_names"]
                    if (school := School.objects.filter(name__iexact=name).first())
                ]
                program.allowed_schools.set(allowed)
            for order, (code, name, base, merit) in enumerate(entry["tiers"]):
                _, tier_created = BenefitTier.objects.get_or_create(
                    program=program,
                    code=code,
                    defaults={
                        "name": name,
                        "base_amount": base,
                        "merit_amount": merit,
                        "effective_from": first_term,
                        "sort_order": order,
                    },
                )
                tiers += tier_created
            for order, (code, label, applies_to, required, types, help_text) in enumerate(
                STARTER_DOCUMENTS
            ):
                _, doc_created = RequiredDocument.objects.get_or_create(
                    program=program,
                    code=code,
                    defaults={
                        "label": label,
                        "help_text": help_text,
                        "applies_to": applies_to,
                        "is_required": required,
                        "accepted_types": types,
                        "max_bytes": MAX_BYTES,
                        "sort_order": order,
                    },
                )
                documents += doc_created
        self.stdout.write(
            f"{programs} program(s), {tiers} tier(s), {documents} document(s), "
            f"{schools} school(s), {terms} term(s) created."
        )

    def _seed_schools(self) -> int:
        created = 0
        for entry in STARTER_SCHOOLS:
            if not School.objects.filter(name__iexact=entry["name"]).exists():
                School.objects.create(**entry)
                created += 1
        return created

    def _seed_terms(self) -> int:
        if AcademicTerm.objects.exists():
            return 0
        today = timezone.localdate()
        specs = school_year_terms(today)
        for spec in specs:
            AcademicTerm.objects.create(
                school_year_start=spec.school_year_start,
                term=spec.term,
                starts_on=spec.starts_on,
                ends_on=spec.ends_on,
                is_current=spec.starts_on <= today <= spec.ends_on,
            )
        return len(specs)
