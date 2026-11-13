from typing import Any

import pytest
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.views import View

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.programs.models import ProgramMembership
from apps.programs.tests.factories import MembershipFactory, ProgramFactory


def _login(client: Any, user: User, **extra: str) -> Any:
    return client.post(
        "/accounts/login/", {"login": user.email, "password": DEFAULT_PASSWORD, **extra}
    )


def test_login_lands_on_the_role_home(client: Any, db: Any) -> None:
    student = UserFactory.create(verified=True)
    assert _login(client, student).url == "/me/"
    client.logout()

    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    assert _login(client, office).url == "/office/"
    client.logout()

    staff = UserFactory.create(role=User.Role.STAFF, verified=True)
    MembershipFactory.create(user=staff, program=ProgramFactory.create(slug="tcu-ceaa", name="TCU"))
    MembershipFactory.create(user=staff, program=ProgramFactory.create(slug="lani", name="LANI"))
    assert _login(client, staff).url == "/staff/lani/"
    client.logout()

    loner = UserFactory.create(role=User.Role.STAFF, verified=True)
    assert _login(client, loner).url == "/staff/"


def test_safe_next_wins_and_unsafe_next_is_ignored(client: Any, db: Any) -> None:
    office = UserFactory.create(role=User.Role.SUPER_ADMIN, verified=True)
    assert _login(client, office, next="/office/").url == "/office/"
    client.logout()
    assert _login(client, office, next="https://evil.example/").url == "/office/"
    client.logout()
    student = UserFactory.create(verified=True)
    assert _login(client, student, next="/staff/").url == "/staff/"
    client.logout()
    assert _login(client, student, next="https://evil.example/").url == "/me/"


class _HeadOnly(ProgramStaffRequiredMixin, View):
    level = ProgramMembership.Level.HEAD

    def get(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        return HttpResponse("ok")


def test_head_only_view_refuses_staff(rf: Any, db: Any) -> None:
    program = ProgramFactory.create()
    staff = MembershipFactory.create(program=program).user
    head = MembershipFactory.create(program=program, level=ProgramMembership.Level.HEAD).user
    request = rf.get("/")
    request.user = staff
    with pytest.raises(PermissionDenied):
        _HeadOnly.as_view()(request, program=program.slug)
    request.user = head
    assert _HeadOnly.as_view()(request, program=program.slug).status_code == 200


def test_inactive_program_is_404_for_staff(client: Any, db: Any) -> None:
    program = ProgramFactory.create(is_active=False)
    staff = MembershipFactory.create(program=program).user
    client.force_login(staff)
    assert client.get(f"/staff/{program.slug}/").status_code == 404


def test_staff_without_membership_is_refused(client: Any, db: Any) -> None:
    program = ProgramFactory.create()
    client.force_login(UserFactory.create(role=User.Role.STAFF))
    assert client.get(f"/staff/{program.slug}/").status_code == 403


def test_no_programs_page_only_for_staff_without_programs(client: Any, db: Any) -> None:
    client.force_login(UserFactory.create())
    response = client.get("/staff/")
    assert response.status_code == 302 and response.url == "/me/"
    client.force_login(UserFactory.create(role=User.Role.STAFF))
    assert b"No programs yet" in client.get("/staff/").content


def test_super_admin_passes_a_head_only_view(rf: Any, db: Any) -> None:
    request = rf.get("/")
    request.user = UserFactory.create(role=User.Role.SUPER_ADMIN)
    program = ProgramFactory.create()
    assert _HeadOnly.as_view()(request, program=program.slug).status_code == 200


def test_office_gets_404_for_an_inactive_program(client: Any, db: Any) -> None:
    program = ProgramFactory.create(is_active=False)
    client.force_login(UserFactory.create(role=User.Role.SUPER_ADMIN))
    assert client.get(f"/staff/{program.slug}/").status_code == 404


def test_inactive_user_is_sent_to_login(client: Any, db: Any) -> None:
    user = UserFactory.create(is_active=False)
    client.force_login(user)  # force_login ignores is_active; the session backend then rejects it
    response = client.get("/me/")
    assert response.status_code == 302 and response.url.startswith("/accounts/login/")


def test_head_of_one_program_is_only_staff_in_another(rf: Any, db: Any) -> None:
    program_a, program_b = ProgramFactory.create(), ProgramFactory.create()
    user = MembershipFactory.create(program=program_a, level=ProgramMembership.Level.HEAD).user
    MembershipFactory.create(user=user, program=program_b)
    request = rf.get("/")
    request.user = user
    assert _HeadOnly.as_view()(request, program=program_a.slug).status_code == 200
    with pytest.raises(PermissionDenied):
        _HeadOnly.as_view()(request, program=program_b.slug)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("case", "allowed"),
    [
        ("member", True),
        ("head", True),
        ("other_program_staff", False),
        ("inactive_actor", False),
        ("inactive_program_member", False),
        ("inactive_program_office", False),
        ("office_none", True),
        ("office_active_program", True),
        ("student", False),
        ("staff_none", False),
    ],
)
def test_require_program_staff(case: str, allowed: bool) -> None:
    from apps.core.permissions import require_program_staff

    program = ProgramFactory.create(
        is_active=case not in {"inactive_program_member", "inactive_program_office"}
    )
    other = ProgramFactory.create()
    target: Any = program
    if case == "member":
        actor = MembershipFactory.create(program=program).user
    elif case == "head":
        actor = MembershipFactory.create(program=program, level=ProgramMembership.Level.HEAD).user
    elif case == "other_program_staff":
        actor = MembershipFactory.create(program=other).user
    elif case == "inactive_actor":
        actor = MembershipFactory.create(program=program).user
        actor.is_active = False
        actor.save()
    elif case == "inactive_program_member":
        actor = MembershipFactory.create(program=program).user
    elif case in {"inactive_program_office", "office_active_program"}:
        actor = UserFactory.create(role=User.Role.SUPER_ADMIN)
    elif case == "office_none":
        actor = UserFactory.create(role=User.Role.SUPER_ADMIN)
        target = None
    elif case == "staff_none":
        actor = MembershipFactory.create(program=program).user
        target = None
    else:
        actor = UserFactory.create()
    if allowed:
        require_program_staff(actor, target)
    else:
        with pytest.raises(PermissionDenied, match="Only this program's staff can do that."):
            require_program_staff(actor, target)
