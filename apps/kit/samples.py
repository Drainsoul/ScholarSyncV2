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
    tone: str  # a tag modifier (success, warning, danger, info); "" renders a plain grey tag


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
    "on_hold": {"label": "On hold", "tone": ""},
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
    icon: str


PUBLIC_NAV = [("Programs", "", 0), ("Help", "", 0)]
STUDENT_NAV = [
    ("Home", "house", 0),
    ("Find programs", "search", 0),
    ("Applications", "file-text", 1),
    ("Allowances", "banknote", 0),
    ("Profile", "user", 0),
]
STAFF_NAV = [
    ("Dashboard", "layout-dashboard", 0),
    ("Applications", "file-text", 14),
    ("Scholars", "users", 0),
    ("Disbursements", "banknote", 0),
    ("Terms", "calendar", 0),
    ("Reports", "chart-column", 0),
    ("Tasks", "list-checks", 3),
]
OFFICE_NAV = [
    ("Overview", "layout-dashboard", 0),
    ("Programs", "clipboard-check", 0),
    ("Staff", "user", 0),
    ("Scholars", "users", 0),
    ("Schools", "building-2", 0),
    ("Terms", "calendar", 0),
    ("Reports", "file-text", 3),
    ("Analytics", "chart-column", 0),
    ("Audit log", "shield", 0),
]
HELP_NAV = [("Help and guides", "circle-help", 0)]
STAFF_SUPPORT_NAV = [("Settings", "sliders-horizontal", 0), *HELP_NAV]


def nav(items: list[tuple[str, str, int]], current: str) -> list[NavItem]:
    return [
        {"label": label, "url": "#", "current": label == current, "count": count, "icon": icon}
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
            "nav_heading": "Scholarships",
            "nav_items": nav(STUDENT_NAV, current or "Home"),
            "nav_secondary": nav(HELP_NAV, current),
            "viewer": {"name": "Carolyn Hawkins", "first_name": "Carolyn", "role": "Student"},
            "notifications_url": "#",
            "notifications_count": 2,
        }
    if area == "staff":
        return {
            **signed_in,
            "nav_items": nav(STAFF_NAV, current or "Dashboard"),
            "nav_secondary": nav(STAFF_SUPPORT_NAV, current),
            "viewer": {"name": "Krista Kelley", "role": "Program staff"},
            "program": {"name": "TCU CEAA"},
            "programs": [
                {"name": "TCU CEAA", "url": "#", "current": True},
                {"name": "LANI", "url": "#", "current": False},
            ],
            "search_url": "#",
            "terms": [
                {"name": "1st sem 2026–2027", "url": "#", "current": True},
                {"name": "2nd sem 2025–2026", "url": "#", "current": False},
                {"name": "1st sem 2025–2026", "url": "#", "current": False},
            ],
            "notifications_url": "#",
            "notifications_count": 3,
        }
    if area == "office":
        return {
            **signed_in,
            "nav_heading": "City-wide",
            "nav_items": nav(OFFICE_NAV, current or "Overview"),
            "viewer": {"name": "Jessica Tate", "role": "Scholarship office"},
            "search_url": "#",
            "notifications_url": "#",
            "notifications_count": 2,
        }
    raise ValueError(f"unknown area {area!r}")


