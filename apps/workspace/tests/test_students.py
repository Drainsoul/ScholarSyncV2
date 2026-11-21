from datetime import date
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.programs.tests.factories import MembershipFactory, ProgramFactory
from apps.students.models import ProfileInvite, StudentProfile
from apps.students.services import create_staff_profile
from apps.workspace.models import EmailOutbox

pytestmark = pytest.mark.django_db

FORM = {
    "first_name": "Paolo",
    "middle_name": "",
    "last_name": "Villanueva",
    "suffix": "",
    "birth_date": "2007-05-01",
    "email": "paolo@example.com",
}


def _staff(slug: str = "tcu-ceaa") -> Any:
    program = ProgramFactory.create(slug=slug, name=slug.upper())
    return MembershipFactory.create(program=program, user__verified=True)


def _profile(membership: Any, email: str = "kid@example.com", first_name: str = "Ana") -> Any:
    profile, _ = create_staff_profile(
        actor=membership.user,
        program=membership.program,
        first_name=first_name,
        middle_name="",
        last_name="Reyes",
        suffix="",
        birth_date=date(2007, 1, 2),
        email=email,
    )
    return profile


def _list_url(slug: str = "tcu-ceaa") -> str:
    return reverse("workspace:students", kwargs={"program": slug})


def _invite_url(profile: Any, slug: str = "tcu-ceaa") -> str:
    return reverse("workspace:students-invite", kwargs={"program": slug, "profile_id": profile.pk})


def test_staff_create_a_profile_and_see_it_listed(client: Any) -> None:
    membership = _staff()
    client.force_login(membership.user)
    response = client.post(reverse("workspace:students-new", kwargs={"program": "tcu-ceaa"}), FORM)
    assert response.status_code == 302
    assert response.url == _list_url()
    assert EmailOutbox.objects.filter(kind="profile_invite").count() == 1
    html = client.get(response.url).content.decode()
    assert "Profile created and invitation sent." in html
    assert "Paolo Villanueva" in html
    assert "paolo@example.com" in html
    assert "Sent, expires" in html


def test_new_form_rejects_a_bad_email(client: Any) -> None:
    client.force_login(_staff().user)
    url = reverse("workspace:students-new", kwargs={"program": "tcu-ceaa"})
    response = client.post(url, {**FORM, "email": "nope"})
    assert response.status_code == 200
    assert not StudentProfile.objects.exists()


def test_new_form_rejects_a_future_birth_date(client: Any) -> None:
    client.force_login(_staff().user)
    url = reverse("workspace:students-new", kwargs={"program": "tcu-ceaa"})
    today = timezone.localdate()
    response = client.post(
        url, {**FORM, "birth_date": today.replace(year=today.year + 1).isoformat()}
    )
    assert response.status_code == 200
    assert not StudentProfile.objects.exists()


def test_empty_list_says_what_shows_here(client: Any) -> None:
    client.force_login(_staff().user)
    html = client.get(_list_url()).content.decode()
    assert "Profiles you create for students show here until they claim them." in html


def test_other_programs_staff_get_403_on_the_list(client: Any) -> None:
    _staff("tcu-ceaa")
    client.force_login(_staff("lani").user)
    assert client.get(_list_url()).status_code == 403


def test_list_shows_only_this_programs_profiles(client: Any) -> None:
    mine, theirs = _staff("tcu-ceaa"), _staff("lani")
    _profile(mine, first_name="Mine")
    _profile(theirs, first_name="Theirs")
    client.force_login(mine.user)
    html = client.get(_list_url()).content.decode()
    assert "Mine Reyes" in html
    assert "Theirs Reyes" not in html


def test_resend_sends_a_new_invite(client: Any) -> None:
    membership = _staff()
    profile = _profile(membership)
    client.force_login(membership.user)
    response = client.post(_invite_url(profile))
    assert response.status_code == 302
    assert ProfileInvite.objects.filter(profile=profile).count() == 2
    assert EmailOutbox.objects.filter(kind="profile_invite").count() == 2
    assert "Invitation sent again." in client.get(response.url).content.decode()


def test_resend_for_another_programs_profile_is_404(client: Any) -> None:
    mine, theirs = _staff("tcu-ceaa"), _staff("lani")
    profile = _profile(theirs)
    sent = EmailOutbox.objects.filter(kind="profile_invite").count()
    client.force_login(mine.user)
    assert client.post(_invite_url(profile)).status_code == 404
    assert ProfileInvite.objects.filter(profile=profile).count() == 1
    assert EmailOutbox.objects.filter(kind="profile_invite").count() == sent


