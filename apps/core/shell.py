from django.http import HttpRequest
from django.urls import reverse

from apps.accounts.models import User
from apps.applications.review_selectors import waiting_count
from apps.programs.models import Program
from apps.programs.selectors import programs_for


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
                    "label": "Students",
                    "url": students,
                    "current": path.startswith(students),
                    "count": 0,
                    "icon": "users",
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
