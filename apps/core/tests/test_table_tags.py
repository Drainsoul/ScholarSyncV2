from html import unescape

from django.core.paginator import Paginator
from django.template import RequestContext, Template
from django.test import RequestFactory


def render(source: str, url: str, **context) -> str:
    request = RequestFactory().get(url)
    return Template("{% load ui %}" + source).render(RequestContext(request, context))


def test_sort_th_marks_the_current_column_and_flips_it():
    html = render('{% sort_th "Name" "name" %}', "/x/?sort=name&page=3&q=ana")
    assert 'aria-sort="ascending"' in html
    assert 'href="?sort=-name&amp;q=ana"' in html
    assert '<a class="sort" id="sort-name"' in html
    assert "#arrow-up" in html


def test_sort_th_descending():
    html = render('{% sort_th "Name" "name" %}', "/x/?sort=-name")
    assert 'aria-sort="descending"' in html
    assert 'href="?sort=name"' in html
    assert "#arrow-down" in html


def test_sort_th_other_columns_are_unsorted():
    html = render('{% sort_th "School" "school" %}', "/x/?sort=name&q=ana")
    assert html.startswith('<th scope="col">')
    assert "aria-sort" not in html
    assert 'href="?sort=school&amp;q=ana"' in html
    assert "#chevrons-up-down" in html


def test_sort_th_numeric_column():
    html = render('{% sort_th "Allowance" "amount" "num" %}', "/x/")
    assert html.startswith('<th scope="col" class="num">')


def test_sort_th_escapes_label_and_query():
    html = render('{% sort_th label "name" %}', '/x/?q="><script>', label="<b>Name</b>")
    assert "<script>" not in html
    assert "<b>" not in html
    assert "&lt;b&gt;Name&lt;/b&gt;" in html


def test_pagination_keeps_filters_and_links_neighbours():
    page = Paginator(range(100), 10).page(2)
    html = render("{% pagination page %}", "/x/?status=active&page=2", page=page)
    assert 'aria-label="Pagination"' in html
    assert "Page 2 of 10" in html
    assert 'href="?status=active&page=1"' in unescape(html)
    assert 'href="?status=active&page=3"' in unescape(html)
    assert 'id="page-prev"' in html
    assert 'id="page-next"' in html


def test_pagination_is_empty_for_a_single_page():
    page = Paginator(range(3), 10).page(1)
    assert render("{% pagination page %}", "/x/", page=page).strip() == ""


def test_sort_th_uses_the_views_default_sort_when_no_sort_param():
    html = render('{% sort_th "Name" "name" %}', "/x/", default_sort="name")
    assert 'aria-sort="ascending"' in html
    assert 'href="?sort=-name"' in html


def test_sort_th_explicit_sort_overrides_the_default():
    html = render('{% sort_th "Name" "name" %}', "/x/?sort=school", default_sort="name")
    assert "aria-sort" not in html
