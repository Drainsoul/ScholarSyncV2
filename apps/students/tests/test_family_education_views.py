from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.core.models import AuditEvent
from apps.programs.models import School
from apps.programs.tests.factories import SchoolFactory
from apps.students.forms import EducationForm, FamilyMemberForm
from apps.students.models import EducationRecord, FamilyMember
from apps.students.tests.factories import (
    EducationRecordFactory,
    FamilyMemberFactory,
    FullProfileFactory,
    ProfileFactory,
)

pytestmark = pytest.mark.django_db

PHONE_ERROR = "Enter a mobile number like 0917 123 4567."
THIS_YEAR = date.today().year


@pytest.fixture
def student(db):
    return UserFactory.create(verified=True)


@pytest.fixture
def signed_in(client, student):
    client.force_login(student)
    return client


@pytest.fixture
def profile(student):
    return FullProfileFactory.create(user=student)


def family_data(**overrides):
    data = {
        "relation": "mother",
        "name": "Ma. Luz Dela Cruz",
        "occupation": "Vendor",
        "monthly_income": "12,500.50",
        "contact": "0917 123 4567",
    }
    return {**data, **overrides}


def education_data(**overrides):
    data = {
        "level": "college",
        "school": "",
        "school_name": "Bicutan Science School",
        "school_type": "public",
        "gwa_scale": "percent",
        "course": "BS Biology",
        "year_level": "2",
        "gwa": "90",
        "units": "21",
        "year_from": "2024",
        "year_to": "2028",
        "is_current": "on",
    }
    return {**data, **overrides}


# --- family form ---------------------------------------------------------------------------


def test_family_form_normalises_phone_and_income():
    form = FamilyMemberForm(family_data())
    assert form.is_valid(), form.errors
    assert form.cleaned_data["contact"] == "+639171234567"
    assert form.cleaned_data["monthly_income"] == Decimal("12500.50")


def test_family_contact_and_income_may_be_blank():
    form = FamilyMemberForm(family_data(contact="", monthly_income="", occupation=""))
    assert form.is_valid(), form.errors


def test_family_bad_phone_and_negative_income_are_refused():
    form = FamilyMemberForm(family_data(contact="12345", monthly_income="-1"))
    assert form.errors["contact"] == [PHONE_ERROR]
    assert "monthly_income" in form.errors


def test_family_name_is_required():
    assert "name" in FamilyMemberForm(family_data(name="  ")).errors


# --- education form ------------------------------------------------------------------------


def test_education_needs_a_school_or_a_name():
    form = EducationForm(education_data(school_name=""))
    assert form.non_field_errors() == ["Choose your school or type its name."]
    form = EducationForm(education_data(school_name="   "))
    assert form.non_field_errors() == ["Choose your school or type its name."]


def test_education_refuses_school_and_name_together():
    school = SchoolFactory.create()
    form = EducationForm(education_data(school=str(school.pk)))
    assert form.non_field_errors() == ["Choose a school from the list or type a name, not both."]


def test_name_requires_type_and_scale():
    form = EducationForm(education_data(school_type="", gwa_scale="", gwa=""))
    assert "school_type" in form.errors
    assert "gwa_scale" in form.errors


def test_gwa_needs_a_scale():
    form = EducationForm(education_data(gwa_scale=""))
    assert "gwa_scale" in form.errors


@pytest.mark.parametrize(
    ("scale", "gwa", "message"),
    [
        ("one_to_five", "95", "Enter a GWA from 1.00 to 5.00."),
        ("percent", "1.25", "Enter a GWA from 50 to 100."),
        ("percent", "101", "Enter a GWA from 50 to 100."),
        ("four_point", "4.5", "Enter a GWA from 0.00 to 4.00."),
    ],
)
def test_gwa_must_fit_its_scale(scale, gwa, message):
    form = EducationForm(education_data(gwa_scale=scale, gwa=gwa))
    assert form.errors["gwa"] == [message]


