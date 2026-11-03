"""The four demo accounts. Explore mode only; they share one published password."""

from dataclasses import dataclass

from apps.accounts.models import User
from apps.programs.models import ProgramMembership

PASSWORD = "explore-taguig-2026"  # noqa: S105 (public by design, shown on the login page)


@dataclass(frozen=True)
class DemoAccount:
    button: str
    email: str
    full_name: str
    role: User.Role
    program: str | None = None
    level: ProgramMembership.Level | None = None


ACCOUNTS: list[DemoAccount] = [
    DemoAccount("Student", "student@scholarsync.test", "Carolyn Hawkins", User.Role.STUDENT),
    DemoAccount(
        "Program staff",
        "staff@scholarsync.test",
        "Krista Kelley",
        User.Role.STAFF,
        "tcu-ceaa",
        ProgramMembership.Level.STAFF,
    ),
    DemoAccount(
        "Program head",
        "head@scholarsync.test",
        "Shannon Briggs",
        User.Role.STAFF,
        "tcu-ceaa",
        ProgramMembership.Level.HEAD,
    ),
    DemoAccount(
        "Scholarship office",
        "office@scholarsync.test",
        "Jessica Tate",
        User.Role.SUPER_ADMIN,
    ),
]
