"""Browser steps shared by the end-to-end tests."""

import base64
import re
from decimal import Decimal
from typing import Any

from django.utils import timezone
from playwright.sync_api import FilePayload, Page, expect

from apps.accounts.tests.factories import DEFAULT_PASSWORD
from apps.applications.models import Application
from apps.applications.tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentFileFactory,
)
from apps.programs.models import AcademicTerm, BenefitTier, Program, RequiredDocument
from apps.programs.tests.factories import (
    AcademicTermFactory,
    BenefitTierFactory,
    RequiredDocumentFactory,
)
from apps.students.tests.factories import FullProfileFactory

SIGNUP_PASSWORD = "signup-pass-2026"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
# A 20x20 solid PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAIAAAAC64paAAAAGklEQVR4nGMQaDhANmIY1TyqeVTzqOaB1QwANQINH6BXGBYAAAAASUVORK5CYII="
)


def one_kb_pdf() -> bytes:
    return PDF + b"%" + b"0" * (1024 - len(PDF) - 2) + b"\n"


def payload(name: str, mime_type: str, buffer: bytes) -> FilePayload:
    return {"name": name, "mimeType": mime_type, "buffer": buffer}


def log_in(page: Page, base: str, email: str, next_path: str = "/me/") -> None:
    page.goto(f"{base}/accounts/login/?next={next_path}")
    page.locator("#login-form input[name=login]").fill(email)
    page.locator("#login-form input[name=password]").fill(DEFAULT_PASSWORD)
    page.get_by_role("button", name="Log in").click()


def sign_up_and_verify(page: Page, base: str, mailoutbox, name: str, email: str) -> None:
    page.goto(f"{base}/accounts/signup/")
    page.get_by_label("Full name").fill(name)
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password", exact=True).fill(SIGNUP_PASSWORD)
    page.get_by_label("Password (again)").fill(SIGNUP_PASSWORD)
    page.get_by_label("I have read the privacy notice").check()
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Check your email")
    match = re.search(r"https?://\S+/accounts/confirm-email/\S+/", mailoutbox[0].body)
    assert match is not None
    page.goto(match.group(0))
    page.get_by_role("button", name="Confirm").click()
    expect(page).to_have_url(f"{base}/me/")


def fill_personal_details(page: Page, base: str) -> None:
    page.goto(f"{base}/me/profile/personal/")
    page.get_by_label("First name").fill("Carolyn")
    page.get_by_label("Last name").fill("Hawkins")
    page.get_by_label("Birth date").fill("2006-03-14")
    page.get_by_label("Sex (as on your birth certificate)").select_option("female")
    page.get_by_label("Phone").fill("0917 123 4567")
    page.get_by_label("Address line").fill("12 Mabini Street")
    page.get_by_label("Barangay").select_option("ususan")
    page.get_by_label("Living in Taguig since (year)").fill("2012")
    page.get_by_label("Yes", exact=True).check()
    page.get_by_label("Monthly household income").fill("18,000.00")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Personal details saved.")).to_be_visible()


def submitted_application(
    program: Program,
    *,
    documents: int = 2,
    status: str = Application.Status.SUBMITTED,
    first_name: str | None = None,
    **extra: Any,
) -> Application:
    """A submitted application with `documents` required documents, each with a ready file.

    Creates the current term, one benefit tier and the required documents when they don't exist
    yet, so several calls for one program share them.
    """
    term = AcademicTerm.objects.filter(is_current=True).first() or AcademicTermFactory.create(
        school_year_start=2026, is_current=True
    )
    tier = BenefitTier.objects.filter(program=program).first() or BenefitTierFactory.create(
        program=program, effective_from=term, code="full", name="Full allowance"
    )
    profile_values: dict[str, Any] = {"user__verified": True}
    if first_name is not None:
        profile_values["first_name"] = first_name
    profile = FullProfileFactory.create(**profile_values)
    now = timezone.now()
    application = ApplicationFactory.create(
        profile=profile,
        program=program,
        term=term,
        status=status,
        requested_tier=tier,
        school_name="Taguig City University",
        course="BS Information Technology",
        year_level=2,
        gwa=Decimal("90.00"),
        gwa_scale="percent",
        units=21,
        submitted_at=now,
        first_submitted_at=now,
        **extra,
    )
    for index in range(1, documents + 1):
        requirement = RequiredDocument.objects.filter(
            program=program, code=f"doc-{index}"
        ).first() or RequiredDocumentFactory.create(
            program=program, code=f"doc-{index}", label=f"Document {index}", sort_order=index
        )
        document = DocumentFactory.create(application=application, requirement=requirement)
        DocumentFileFactory.create(
            document=document,
            file__uploaded_by=profile.user,
            file__original_name=f"document-{index}.pdf",
        )
    return application