def test_a_listed_school_supplies_the_scale_for_the_range():
    school = SchoolFactory.create(grading_scale=School.Scale.ONE_TO_FIVE)
    data = education_data(school=str(school.pk), school_name="", school_type="", gwa_scale="")
    assert EducationForm({**data, "gwa": "95"}).errors["gwa"] == ["Enter a GWA from 1.00 to 5.00."]
    assert EducationForm({**data, "gwa": "1.25"}).is_valid()


@pytest.mark.parametrize(
    ("level", "year_level"),
    [("elementary", 7), ("jhs", 6), ("shs", 10), ("college", 6), ("college", 0)],
)
def test_year_level_ranges(level, year_level):
    form = EducationForm(education_data(level=level, year_level=str(year_level)))
    assert "year_level" in form.errors


def test_year_level_error_text():
    form = EducationForm(education_data(level="shs", year_level="13"))
    assert form.errors["year_level"] == ["Enter a year level from 11 to 12."]


def test_als_has_no_year_level_range():
    form = EducationForm(education_data(level="als", year_level="40"))
    assert "year_level" not in form.errors


def test_years_must_be_ordered_and_in_range():
    form = EducationForm(education_data(year_from="2028", year_to="2024"))
    assert "year_to" in form.errors
    assert "year_from" in EducationForm(education_data(year_from="1949")).errors
    assert "year_to" in EducationForm(education_data(year_to=str(THIS_YEAR + 7))).errors
    assert EducationForm(education_data(year_to=str(THIS_YEAR + 6))).is_valid()


def test_school_choice_has_an_empty_option():
    field = EducationForm().fields["school"]
    assert getattr(field, "empty_label", None) == "My school isn't listed"


# --- family views --------------------------------------------------------------------------


def test_family_add_edit_remove_round_trip(signed_in, profile):
    response = signed_in.post(reverse("students:profile-family-add"), family_data())
    assert response.status_code == 302
    assert response["Location"] == reverse("students:profile-family")
    assert "Family member added." in signed_in.get(response["Location"]).content.decode()
    member = FamilyMember.objects.get(profile=profile)
    assert member.contact == "+639171234567"
    assert AuditEvent.objects.filter(action="family.added").count() == 1

    url = reverse("students:profile-family-edit", kwargs={"pk": member.pk})
    assert signed_in.get(url).status_code == 200
    response = signed_in.post(url, family_data(occupation="Teacher"))
    assert response["Location"] == reverse("students:profile-family")
    member.refresh_from_db()
    assert member.occupation == "Teacher"
    assert AuditEvent.objects.filter(action="family.updated").count() == 1
    assert "Family member updated." in signed_in.get(response["Location"]).content.decode()

    url = reverse("students:profile-family-delete", kwargs={"pk": member.pk})
    assert signed_in.get(url).status_code == 200
    assert FamilyMember.objects.filter(pk=member.pk).exists()
    response = signed_in.post(url)
    assert response["Location"] == reverse("students:profile-family")
    assert not FamilyMember.objects.filter(pk=member.pk).exists()
    assert AuditEvent.objects.filter(action="family.removed").count() == 1
    assert "Family member removed." in signed_in.get(response["Location"]).content.decode()


def test_family_add_without_profile_creates_one(signed_in, student):
    response = signed_in.post(reverse("students:profile-family-add"), family_data())
    assert response.status_code == 302
    assert FamilyMember.objects.filter(profile__user=student).count() == 1


def test_family_invalid_post_rerenders_with_errors(signed_in, profile):
    response = signed_in.post(reverse("students:profile-family-add"), family_data(contact="1"))
    assert response.status_code == 200
    assert PHONE_ERROR in response.content.decode()
    assert not FamilyMember.objects.exists()


def test_family_list_is_empty_without_profile(signed_in):
    assert signed_in.get(reverse("students:profile-family")).status_code == 200


