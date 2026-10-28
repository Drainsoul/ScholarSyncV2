"""Sample data for the design kit and mockups.

Names are Faker en_PH output (Faker.seed(2026)), never real people. Amounts and rules are
placeholders until Kenneth confirms them (spec §18, open questions 2–5).
"""

from decimal import Decimal
from typing import TypedDict

from django.urls import reverse


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


class NavItem(TypedDict):
    label: str
    url: str
    icon: str
    current: bool
    count: int


PUBLIC_NAV = [("Programs", "school", 0), ("Help", "info", 0)]
STUDENT_NAV = [
    ("Dashboard", "layout-dashboard", 0),
    ("Profile", "user", 0),
    ("Find programs", "search", 0),
    ("Applications", "file-text", 1),
    ("Scholarships", "wallet", 0),
]
STAFF_NAV = [
    ("Dashboard", "layout-dashboard", 0),
    ("Applications", "file-text", 14),
    ("Scholars", "users", 0),
    ("Terms", "calendar", 0),
    ("Disbursements", "banknote", 0),
    ("Budget", "wallet", 0),
    ("Reports", "chart-column", 0),
    ("Tasks", "list-checks", 3),
    ("Settings", "settings", 0),
]
OFFICE_NAV = [
    ("Overview", "layout-dashboard", 0),
    ("Programs", "school", 0),
    ("Staff", "shield-check", 0),
    ("Scholars", "users", 0),
    ("Reports", "file-check", 3),
    ("Analytics", "chart-column", 0),
    ("Audit log", "eye", 0),
    ("Schools", "building-2", 0),
    ("Terms", "calendar", 0),
]


def nav(items: list[tuple[str, str, int]], current: str) -> list[NavItem]:
    return [
        {"label": label, "url": "#", "icon": icon, "current": label == current, "count": count}
        for label, icon, count in items
    ]


def chrome(area: str, current: str = "") -> dict[str, object]:
    """Layout context for a sample page in one area (public, auth, student, staff, office)."""
    signed_in = {"home_url": "#", "logout_url": reverse("kit:demo-signout")}
    if area == "public":
        return {"nav_items": nav(PUBLIC_NAV, current)}
    if area == "auth":
        return {}
    if area == "student":
        return {
            **signed_in,
            "nav_items": nav(STUDENT_NAV, current or "Dashboard"),
            "viewer": {"name": "Carolyn Hawkins", "first_name": "Carolyn", "role": "Student"},
            "notifications_url": "#",
            "notifications_count": 2,
        }
    if area == "staff":
        return {
            **signed_in,
            "nav_items": nav(STAFF_NAV, current or "Dashboard"),
            "viewer": {"name": "Krista Kelley", "role": "Program staff"},
            "program": {"name": "TCU CEAA"},
            "programs": [
                {"name": "TCU CEAA", "url": "#", "current": True},
                {"name": "LANI", "url": "#", "current": False},
            ],
        }
    if area == "office":
        return {
            **signed_in,
            "nav_items": nav(OFFICE_NAV, current or "Overview"),
            "viewer": {"name": "Jessica Tate", "role": "Scholarship office"},
        }
    raise ValueError(f"unknown area {area!r}")
