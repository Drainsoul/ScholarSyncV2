import re

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

NAV = [
    {"label": "Dashboard", "url": "/me/", "current": True, "count": 0},
    {"label": "Applications", "url": "/me/applications/", "current": False, "count": 2},
]
PROGRAMS = [
    {"name": "TCU CEAA", "url": "/staff/tcu-ceaa/", "current": True},
    {"name": "LANI", "url": "/staff/lani/", "current": False},
]


def render(template: str, **context) -> str:
    base = {
        "nav_items": NAV,
        "viewer": {"name": "Carolyn Hawkins", "role": "Student"},
        "program": {"name": "TCU CEAA"},
        "programs": PROGRAMS,
    }
    return render_to_string(template, {**base, **context}, request=RequestFactory().get("/"))


@pytest.mark.parametrize(
    "layout",
    [
        "layouts/public.html",
        "layouts/auth.html",
        "layouts/student.html",
        "layouts/staff.html",
        "layouts/office.html",
    ],
)
def test_every_layout_has_one_main_a_skip_link_and_the_logo(layout, vite_build):
    html = render(layout)
    assert html.count('<main id="main"') == 1
    assert '<a class="skip-link" href="#main">' in html
    assert "icons.svg#logo" in html


def test_current_nav_item_is_marked(vite_build):
    html = render("layouts/student.html")
    assert '<a href="/me/" aria-current="page">' in html
    assert html.count('aria-current="page"') == 1
    assert '<span class="tag">2</span>' in html


def test_nav_toggle_is_hidden_until_javascript_runs(vite_build):
    html = render("layouts/staff.html")
    assert re.search(r"<button[^>]*data-nav-toggle[^>]*\bhidden>", html)


def test_program_switcher_lists_programs(vite_build):
    html = render("layouts/staff.html")
    assert '<a href="/staff/lani/">LANI</a>' in html
    assert '<a href="/staff/tcu-ceaa/" aria-current="true">TCU CEAA</a>' in html


def test_layouts_without_nav_have_no_menu_button(vite_build):
    assert "data-nav-toggle" not in render("layouts/public.html", nav_items=[])
    assert "data-nav-toggle" not in render("layouts/auth.html")


def test_sign_out_is_a_post_form_only_when_a_url_is_given(vite_build):
    html = render("layouts/office.html", logout_url="/accounts/logout/")
    assert '<form method="post" action="/accounts/logout/">' in html
    assert "csrfmiddlewaretoken" in html
    assert "Sign out" not in render("layouts/office.html")


@pytest.mark.parametrize("layout", ["layouts/staff.html", "layouts/office.html"])
def test_app_bar_is_the_banner_landmark(layout, vite_build):
    html = render(layout)
    assert '<header class="appbar">' in html
    assert html.count("<header") == 1


@pytest.mark.parametrize(
    "layout",
    [
        "layouts/public.html",
        "layouts/auth.html",
        "layouts/student.html",
        "layouts/staff.html",
        "layouts/office.html",
    ],
)
def test_every_layout_has_the_civic_stripe(layout, vite_build):
    assert '<div class="civic-stripe" aria-hidden="true"></div>' in render(layout)


def test_app_shell_has_a_navy_top_bar_and_text_only_side_nav(vite_build):
    html = render("layouts/staff.html")
    assert '<header class="appbar">' in html
    nav = html[html.index('<nav class="sidenav"') :]
    nav = nav[: nav.index("</nav>")]
    assert "<svg" not in nav
    assert 'aria-current="page"' in nav
