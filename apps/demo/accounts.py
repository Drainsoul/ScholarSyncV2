"""The demo's test accounts (spec §11 rev 36). Explore mode only; they share one published password.

`ACCOUNTS` are the role accounts `load()` creates. `SAMPLE_LOGINS` are listed on the login page too,
but a sample step creates them with their data (an application, an award), so `load()` never does.
"""

from dataclasses import dataclass

from apps.accounts.models import User
from apps.programs.models import ProgramMembership

PASSWORD = "explore-demo-2026"  # noqa: S105 (public by design, shown on the login page)

STUDENTS = "Students"
STAFF = "Program staff"
OFFICE = "Scholarship office"
GROUPS = (STUDENTS, STAFF, OFFICE)


@dataclass(frozen=True)
class DemoAccount:
    button: str  # reads alone: the fill status says "Filled in the {button} account."
    email: str
    full_name: str
    role: User.Role
    group: str
    program: str | None = None
    level: ProgramMembership.Level | None = None


ACCOUNTS: list[DemoAccount] = [
    DemoAccount("New student", "new@scholarsync.test", "Bea Navarro", User.Role.STUDENT, STUDENTS),
    DemoAccount(
        "Applicant", "student@scholarsync.test", "Carolyn Hawkins", User.Role.STUDENT, STUDENTS
    ),
    DemoAccount(
        "CEAA staff",
        "staff@scholarsync.test",
        "Krista Kelley",
        User.Role.STAFF,
        STAFF,
        "tcu-ceaa",
        ProgramMembership.Level.STAFF,
    ),
    DemoAccount(
        "CEAA head",
        "head@scholarsync.test",
        "Shannon Briggs",
        User.Role.STAFF,
        STAFF,
        "tcu-ceaa",
        ProgramMembership.Level.HEAD,
    ),
    DemoAccount(
        "LANI staff",
        "lani.staff@scholarsync.test",
        "Ronaldo Pascual",
        User.Role.STAFF,
        STAFF,
        "lani",
        ProgramMembership.Level.STAFF,
    ),
    DemoAccount(
        "LANI head",
        "lani.head@scholarsync.test",
        "Liza Domingo",
        User.Role.STAFF,
        STAFF,
        "lani",
        ProgramMembership.Level.HEAD,
    ),
    DemoAccount(
        "Scholarship office",
        "office@scholarsync.test",
        "Jessica Tate",
        User.Role.SUPER_ADMIN,
        OFFICE,
    ),
]

# Made by the sample steps in loader.py (the emails match samples.py); listed here so a visitor
# can sign in as them.
SAMPLE_LOGINS: list[DemoAccount] = [
    DemoAccount(
        "Returned applicant",
        "applicant4@scholarsync.test",
        "Miguel Bautista",
        User.Role.STUDENT,
        STUDENTS,
    ),
    DemoAccount(
        "Scholar due to renew",
        "scholar@scholarsync.test",
        "Carmela Villanueva",
        User.Role.STUDENT,
        STUDENTS,
    ),
    DemoAccount(
        "Scholar on hold",
        "scholar3@scholarsync.test",
        "Elena Garcia",
        User.Role.STUDENT,
        STUDENTS,
    ),
]

# Every account the login page can offer, in the order it shows them within a group.
LISTED: list[DemoAccount] = [*ACCOUNTS[:2], *SAMPLE_LOGINS, *ACCOUNTS[2:]]
LISTED_EMAILS = frozenset(account.email for account in LISTED)
