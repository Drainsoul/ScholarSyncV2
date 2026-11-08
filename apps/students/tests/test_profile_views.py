import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.students.forms import PersonalForm
from apps.students.models import StudentProfile
from apps.students.tests.factories import FullProfileFactory, ProfileFactory

pytestmark = pytest.mark.django_db

PHONE_ERROR = "Enter a mobile number like 0917 123 4567."


def personal_data(**overrides):
    data = {
        "first_name": "Ma. Niña",
        "middle_name": "",
        "last_name": "Dela Cruz-Santos",
        "suffix": "",
        "birth_date": "2006-03-14",
        "sex": "female",
        "phone": "0917 123 4567",
        "address_line": "12 Mabini Street",
        "barangay": "ususan",
        "residing_since": "2010",
        "is_registered_voter": "False",
        "monthly_household_income": "25,000.50",
    }
    return {**data, **overrides}


@pytest.fixture
def student(db):
    return UserFactory.create(verified=True)


@pytest.fixture
def signed_in(client, student):
    client.force_login(student)
    return client


@pytest.mark.parametrize("phone", ["0917 123 4567", "639171234567", "+63 (917) 123-4567"])
def test_valid_phones_are_stored_in_international_form(phone):
    form = PersonalForm(personal_data(phone=phone))
    assert form.is_valid(), form.errors
    assert form.cleaned_data["phone"] == "+639171234567"


@pytest.mark.parametrize("phone", ["0217123456", "12345", "0917123456a"])
def test_other_phones_are_refused(phone):
    form = PersonalForm(personal_data(phone=phone))
    assert form.errors["phone"] == [PHONE_ERROR]


def test_income_accepts_thousands_commas():
    form = PersonalForm(personal_data(monthly_household_income="25,000.50"))
    assert form.is_valid(), form.errors
    assert form.cleaned_data["monthly_household_income"] == Decimal("25000.50")


def test_negative_income_is_refused():
    assert (
        "monthly_household_income"
        in PersonalForm(personal_data(monthly_household_income="-1")).errors
    )


def test_future_birth_date_is_refused():
    form = PersonalForm(personal_data(birth_date="2999-01-01"))
    assert form.errors["birth_date"] == ["Your birth date can't be in the future."]


def test_birth_date_before_1900_is_refused():
    assert "birth_date" in PersonalForm(personal_data(birth_date="1899-12-31")).errors


def test_residing_since_before_birth_year_is_refused():
    form = PersonalForm(personal_data(residing_since="2000"))
    assert form.errors["residing_since"] == [
        f"Enter a year from your birth year to {date.today().year}."
    ]


def test_residing_since_without_birth_date_is_capped_at_this_year():
    form = PersonalForm(personal_data(birth_date="", residing_since="2999"))
    assert form.errors["residing_since"] == [f"Enter a year up to {date.today().year}."]


def test_registered_voter_is_required():
    assert "is_registered_voter" in PersonalForm(personal_data(is_registered_voter="")).errors


def test_labels():
    form = PersonalForm()
    assert form.fields["sex"].label == "Sex (as on your birth certificate)"
    assert form.fields["residing_since"].label == "Living in Taguig since (year)"
    assert form.fields["is_registered_voter"].label == "Registered voter of Taguig"
    assert form.fields["monthly_household_income"].label == "Monthly household income (₱)"


def test_get_personal_without_profile_shows_empty_form(signed_in):
    response = signed_in.get(reverse("students:profile-personal"))
    assert response.status_code == 200
    assert b'name="first_name"' in response.content


def test_valid_post_saves_and_redirects(signed_in, student):
    response = signed_in.post(reverse("students:profile-personal"), personal_data())
    assert response.status_code == 302
    assert response["Location"] == reverse("students:profile")
    profile = StudentProfile.objects.get(user=student)
    assert profile.phone == "+639171234567"
    assert profile.monthly_household_income == Decimal("25000.50")
    student.refresh_from_db()
    assert student.full_name == "Ma. Niña Dela Cruz-Santos"
    assert AuditEvent.objects.filter(action="profile.updated").count() == 1
    followed = signed_in.get(response["Location"])
    assert "Personal details saved." in followed.content.decode()


def test_invalid_post_rerenders_with_errors(signed_in, student):
    response = signed_in.post(reverse("students:profile-personal"), personal_data(phone="12345"))
    assert response.status_code == 200
    assert PHONE_ERROR in response.content.decode()
    assert not StudentProfile.objects.filter(user=student).exists()


def test_overview_without_profile_lists_sections_as_missing(signed_in):
    response = signed_in.get(reverse("students:profile"))
    html = response.content.decode()
    assert response.status_code == 200
    assert "Missing: first name, last name" in html
    assert html.count("Edit") >= 1
    assert "<img" not in html.split("<main", 1)[1]


def test_overview_shows_missing_phone(signed_in, student):
    FullProfileFactory.create(user=student, phone="")
    html = signed_in.get(reverse("students:profile")).content.decode()
    assert "Missing: phone" in html


def test_overview_marks_a_finished_section_complete(signed_in, student):
    FullProfileFactory.create(user=student)
    html = signed_in.get(reverse("students:profile")).content.decode()
    assert "Complete</p>" in html


def test_overview_links_only_to_pages_that_exist(signed_in):
    html = signed_in.get(reverse("students:profile")).content.decode()
    assert reverse("students:profile-personal") in html


def test_overview_uses_at_most_6_queries(signed_in, student, django_assert_max_num_queries):
    ProfileFactory.create(user=student)
    with django_assert_max_num_queries(6):
        assert signed_in.get(reverse("students:profile")).status_code == 200


def test_home_card_for_new_student(signed_in):
    html = signed_in.get(reverse("students:home")).content.decode()
    assert "0%" in html and "complete" in html
    assert "Complete your profile" in html
    assert reverse("students:profile") in html


def test_home_card_at_100_percent_offers_view(signed_in, student, monkeypatch):
    from apps.students import views
    from apps.students.completion import Completion

    monkeypatch.setattr(
        views, "profile_page", lambda user: (None, Completion(percent=100, sections=()))
    )
    html = signed_in.get(reverse("students:home")).content.decode()
    assert "View your profile" in html


def nav_link(html, href):
    start = html.index('<nav class="sidebar"')
    nav = html[start : html.index("</nav>", start)]
    found = re.search(rf'<li><a href="{href}"[^>]*>', nav)
    assert found is not None
    return found.group(0)


def test_nav_marks_profile_current_on_personal_page(signed_in):
    html = signed_in.get("/me/profile/personal/").content.decode()
    assert 'aria-current="page"' in nav_link(html, "/me/profile/")
    assert "aria-current" not in nav_link(html, "/me/")


def test_nav_marks_home_current_only_on_home(signed_in):
    html = signed_in.get("/me/").content.decode()
    assert 'aria-current="page"' in nav_link(html, "/me/")
    assert "aria-current" not in nav_link(html, "/me/profile/")