@pytest.mark.parametrize("route", ["profile-family-edit", "profile-family-delete"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_other_students_family_row_is_404_and_unchanged(signed_in, profile, route, method):
    other = FamilyMemberFactory.create(profile=ProfileFactory.create(), name="Their Mother")
    url = reverse(f"students:{route}", kwargs={"pk": other.pk})
    response = getattr(signed_in, method)(url, family_data(name="Changed"))
    assert response.status_code == 404
    other.refresh_from_db()
    assert other.name == "Their Mother"
    assert not AuditEvent.objects.filter(action__startswith="family.").exists()


def test_family_list_query_count(signed_in, profile, django_assert_max_num_queries):
    FamilyMemberFactory.create_batch(4, profile=profile)
    with django_assert_max_num_queries(6):
        response = signed_in.get(reverse("students:profile-family"))
    assert response.status_code == 200


# --- education views -----------------------------------------------------------------------


def test_education_add_edit_remove_round_trip(signed_in, profile):
    response = signed_in.post(reverse("students:profile-education-add"), education_data())
    assert response.status_code == 302
    assert response["Location"] == reverse("students:profile-education")
    assert "School added." in signed_in.get(response["Location"]).content.decode()
    record = EducationRecord.objects.get(profile=profile)
    assert record.school_name == "Bicutan Science School"
    assert record.gwa == Decimal("90")
    assert AuditEvent.objects.filter(action="education.added").count() == 1

    url = reverse("students:profile-education-edit", kwargs={"pk": record.pk})
    assert signed_in.get(url).status_code == 200
    response = signed_in.post(url, education_data(course="BS Chemistry"))
    assert response["Location"] == reverse("students:profile-education")
    record.refresh_from_db()
    assert record.course == "BS Chemistry"
    assert AuditEvent.objects.filter(action="education.updated").count() == 1
    assert "School updated." in signed_in.get(response["Location"]).content.decode()

    url = reverse("students:profile-education-delete", kwargs={"pk": record.pk})
    assert signed_in.get(url).status_code == 200
    assert EducationRecord.objects.filter(pk=record.pk).exists()
    response = signed_in.post(url)
    assert response["Location"] == reverse("students:profile-education")
    assert not EducationRecord.objects.filter(pk=record.pk).exists()
    assert AuditEvent.objects.filter(action="education.removed").count() == 1
    assert "School removed." in signed_in.get(response["Location"]).content.decode()


def test_listed_school_takes_its_scale(signed_in, profile):
    school = SchoolFactory.create(grading_scale=School.Scale.ONE_TO_FIVE)
    data = education_data(
        school=str(school.pk), school_name="", school_type="", gwa_scale="", gwa="1.75"
    )
    assert signed_in.post(reverse("students:profile-education-add"), data).status_code == 302
    record = EducationRecord.objects.get(profile=profile)
    assert record.school == school
    assert record.gwa_scale == "one_to_five"
    assert record.school_name == ""


def test_education_edit_form_shows_the_stored_row(signed_in, profile):
    record = EducationRecordFactory.create(profile=profile, course="BS Physics")
    url = reverse("students:profile-education-edit", kwargs={"pk": record.pk})
    assert "BS Physics" in signed_in.get(url).content.decode()


def test_education_invalid_post_rerenders_with_errors(signed_in, profile):
    response = signed_in.post(
        reverse("students:profile-education-add"), education_data(gwa_scale="one_to_five")
    )
    assert response.status_code == 200
    assert "Enter a GWA from 1.00 to 5.00." in response.content.decode()
    assert not EducationRecord.objects.exists()


@pytest.mark.parametrize("route", ["profile-education-edit", "profile-education-delete"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_other_students_education_row_is_404_and_unchanged(signed_in, profile, route, method):
    other = EducationRecordFactory.create(profile=ProfileFactory.create(), course="Theirs")
    url = reverse(f"students:{route}", kwargs={"pk": other.pk})
    response = getattr(signed_in, method)(url, education_data(course="Changed"))
    assert response.status_code == 404
    other.refresh_from_db()
    assert other.course == "Theirs"
    assert not AuditEvent.objects.filter(action__startswith="education.").exists()


def test_education_list_query_count(signed_in, profile, django_assert_max_num_queries):
    EducationRecordFactory.create_batch(5, profile=profile, is_current=False)
    with django_assert_max_num_queries(6):
        response = signed_in.get(reverse("students:profile-education"))
    assert response.status_code == 200


def test_overview_links_to_the_new_sections(signed_in, profile):
    content = signed_in.get(reverse("students:profile")).content.decode()
    assert reverse("students:profile-family") in content
    assert reverse("students:profile-education") in content
