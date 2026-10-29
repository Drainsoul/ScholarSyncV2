"""Sample data for the design kit and mockups.

Names are Faker en_PH output (Faker.seed(2026)), never real people. Amounts and rules are
placeholders until Kenneth confirms them (spec §18, open questions 2–5).
"""

from decimal import Decimal
from typing import TypedDict

from django.core.paginator import Paginator
from django.urls import reverse

from apps.kit.forms import ApplyForm, DecisionForm


class Status(TypedDict):
    label: str
    tone: str


class Scholar(TypedDict):
    id: int
    name: str
    school: str
    tier: str
    amount: Decimal
    status: str
    status_label: str
    tone: str


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
    "active": {"label": "Active", "tone": "success"},
    "at_risk": {"label": "At risk", "tone": "warning"},
    "on_hold": {"label": "On hold", "tone": "neutral"},
    "ended": {"label": "Ended", "tone": "danger"},
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
            }
        )
    return rows


class NavItem(TypedDict):
    label: str
    url: str
    current: bool
    count: int


PUBLIC_NAV = [("Programs", 0), ("Help", 0)]
STUDENT_NAV = [
    ("Dashboard", 0),
    ("Profile", 0),
    ("Find programs", 0),
    ("Applications", 1),
    ("Scholarships", 0),
]
STAFF_NAV = [
    ("Dashboard", 0),
    ("Applications", 14),
    ("Scholars", 0),
    ("Terms", 0),
    ("Disbursements", 0),
    ("Budget", 0),
    ("Reports", 0),
    ("Tasks", 3),
    ("Settings", 0),
]
OFFICE_NAV = [
    ("Overview", 0),
    ("Programs", 0),
    ("Staff", 0),
    ("Scholars", 0),
    ("Reports", 3),
    ("Analytics", 0),
    ("Audit log", 0),
    ("Schools", 0),
    ("Terms", 0),
]


