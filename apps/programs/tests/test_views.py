import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.programs.models import AcademicTerm
from apps.programs.tests.factories import ProgramFactory

pytestmark = pytest.mark.django_db


def test_list_shows_active_programs_and_links_to_them(client):
    ProgramFactory(slug="alpha", name="Alpha Grant")
    ProgramFactory(slug="hidden", name="Hidden Grant", is_active=False)
    response = client.get(reverse("programs:list"))
    html = response.content.decode()
    assert response.status_code == 200
    assert "Alpha Grant" in html
    assert f'href="{reverse("programs:detail", kwargs={"slug": "alpha"})}"' in html
    assert "Hidden Grant" not in html


def test_lani_detail_shows_amounts_after_seeding(client):
    call_command("seed_programs")
    response = client.get(reverse("programs:detail", kwargs={"slug": "lani"}))
    html = response.content.decode()
    assert response.status_code == 200
    assert "₱25,000.00" in html
    assert "Basic Plus" in html
    assert "Who can apply" in html
    assert "Documents for new applicants" in html


@pytest.mark.parametrize("slug", ["nope", "off"])
def test_inactive_or_unknown_program_is_404(client, slug):
    ProgramFactory(slug="off", is_active=False)
    assert client.get(reverse("programs:detail", kwargs={"slug": slug})).status_code == 404


def test_detail_without_a_current_term_says_amounts_come_later(client):
    ProgramFactory(slug="alpha")
    AcademicTerm.objects.update(is_current=False)
    html = client.get(reverse("programs:detail", kwargs={"slug": "alpha"})).content.decode()
    assert "Amounts will be published with the next school term." in html
    assert "Dates to be announced." in html
    assert "The scholarship office hasn't published the rules yet." in html


def test_public_top_bar_lists_programs_first(client):
    html = client.get(reverse("core:about")).content.decode()
    nav = html[html.index('id="site-nav"') :]
    assert nav.index(reverse("programs:list")) < nav.index(reverse("core:help"))


def test_list_page_query_budget(client, django_assert_max_num_queries):
    call_command("seed_programs")
    with django_assert_max_num_queries(3):
        client.get(reverse("programs:list"))


def test_detail_page_query_budget(client, django_assert_max_num_queries):
    call_command("seed_programs")
    url = reverse("programs:detail", kwargs={"slug": "tcu-ceaa"})
    with django_assert_max_num_queries(6):
        client.get(url)