def student_dashboard() -> dict[str, object]:
    return {
        **chrome("student", "Home"),
        "award": {"program": "TCU CEAA", "tier": "Priority", "amount": Decimal("7500.00")},
        "profile_percent": 85,
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
                "label": "Scheduled",
                "tone": "warning",
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
        "checks": {"passed": 5, "total": 8, "percent": 63},
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
        ("Prepared", ""),
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


# Scholars page (canvas: Main.dc.html). Per scholar id: course and year, barangay, scholar since
# and GWA (%).
_SCHOLAR_DETAILS: dict[int, tuple[str, str, str, int]] = {
    1: ("BS Accountancy, 3rd year", "Ususan", "2024", 88),
    2: ("BS Civil Engineering, 4th year", "Fort Bonifacio", "2023", 91),
    3: ("BS Nursing, 2nd year", "Hagonoy", "2025", 79),
    4: ("BS Electrical Engineering, 1st year", "Signal Village", "2026", 85),
    5: ("BA Communication, 3rd year", "Tuktukan", "2024", 84),
    6: ("BS Social Work, 2nd year", "Bagumbayan", "2025", 87),
    7: ("BS Psychology, 4th year", "Napindan", "2022", 74),
    8: ("BS Computer Science, 2nd year", "Upper Bicutan", "2025", 93),
    9: ("BS Information Technology, 2nd year", "Western Bicutan", "2025", 78),
    10: ("BS Architecture, 3rd year", "Pinagsama", "2024", 86),
    11: ("BS Education, 1st year", "Tipas", "2026", 90),
    12: ("BS Biology, 3rd year", "Lower Bicutan", "2024", 83),
    13: ("BS Industrial Engineering, 2nd year", "North Signal Village", "2025", 89),
}
# A long Faker name (first, first, last, last-last), so layouts are checked against one.
LONG_NAME = "Kimberly Catherine Pena Gilbert-Middleton"
SCHOLAR_TABS = [
    ("all", "All", 968),
    ("active", "Active", 900),
    ("at_risk", "At risk", 37),
    ("on_hold", "On hold", 12),
    ("ended", "Ended", 19),
]
RENEWAL_MARK = 80


def _scholar_rows() -> list[dict[str, object]]:
    """scholars() plus one long name, with the fields the Scholars page shows, sorted by name."""
    base: list[Scholar] = [
        *scholars(),
        {
            "id": 13,
            "name": LONG_NAME,
            "school": SCHOOLS[0],
            "tier": "Priority",
            "amount": Decimal("7500.00"),
            "status": "active",
            "status_label": STATUSES["active"]["label"],
            "tone": STATUSES["active"]["tone"],
        },
    ]
    rows: list[dict[str, object]] = []
    for row in base:
        course, barangay, since, gwa = _SCHOLAR_DETAILS[row["id"]]
        words = row["name"].split()
        rows.append(
            {
                **row,
                "tone": row["tone"] or "neutral",
                "email": f"{words[0][0]}.{words[-1]}@example.com".lower(),
                "course": course,
                "barangay": barangay,
                "since": since,
                "gwa": gwa,
                "gwa_low": gwa < RENEWAL_MARK,
                "avatar_index": row["id"] - 1,
            }
        )
    return sorted(rows, key=lambda row: str(row["name"]))


def _drawer(row: dict[str, object]) -> dict[str, object]:
    amount = row["amount"]
    note = (
        f"Below the {RENEWAL_MARK}% renewal mark. Staff are asked to check in before 15 Nov."
        if row["gwa_low"]
        else f"Meets the {RENEWAL_MARK}% renewal mark with at least 15 units."
    )
    return {
        **row,
        "gwa_note": note,
        "allowances": [
            {
                "term": "1st sem 2026–2027",
                "when": "Release on 14 Nov",
                "amount": amount,
                "label": "Scheduled",
                "tone": "warning",
            },
            {
                "term": "2nd sem 2025–2026",
                "when": "Released 3 Apr",
                "amount": amount,
                "label": "Released",
                "tone": "success",
            },
            {
                "term": "1st sem 2025–2026",
                "when": "Released 7 Nov",
                "amount": amount,
                "label": "Released",
                "tone": "success",
            },
        ],
    }


def scholars_page(status: str, scholar: int | None, page: str | None = None) -> dict[str, object]:
    """The Scholars list for one status tab (unknown: all), with the drawer for a known id."""
    counts = {key: count for key, _, count in SCHOLAR_TABS}
    if status not in counts:
        status = "all"
    everyone = _scholar_rows()
    rows = everyone if status == "all" else [row for row in everyone if row["status"] == status]
    rows = rows[:10]
    selected = next((row for row in everyone if row["id"] == scholar), None)
    return {
        **chrome("staff", "Scholars"),
        "crumbs": [{"label": "TCU CEAA", "url": "#"}, {"label": "Scholars", "url": ""}],
        "status": status,
        "figures": [
            {"label": "Active scholars", "value": "900"},
            {"label": "At risk", "value": "37"},
            {"label": "On hold", "value": "12"},
            {"label": "Budget used", "value": "64%"},
        ],
        "tabs": [
            {"label": label, "url": f"?status={key}", "current": key == status, "count": count}
            for key, label, count in SCHOLAR_TABS
        ],
        "schools": SCHOOLS,
        "tiers": [tier for tier, _ in TIERS],
        "rows": rows,
        "shown": len(rows),
        "total": counts[status],
        # The sample has one page of rows; the pager shows the real page count (10 a page).
        "page": Paginator(range(counts[status]), 10).get_page(page),
        "selected_id": scholar if selected else None,
        # Closing goes back to the same tab, at the scholar's row.
        "drawer": {**_drawer(selected), "close_url": f"?status={status}#scholar-{scholar}"}
        if selected
        else None,
    }


def _month_bars(counts: list[tuple[str, int]], peak: int) -> list[dict[str, object]]:
    """Chart months: bar height is the share of the peak, in the 5 % steps the CSS maps."""
    return [
        {
            "label": label,
            "short": label[:3],
            "count": count,
            "percent": min(100, round(count / peak * 20) * 5),
            "current": index == len(counts) - 1,
        }
        for index, (label, count) in enumerate(counts)
    ]


def office_dashboard() -> dict[str, object]:
    return {
        **chrome("office", "Overview"),
        "greeting": "Good morning, Jessica",
        "figures": [
            {"label": "Scholars", "value": "1,284"},
            {"label": "Applications", "value": "645"},
            {"label": "Waiting over 7 days", "value": "12"},
            {"label": "Reports to review", "value": "3"},
        ],
        "programs": [
            {
                "name": "TCU CEAA",
                "window": "Applications closed",
                "applications": 412,
                "scholars": 968,
                "used_percent": 64,
                "initials_index": 0,
            },
            {
                "name": "LANI",
                "window": "Open until 15 November",
                "applications": 233,
                "scholars": 316,
                "used_percent": 41,
                "initials_index": 2,
            },
        ],
        "months": _month_bars(
            [("June", 182), ("July", 96), ("August", 54), ("September", 71), ("October", 242)],
            250,
        ),
        "attention": [
            {
                "title": "3 program reports are waiting for your review",
                "detail": "Oldest sent 4 days ago",
                "tone": "warning",
                "url": "#",
            },
            {
                "title": "12 LANI applications have waited more than 7 days",
                "detail": "Overdue: window closes 15 November",
                "tone": "danger",
                "url": "#",
            },
            {
                "title": "TCU CEAA has used 64% of its budget",
                "detail": "2 months left in the school year",
                "tone": "warning",
                "url": "#",
            },
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
    }
