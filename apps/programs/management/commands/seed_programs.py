from typing import Any

from django.core.management.base import BaseCommand

from apps.programs.models import Program

STARTER_PROGRAMS = [
    {
        "slug": "tcu-ceaa",
        "name": "TCU CEAA Scholarship",
        "description": (
            "The Taguig City University City Educational Assistance Allowance "
            "gives scholars an allowance each semester."
        ),
    },
    {
        "slug": "lani",
        "name": "LANI Scholarship Program",
        "description": (
            "Lifeline Assistance for Neighbors In-need is a City of Taguig "
            "scholarship that pays scholars an allowance each semester."
        ),
    },
]


class Command(BaseCommand):
    help = "Create the Taguig starter programs (TCU CEAA and LANI) if they are missing."

    def handle(self, *args: Any, **options: Any) -> None:
        created = 0
        for entry in STARTER_PROGRAMS:
            _, was_created = Program.objects.get_or_create(
                slug=entry["slug"],
                defaults={"name": entry["name"], "description": entry["description"]},
            )
            created += was_created
        self.stdout.write(
            f"{created} program(s) created, {len(STARTER_PROGRAMS) - created} already present."
        )
