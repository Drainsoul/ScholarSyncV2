from apps.accounts.tests.factories import UserFactory


def test_public_page_renders_layout_with_hashed_assets(client, vite_build):
    response = client.get("/about/")
    body = response.content.decode()
    assert response.status_code == 200
    assert '<a class="skip-link" href="#main">' in body
    assert '<main id="main"' in body
    assert body.count("<h1") == 1
    assert '<script type="module"' in body
    assert "/static/dist/assets/main-" in body
    assert '<html lang="en">' in body


def test_public_page_links_the_favicon(client, vite_build):
    body = client.get("/about/").content.decode()
    assert '<link rel="icon" href="/static/images/favicon.svg" type="image/svg+xml">' in body


def test_home_sends_a_signed_out_visitor_to_the_sign_in_page(client):
    response = client.get("/")
    assert response.status_code == 302 and response.url == "/accounts/login/"


def test_home_sends_a_signed_in_user_to_their_own_home(client, db):
    client.force_login(UserFactory.create(verified=True))
    response = client.get("/")
    assert response.status_code == 302 and response.url == "/me/"
