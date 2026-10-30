import re
from pathlib import Path

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

STYLES = Path(__file__).resolve().parents[3] / "frontend" / "src" / "styles"
NAV = [
    {"label": "Dashboard", "url": "/me/", "current": True, "count": 0, "icon": "house"},
    {
        "label": "Applications",
        "url": "/me/applications/",
        "current": False,
        "count": 2,
        "icon": "file-text",
    },
]
NAV_SECONDARY = [
    {
        "label": "Help and guides",
        "url": "/help/",
        "current": False,
        "count": 0,
        "icon": "circle-help",
    },
]
PROGRAMS = [
    {"name": "TCU CEAA", "url": "/staff/tcu-ceaa/", "current": True},
    {"name": "LANI", "url": "/staff/lani/", "current": False},
]
APP_LAYOUTS = ["layouts/student.html", "layouts/staff.html", "layouts/office.html"]
ALL_LAYOUTS = ["layouts/public.html", "layouts/auth.html", *APP_LAYOUTS]


def render(template: str, **context) -> str:
    base = {
        "nav_items": NAV,
        "nav_secondary": NAV_SECONDARY,
        "viewer": {"name": "Carolyn Hawkins", "role": "Student"},
        "program": {"name": "TCU CEAA"},
        "programs": PROGRAMS,
    }
    return render_to_string(template, {**base, **context}, request=RequestFactory().get("/"))


def sidebar(html: str) -> str:
    start = html.index('<nav class="sidebar"')
    return html[start : html.index("</nav>", start)]


def topbar(html: str) -> str:
    start = html.index('<header class="topbar">')
    return html[start : html.index("</header>", start)]


@pytest.mark.parametrize("layout", ALL_LAYOUTS)
def test_every_layout_has_one_main_a_skip_link_and_the_logo(layout, vite_build):
    html = render(layout)
    assert html.count('<main id="main"') == 1
    assert '<a class="skip-link" href="#main">' in html
    assert "icons.svg#logo" in html


def test_current_nav_item_is_marked(vite_build):
    html = render("layouts/student.html")
    assert '<a href="/me/" aria-current="page">' in html
    assert html.count('aria-current="page"') == 1
    assert '<span class="count count--accent">2</span>' in html


def test_nav_toggle_is_hidden_until_javascript_runs(vite_build):
    html = render("layouts/staff.html")
    assert re.search(r"<button[^>]*data-nav-toggle[^>]*\bhidden>", html)
    assert 'aria-controls="app-nav"' in html


def test_program_switcher_lists_programs(vite_build):
    html = render("layouts/staff.html")
    assert '<a href="/staff/lani/">LANI</a>' in html
    assert '<a href="/staff/tcu-ceaa/" aria-current="true">TCU CEAA</a>' in html
    assert '<details class="switcher">' in sidebar(html)


def test_layouts_without_nav_have_no_menu_button(vite_build):
    assert "data-nav-toggle" not in render("layouts/public.html", nav_items=[])
    assert "data-nav-toggle" not in render("layouts/auth.html")


def test_sign_out_is_a_post_form_only_when_a_url_is_given(vite_build):
    html = render("layouts/office.html", logout_url="/accounts/logout/")
    assert '<form method="post" action="/accounts/logout/">' in html
    assert "csrfmiddlewaretoken" in html
    assert "Sign out" not in render("layouts/office.html")


@pytest.mark.parametrize("layout", ALL_LAYOUTS)
def test_every_layout_has_the_civic_stripe(layout, vite_build):
    html = render(layout)
    stripe = '<div class="civic-stripe" aria-hidden="true"></div>'
    assert html.count(stripe) == 1
    if layout in APP_LAYOUTS:
        assert sidebar(html).index(stripe) < sidebar(html).index('class="brand"')
    else:
        body = html[html.index('<a class="skip-link"') :]
        assert body.index(stripe) < body.index("<main")


@pytest.mark.parametrize("layout", APP_LAYOUTS)
def test_app_shell_has_a_sidebar_and_a_topbar(layout, vite_build):
    html = render(layout)
    assert html.count('<nav class="sidebar"') == 1
    assert '<nav class="sidebar" id="app-nav" aria-label="Main">' in html
    assert html.count('<header class="topbar">') == 1
    assert html.count("<header") == 1
    assert html.count('<main id="main"') == 1
    assert html.index('<div class="app">') < html.index('<nav class="sidebar"')
    assert "{#" not in html  # a multi-line {# #} would render as a stray grid item
    # The Menu button is the top bar's last control, right before the sidebar it opens.
    assert html.index('<header class="topbar">') < html.index('<nav class="sidebar"')
    assert html.index('<nav class="sidebar"') < html.index('<main id="main"')
    bar = topbar(html)
    toggle = bar.index("data-nav-toggle")
    assert not re.search(r"<(a|button|input|summary)", bar[bar.index(">", toggle) :])
    nav = sidebar(html)
    items = re.findall(r"<li><a [^>]*>(.*?)</a></li>", nav, re.S)
    labels = [item for item in items if "Dashboard" in item or "Applications" in item]
    assert len(labels) == 2
    for item in [*labels, *(i for i in items if "Help and guides" in i)]:
        assert "icons.svg#" in item, item
    assert '<p class="sidebar__heading"' in nav
    assert "Workspace" in nav
    assert "Support" in nav