def nav(items: list[tuple[str, int]], current: str) -> list[NavItem]:
    return [
        {"label": label, "url": "#", "current": label == current, "count": count}
        for label, count in items
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


def student_dashboard() -> dict[str, object]:
    return {
        **chrome("student", "Dashboard"),
        "award": {"program": "TCU CEAA", "tier": "Priority", "amount": Decimal("7500.00")},
        "applications": [
            {
                "program": "TCU CEAA",
                "submitted": "12 Jun 2026",
                "label": "Approved",
                "tone": "success",
            },
            {
                "program": "LANI",
                "submitted": "2 Oct 2026",
                "label": "Returned",
                "tone": "warning",
            },
        ],
        "allowances": [
            {
                "term": "1st semester, 2026–2027",
                "amount": Decimal("7500.00"),
                "label": "Scheduled 14 Nov",
                "tone": "info",
            },
            {
                "term": "2nd semester, 2025–2026",
                "amount": Decimal("7500.00"),
                "label": "Released",
                "tone": "success",
            },
            {
                "term": "1st semester, 2025–2026",
                "amount": Decimal("5000.00"),
                "label": "Released",
                "tone": "success",
            },
        ],
        "notices": [
            {
                "text": "LANI returned your application: upload a clearer certificate of grades.",
                "when": "20 Oct",
            },
            {"text": "Your 1st semester allowance is scheduled for 14 November.", "when": "15 Oct"},
        ],
    }


def apply() -> dict[str, object]:
    return {
        **chrome("student", "Find programs"),
        "crumbs": [{"label": "Find programs", "url": "#"}, {"label": "LANI", "url": ""}],
        "documents": [
            {
                "id": "doc-grades",
                "label": "Certificate of grades",
                "help": "Your latest report card or certificate of grades.",
                "state": "done",
                "filename": "grades-2026.pdf",
            },
            {
                "id": "doc-residency",
                "label": "Proof of Taguig residency",
                "help": "Voter's certificate or barangay certificate.",
                "state": "uploading",
                "progress": 60,
                "filename": "barangay-certificate.jpg",
            },
            {
                "id": "doc-enrollment",
                "label": "Certificate of enrollment",
                "help": "For the 1st semester, 2026–2027.",
                "state": "error",
                "error": "This file is 14 MB. Upload a file of 10 MB or less.",
            },
            {
                "id": "doc-id",
                "label": "Valid ID",
                "help": "School ID or any government ID.",
                "state": "idle",
            },
        ],
        "rules": [
            {
                "text": "Taguig resident for at least 3 years",
                "state": "met",
                "icon": "circle-check",
                "status": "Met",
            },
            {
                "text": "Enrolled in a recognized school",
                "state": "met",
                "icon": "circle-check",
                "status": "Met",
            },
            {
                "text": "Family income up to ₱400,000.00 a year",
                "state": "met",
                "icon": "circle-check",
                "status": "Met",
            },
            {
                "text": "GWA of 85% or better",
                "state": "pending",
                "icon": "info",
                "status": "Checked after you upload your grades",
            },
        ],
        "form": ApplyForm(),
    }


def application_review() -> dict[str, object]:
    # A LANI application from a TCU CEAA scholar, so the "no other city scholarship" rule is unmet.
    return {
        **chrome("staff", "Applications"),
        "program": {"name": "LANI"},
        "programs": [
            {"name": "TCU CEAA", "url": "#", "current": False},
            {"name": "LANI", "url": "#", "current": True},
        ],
        "crumbs": [{"label": "Applications", "url": "#"}, {"label": "APP-2026-0147", "url": ""}],
        "tabs": [
            {"label": "Overview", "url": "#", "current": True, "count": 0},
            {"label": "Documents", "url": "#", "current": False, "count": 4},
            {"label": "Profile", "url": "#", "current": False, "count": 0},
            {"label": "History", "url": "#", "current": False, "count": 0},
        ],
        "applicant": {
            "name": "Daniel Montoya",
            "school": "Taguig City University",
            "course": "BS Information Technology, 2nd year",
            "gwa": "1.75 (88%)",
            "income": Decimal("312000.00"),
            "barangay": "Western Bicutan",
        },
        "documents": [
            {
                "label": "Certificate of grades",
                "file": "grades-2026.pdf",
                "status": "Approved",
                "tone": "success",
            },
            {
                "label": "Proof of residency",
                "file": "voters-certificate.pdf",
                "status": "Approved",
                "tone": "success",
            },
            {
                "label": "Certificate of enrollment",
                "file": "enrollment.jpg",
                "status": "Waiting",
                "tone": "info",
            },
            {
                "label": "Valid ID",
                "file": "school-id.jpg",
                "status": "Declined",
                "tone": "danger",
            },
        ],
        "rules": [
            {
                "text": "Taguig resident for at least 3 years",
                "state": "met",
                "icon": "circle-check",
                "status": "Met",
            },
            {
                "text": "Family income up to ₱400,000.00 a year",
                "state": "met",
                "icon": "circle-check",
                "status": "Met (₱312,000.00)",
            },
            {
                "text": "GWA of 85% or better",
                "state": "met",
                "icon": "circle-check",
                "status": "Met (88%)",
            },
            {
                "text": "No other city scholarship this term",
                "state": "unmet",
                "icon": "circle-alert",
                "status": "Not met: holds TCU CEAA",
            },
        ],
        "history": [
            {
                "what": "Valid ID declined",
                "when": "21 Oct 2026, 10:32 AM",
                "datetime": "2026-10-21T10:32+08:00",
                "who": "Krista Kelley",
            },
            {
                "what": "Review started",
                "when": "21 Oct 2026, 10:05 AM",
                "datetime": "2026-10-21T10:05+08:00",
                "who": "Krista Kelley",
            },
            {
                "what": "Submitted",
                "when": "2 Oct 2026, 9:14 AM",
                "datetime": "2026-10-02T09:14+08:00",
                "who": "the applicant",
            },
        ],
        "decision_form": DecisionForm(),
    }


def disbursements() -> dict[str, object]:
    statuses = [
        ("Prepared", "neutral"),
        ("Approved", "info"),
        ("Released", "success"),
    ]
    rows = [
        {
            "id": row["id"],
            "name": row["name"],
            "tier": row["tier"],
            "amount": row["amount"],
            "label": statuses[index % 3][0],
            "tone": statuses[index % 3][1],
        }
        for index, row in enumerate(scholars())
    ]
    return {
        **chrome("staff", "Disbursements"),
        "tabs": [
            {"label": "Disbursements", "url": "#", "current": True, "count": 0},
            {"label": "Schedules", "url": "#", "current": False, "count": 0},
            {"label": "Budget", "url": "#", "current": False, "count": 0},
        ],
        "budget": {
            "total": Decimal("12000000.00"),
            "released": Decimal("6480000.00"),
            "committed": Decimal("1250000.00"),
            "available": Decimal("4270000.00"),
            "used_percent": 64,
        },
        "page": Paginator(rows, 8).get_page(1),
        "total": len(rows),
    }


def office_dashboard() -> dict[str, object]:
    return {
        **chrome("office", "Overview"),
        "programs": [
            {
                "name": "TCU CEAA",
                "window": "Closed",
                "applications": 412,
                "scholars": 968,
                "used_percent": 64,
            },
            {
                "name": "LANI",
                "window": "Open until 15 Nov",
                "applications": 233,
                "scholars": 316,
                "used_percent": 41,
            },
        ],
        "months": [
            {"label": "June", "count": 182},
            {"label": "July", "count": 96},
            {"label": "August", "count": 54},
            {"label": "September", "count": 71},
            {"label": "October", "count": 242},
        ],
        "attention": [
            {"text": "3 program reports are waiting for your review", "icon": "file-check"},
            {
                "text": "LANI: 12 applications have waited more than 7 days",
                "icon": "triangle-alert",
            },
            {"text": "TCU CEAA has used 64% of its budget with 2 months left", "icon": "wallet"},
        ],
        "activity": [
            {
                "what": "Krista Kelley approved 14 disbursements (TCU CEAA)",
                "when": "Today, 9:40 AM",
                "datetime": "2026-10-28T09:40+08:00",
            },
            {
                "what": "Shannon Briggs opened LANI applications",
                "when": "Yesterday, 4:12 PM",
                "datetime": "2026-10-27T16:12+08:00",
            },
            {
                "what": "Jessica Tate added Technological University of the Philippines",
                "when": "25 Oct, 11:03 AM",
                "datetime": "2026-10-25T11:03+08:00",
            },
        ],
        "max_month": 242,
    }
