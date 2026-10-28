import pytest
from django.test import RequestFactory
from django.views import defaults


@pytest.mark.parametrize(
    ("view", "status", "heading"),
    [
        (
            lambda r: defaults.bad_request(r, Exception()),
            400,
            "Something was wrong with that request",
        ),
        (lambda r: defaults.permission_denied(r, Exception()), 403, "You can't open this page"),
        (lambda r: defaults.page_not_found(r, Exception()), 404, "Page not found"),
        (lambda r: defaults.server_error(r), 500, "Something went wrong on our side"),
    ],
)
def test_error_pages_use_the_public_layout(view, status, heading, vite_build):
    response = view(RequestFactory().get("/"))
    body = response.content.decode()
    assert response.status_code == status
    assert f"<h1>{heading}</h1>" in body
    assert '<main id="main"' in body


def test_unknown_url_renders_the_404_page(client, vite_build):
    response = client.get("/no-such-page/")
    assert response.status_code == 404
    assert "<h1>Page not found</h1>" in response.content.decode()