def test_nav_heading_can_be_renamed(vite_build):
    nav = sidebar(render("layouts/office.html", nav_heading="City-wide"))
    assert "City-wide" in nav
    assert "Workspace" not in nav


def test_support_group_is_left_out_without_secondary_items(vite_build):
    assert "Support" not in sidebar(render("layouts/staff.html", nav_secondary=[]))


def test_staff_topbar_has_search_only_with_a_search_url(vite_build):
    html = render("layouts/staff.html", search_url="/staff/tcu-ceaa/search/")
    bar = topbar(html)
    assert '<form class="topbar__search" role="search" action="/staff/tcu-ceaa/search/"' in bar
    assert '<label class="visually-hidden" for="app-search">' in bar
    assert 'type="search"' in bar
    assert 'role="search"' not in render("layouts/staff.html")


def test_student_topbar_never_has_search(vite_build):
    assert 'role="search"' not in render("layouts/student.html", search_url="/search/")


def test_topbar_term_chooser_and_notifications(vite_build):
    terms = [
        {"name": "1st sem 2026–2027", "url": "/t/1/", "current": True},
        {"name": "2nd sem 2025–2026", "url": "/t/0/", "current": False},
    ]
    html = render(
        "layouts/staff.html", terms=terms, notifications_url="/inbox/", notifications_count=3
    )
    bar = topbar(html)
    assert '<details class="switcher switcher--end">' in bar
    assert '<a href="/t/1/" aria-current="true">1st sem 2026–2027</a>' in bar
    assert (
        '<a class="icon-btn topbar__bell" href="/inbox/" aria-label="Notifications, 3 unread">'
        in bar
    )
    assert 'class="topbar__dot"' in bar
    plain = topbar(render("layouts/staff.html", notifications_url="/inbox/"))
    assert 'aria-label="Notifications">' in plain
    assert "topbar__dot" not in plain
    assert "switcher" not in plain


def test_office_sidebar_shows_the_office_context(vite_build):
    nav = sidebar(render("layouts/office.html"))
    assert 'class="sidebar__context"' in nav
    assert "Signed in to" in nav
    assert "Scholarship office" in nav
    assert "switcher" not in nav


def test_student_sidebar_has_no_context_block(vite_build):
    nav = sidebar(render("layouts/student.html"))
    assert "sidebar__context" not in nav
    assert "switcher" not in nav


def test_account_menu_holds_sign_out(vite_build):
    html = render("layouts/staff.html", logout_url="/accounts/logout/")
    nav = sidebar(html)
    menu = re.search(r'<details class="account-menu">(.*?)</details>', nav, re.S)
    assert menu, "the user card is an account menu"
    summary = re.search(r"<summary>(.*?)</summary>", menu.group(1), re.S)
    assert summary
    assert "Carolyn Hawkins" in summary.group(1)
    assert "Student" in summary.group(1)
    assert 'class="avatar' in summary.group(1)
    assert '<form method="post" action="/accounts/logout/">' in menu.group(1)
    assert "Sign out" in menu.group(1)
    # Without a sign-out URL the user card shows who is signed in, with no empty menu.
    plain = sidebar(render("layouts/staff.html"))
    assert "account-menu" not in plain
    assert "Carolyn Hawkins" in plain


def test_sidebar_callout_block_is_empty_by_default(vite_build):
    assert "sidebar__callout" not in render("layouts/staff.html")


def test_sign_out_shows_with_a_logout_url_even_without_a_viewer(vite_build):
    html = render("layouts/staff.html", viewer=None, logout_url="/accounts/logout/")
    assert '<form method="post" action="/accounts/logout/">' in html
    assert "csrfmiddlewaretoken" in html
    assert "Sign out" in html


def test_a_context_items_variable_does_not_change_the_nav(vite_build):
    stray = [{"label": "Stray", "url": "/stray/", "current": False, "count": 0, "icon": ""}]
    for layout in ("layouts/public.html", "layouts/staff.html"):
        assert "Stray" not in render(layout, items=stray)
        assert "Stray" not in render(layout, items=stray, nav_secondary=[])


def _css_rules(selector_start: str) -> str:
    css = (STYLES / "layouts.css").read_text(encoding="utf-8")
    return "".join(
        m.group(0) for m in re.finditer(rf"{re.escape(selector_start)}[^{{]*\{{[^}}]*\}}", css)
    )


def test_auth_panel_uses_on_primary_text():
    rules = _css_rules(".auth__panel") + _css_rules(".auth__tagline") + _css_rules(".auth__note")
    assert "var(--on-primary)" in rules
    assert "var(--text-muted)" not in rules
    assert "var(--nav-" not in rules
    assert re.search(r"\.auth__panel \{[^}]*background: var\(--primary\)", rules)
    assert "var(--on-primary)" in _css_rules(".auth__panel .brand__mark")