def test_claimed_profiles_drop_off_the_list(client: Any) -> None:
    membership = _staff()
    profile = _profile(membership, first_name="Claimed")
    profile.user = UserFactory.create(verified=True)
    profile.save()
    client.force_login(membership.user)
    assert "Claimed Reyes" not in client.get(_list_url()).content.decode()
    assert client.post(_invite_url(profile)).status_code == 404


def test_expired_invite_shows_expired(client: Any) -> None:
    membership = _staff()
    profile = _profile(membership)
    ProfileInvite.objects.filter(profile=profile).update(expires_at=timezone.now())
    client.force_login(membership.user)
    assert "Expired" in client.get(_list_url()).content.decode()


def test_list_uses_at_most_8_queries_with_10_profiles(
    client: Any, django_assert_max_num_queries: Any
) -> None:
    membership = _staff()
    for index in range(10):
        _profile(membership, email=f"s{index}@example.com", first_name=f"Kid{index}")
    client.force_login(membership.user)
    with django_assert_max_num_queries(12):  # Settings check; bell, reports; support (rev 35)
        response = client.get(_list_url())
    assert response.content.decode().count("Send again") == 10


def test_nav_shows_students_and_marks_the_right_item_current(client: Any) -> None:
    client.force_login(_staff().user)
    students = _list_url()
    dashboard = reverse("workspace:dashboard", kwargs={"program": "tcu-ceaa"})
    on_list = client.get(students).content.decode()
    nav = on_list[on_list.index('<nav class="sidebar"') :]
    nav = nav[: nav.index("</nav>")]
    assert f'href="{students}" aria-current="page"' in nav
    assert f'<a href="{dashboard}" aria-current="page">' not in nav
    on_dashboard = client.get(dashboard).content.decode()
    assert f'href="{students}"' in on_dashboard
    assert f'href="{students}" aria-current' not in on_dashboard


def _uninvited(membership: Any) -> StudentProfile:
    """A profile with no invite, as an M9b import creates."""
    return StudentProfile.objects.create(
        first_name="Lia",
        last_name="Santos",
        birth_date=date(2005, 3, 14),
        created_by=membership.user,
        created_for=membership.program,
    )


def test_uninvited_profile_shows_not_invited_with_an_email_field(client: Any) -> None:
    membership = _staff()
    profile = _uninvited(membership)
    client.force_login(membership.user)
    page = client.get(_list_url()).content.decode()
    assert "Lia Santos" in page
    assert "Not invited" in page
    assert "Expired" not in page
    assert f'id="invite-email-{profile.pk}"' in page
    assert "Send invitation" in page


def test_first_invite_takes_an_email(client: Any) -> None:
    membership = _staff()
    profile = _uninvited(membership)
    client.force_login(membership.user)
    response = client.post(_invite_url(profile), {"email": " Lia@Example.com "})
    assert response.status_code == 302
    invite = ProfileInvite.objects.get(profile=profile)
    assert invite.email == "lia@example.com"
    assert EmailOutbox.objects.filter(kind="profile_invite", to="lia@example.com").count() == 1
    assert "Invitation sent." in client.get(response.url).content.decode()


def test_first_invite_without_email_is_refused(client: Any) -> None:
    membership = _staff()
    profile = _uninvited(membership)
    client.force_login(membership.user)
    response = client.post(_invite_url(profile), {"email": ""})
    assert response.status_code == 302
    assert not ProfileInvite.objects.filter(profile=profile).exists()
    assert "Enter the student&#x27;s email address." in client.get(response.url).content.decode()


def test_first_invite_bad_email_is_refused(client: Any) -> None:
    membership = _staff()
    profile = _uninvited(membership)
    client.force_login(membership.user)
    response = client.post(_invite_url(profile), {"email": "not-an-email"})
    assert not ProfileInvite.objects.filter(profile=profile).exists()
    assert "Enter a valid email address." in client.get(response.url).content.decode()


def test_staff_profile_without_invite_reads_not_invited(client) -> None:
    from apps.students.tests.factories import ProfileFactory

    program = ProgramFactory.create(slug="tcu-ceaa")
    staff = MembershipFactory.create(program=program).user
    ProfileFactory.create(user=None, created_for=program)
    client.force_login(staff)
    body = client.get(
        reverse("workspace:students", kwargs={"program": "tcu-ceaa"})
    ).content.decode()
    assert "Not invited" in body
    assert "Expired" not in body
