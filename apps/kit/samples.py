"""Sample data for the design kit and mockups.

Names are Faker en_PH output (Faker.seed(2026)), never real people. Amounts and rules are
placeholders until Kenneth confirms them (spec §18, open questions 2–5).
"""

from decimal import Decimal
from typing import TypedDict


class Status(TypedDict):
    label: str
    tone: str
    icon: str


class Scholar(TypedDict):
    id: int
    name: str
    school: str
    tier: str
    amount: Decimal
    status: str
    status_label: str
    tone: str
    icon: str


NAMES = [
    "David Shaw", "William Heath", "Curtis Walker", "Carolyn Hawkins", "Krista Kelley",
    "Jessica Tate", "Karen Willis", "John Mendez", "Daniel Montoya", "Shannon Briggs",
    "Gina Shelton", "Jason King",
]  # fmt: skip
SCHOOLS = [
    "Taguig City University",
    "University of Makati",
    "Polytechnic University of the Philippines",
    "Technological University of the Philippines",
]
TIERS = [
    ("Basic", Decimal("5000.00")),
    ("Priority", Decimal("7500.00")),
    ("Honors", Decimal("10000.00")),
]
STATUSES: dict[str, Status] = {
    "active": {"label": "Active", "tone": "success", "icon": "circle-check"},
    "at_risk": {"label": "At risk", "tone": "warning", "icon": "triangle-alert"},
    "on_hold": {"label": "On hold", "tone": "neutral", "icon": "info"},
    "ended": {"label": "Ended", "tone": "danger", "icon": "circle-alert"},
}
_SCHOLAR_STATUSES = [
    "active", "active", "at_risk", "active", "on_hold", "active",
    "ended", "active", "at_risk", "active", "active", "on_hold",
]  # fmt: skip


def scholars() -> list[Scholar]:
    rows: list[Scholar] = []
    for index, (name, status) in enumerate(zip(NAMES, _SCHOLAR_STATUSES, strict=True)):
        tier, amount = TIERS[index % len(TIERS)]
        info = STATUSES[status]
        rows.append(
            {
                "id": index + 1,
                "name": name,
                "school": SCHOOLS[index % len(SCHOOLS)],
                "tier": tier,
                "amount": amount,
                "status": status,
                "status_label": info["label"],
                "tone": info["tone"],
                "icon": info["icon"],
            }
        )
    return rows
