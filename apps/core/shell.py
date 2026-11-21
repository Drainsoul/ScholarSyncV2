from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.review_selectors import waiting_count
from apps.programs.models import Program, ProgramMembership
from apps.programs.selectors import membership_for, programs_for
from apps.reports.selectors import staff_nav_count, submitted_count
from apps.workspace.selectors import unread_count
from apps.workspace.support import open_count
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
    # Staff pages: the viewer's membership (None for the office), looked up once.
    membership: ProgramMembership | None = None
    if area == "staff" and program is not None and not user.is_super_admin:
        membership = membership_for(user, program)
    head = membership is not None and membership.level == ProgramMembership.Level.HEAD
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
        if area == "staff" and program is not None and not program.is_active:
            # The office on a closed program's settings: the staff screens would 404 (M14).
            nav = []
        elif area == "staff" and program is not None:
            students = reverse("workspace:students", kwargs={"program": program.slug})
            queue = reverse("review:queue", kwargs={"program": program.slug})
            scholar_list = reverse("scholars:list", kwargs={"program": program.slug})
            money = reverse("money:overview", kwargs={"program": program.slug})
            task_list = reverse("workspace:tasks", kwargs={"program": program.slug})
            report_list = reverse("reports:list", kwargs={"program": program.slug})
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
                    "label": "Reports",
                    "url": report_list,
                    "current": path.startswith(report_list),
                    "count": staff_nav_count(program, head=head),
                    "icon": "chart-column",
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
            office_reports = reverse("office:reports")
            audit = reverse("office:audit")
            insights = reverse("office:analytics")
            inbox = reverse("support:office")
            support_open = open_count()  # once per request; the overview reuses it
            programs = reverse("office:programs")
            accounts = reverse("office:staff")
            office_scholars = reverse("office:scholars")
            schools = reverse("office:schools")
            office_tasks = reverse("office:tasks")
            path = request.path
            nav = [
                {"label": label, "url": home, "current": path == home, "count": 0, "icon": icon},
                {
                    "label": "Programs",
                    "url": programs,
                    "current": path.startswith(programs),
                    "count": 0,
                    "icon": "clipboard-check",
                },
                {
                    "label": "Staff",
                    "url": accounts,
                    "current": path.startswith(accounts),
                    "count": 0,
                    "icon": "user",
                },
                {
                    "label": "Scholars",
                    "url": office_scholars,
                    "current": path.startswith(office_scholars),
                    "count": 0,
                    "icon": "users",
                },
                {
                    "label": "Schools",
                    "url": schools,
                    "current": path.startswith(schools),
                    "count": 0,
                    "icon": "building-2",
                },
                {
                    "label": "Terms",
                    "url": terms,
                    "current": path.startswith(terms),
                    "count": 0,
                    "icon": "calendar",
                },
                {
                    "label": "Reports",
                    "url": office_reports,
                    "current": path.startswith(office_reports),
                    "count": submitted_count(),
                    "icon": "file-text",
                },
                {
                    "label": "Tasks",
                    "url": office_tasks,
                    "current": path.startswith(office_tasks),
                    "count": due_count(user, None, today=timezone.localdate()),
                    "icon": "list-checks",
                },
                {
                    "label": "Analytics",
                    "url": insights,
                    "current": path.startswith(insights),
                    "count": 0,
                    "icon": "chart-column",
                },
                {
                    "label": "Audit log",
                    "url": audit,
                    "current": path.startswith(audit),
                    "count": 0,
                    "icon": "shield",
                },
                {
                    "label": "Support",
                    "url": inbox,
                    "current": path.startswith(inbox),
                    "count": support_open,
                    "icon": "inbox",
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
        help_url = reverse("support:student")
        context["nav_secondary"] = [
            {
                "label": "Help and guides",
                "url": help_url,
                "current": request.path.startswith(help_url),
                "count": 0,
                "icon": "circle-help",
            }
        ]
        context["notifications_count"] = unread_count(user)
    if area == "office":
        context["support_open"] = support_open
        context["notifications_url"] = reverse("office:notifications")
        context["notifications_count"] = unread_count(user)
    if area == "staff" and program is not None:
        context["notifications_url"] = reverse(
            "notifications-staff:list", kwargs={"program": program.slug}
        )
        context["notifications_count"] = unread_count(user)
        context["program"] = program
        context["programs"] = [
            {
                "name": item.name,
                "url": reverse("workspace:dashboard", kwargs={"program": item.slug}),
                "current": item.pk == program.pk,
            }
            for item in programs_for(user).order_by("name")
        ]
        if user.is_super_admin or head:
            settings_url = reverse("settings:rules", kwargs={"program": program.slug})
            audit_url = reverse("audit:program", kwargs={"program": program.slug})
            context["nav_secondary"] = [
                {
                    "label": "Settings",
                    "url": settings_url,
                    "current": request.path.startswith(settings_url),
                    "count": 0,
                    "icon": "sliders-horizontal",
                },
                {
                    "label": "Audit log",
                    "url": audit_url,
                    "current": request.path.startswith(audit_url),
                    "count": 0,
                    "icon": "shield",
                },
            ]
            if not program.is_active:
                # A closed program: only Settings answers (its staff screens and audit log 404),
                # and the logo goes back to the office.
                context["nav_secondary"] = [
                    {
                        "label": "Settings",
                        "url": settings_url,
                        "current": request.path.startswith(settings_url),
                        "count": 0,
                        "icon": "sliders-horizontal",
                    }
                ]
                context["home_url"] = reverse("office:home")
                context["notifications_url"] = reverse("office:notifications")
    return context
