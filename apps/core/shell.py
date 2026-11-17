from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.review_selectors import waiting_count
from apps.programs.models import Program
from apps.programs.selectors import programs_for
from apps.workspace.selectors import unread_count
from apps.workspace.tasks import due_count

# The staff "Disbursements" item is current on every money section (under the dashboard URL).
MONEY_SECTIONS = ("schedules/", "disbursements/", "budget/")


def home_url_for(user: User) -> str:
    """Where this user lands after signing in. Anonymous or inactive users get the login page."""
    if not user.is_authenticated or not user.is_active:
        return reverse("account_login")
    if user.is_super_admin:
        return reverse("office:home")
    if user.is_program_staff:
        first = programs_for(user).order_by("name").first()
        if first is None:
            return reverse("workspace:no_programs")
        return reverse("workspace:dashboard", kwargs={"program": first.slug})
    return reverse("students:home")


def shell_context(
    request: HttpRequest, *, area: str, program: Program | None = None
) -> dict[str, object]:
    """Context the app layouts expect: viewer, sign-out, home link, nav and program switcher."""
    user = request.user
    assert isinstance(user, User)
    nav: list[dict[str, object]]
    if area == "student":
        home, label, icon = reverse("students:home"), "Home", "house"
        profile = reverse("students:profile")
        match = reverse("matching:match")
        applications = reverse("applications:list")
        scholarships = reverse("scholarships:list")
        path = request.path
        nav = [
            {"label": label, "url": home, "current": path == home, "count": 0, "icon": icon},
            {
                "label": "Profile",
                "url": profile,
                "current": path.startswith(profile),
                "count": 0,
                "icon": "user",
            },
            {
                "label": "Find scholarships",
                "url": match,
                "current": path.startswith(match),
                "count": 0,
                "icon": "list-checks",
            },
            {
                "label": "Applications",
                "url": applications,
                "current": path.startswith(applications),
                "count": 0,
                "icon": "file-text",
            },
            {
                "label": "Scholarships",
                "url": scholarships,
                "current": path.startswith(scholarships),
                "count": 0,
                "icon": "wallet",
            },
        ]
    else:
        if area == "office":
            home, label, icon = reverse("office:home"), "Overview", "layout-dashboard"
        elif program is not None:
            home = reverse("workspace:dashboard", kwargs={"program": program.slug})
            label, icon = "Dashboard", "layout-dashboard"
        else:
            home, label, icon = reverse("workspace:no_programs"), "Dashboard", "layout-dashboard"
        if area == "staff" and program is not None:
            students = reverse("workspace:students", kwargs={"program": program.slug})
            queue = reverse("review:queue", kwargs={"program": program.slug})
            scholar_list = reverse("scholars:list", kwargs={"program": program.slug})
            money = reverse("money:overview", kwargs={"program": program.slug})
            task_list = reverse("workspace:tasks", kwargs={"program": program.slug})
            path = request.path
            nav = [
                {"label": label, "url": home, "current": path == home, "count": 0, "icon": icon},
                {
                    "label": "Applications",
                    "url": queue,
                    "current": path.startswith(queue),
                    "count": waiting_count(program),
                    "icon": "file-text",
                },
                {
                    "label": "Scholars",
                    "url": scholar_list,
                    "current": path.startswith(scholar_list),
                    "count": 0,
                    "icon": "school",
                },
                {
                    "label": "Disbursements",
                    "url": money,
                    "current": any(path.startswith(home + part) for part in MONEY_SECTIONS),
                    "count": 0,
                    "icon": "banknote",
                },
                {
                    "label": "Students",
                    "url": students,
                    "current": path.startswith(students),
                    "count": 0,
                    "icon": "users",
                },
                {
                    "label": "Tasks",
                    "url": task_list,
                    "current": path.startswith(task_list),
                    "count": due_count(user, program, today=timezone.localdate()),
                    "icon": "list-checks",
                },
            ]
        elif area == "office":
            terms = reverse("office:terms")
            path = request.path
            nav = [
                {"label": label, "url": home, "current": path == home, "count": 0, "icon": icon},
                {
                    "label": "Terms",
                    "url": terms,
                    "current": path.startswith(terms),
                    "count": 0,
                    "icon": "calendar",
                },
            ]
        else:
            nav = [{"label": label, "url": home, "current": True, "count": 0, "icon": icon}]
    context: dict[str, object] = {
        "viewer": {
            "name": user.full_name or user.email,
            "first_name": user.get_short_name(),
            "role": user.get_role_display(),
        },
        "logout_url": reverse("account_logout"),
        "home_url": home,
        "nav_items": nav,
    }
    if area == "student":
        context["notifications_url"] = reverse("notifications:list")
        context["notifications_count"] = unread_count(user)
    if area == "staff" and program is not None:
        context["program"] = program
        context["programs"] = [
            {
                "name": item.name,
                "url": reverse("workspace:dashboard", kwargs={"program": item.slug}),
                "current": item.pk == program.pk,
            }
            for item in programs_for(user).order_by("name")
        ]
    return context
