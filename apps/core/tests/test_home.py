def test_home_renders_layout_with_hashed_assets(client, vite_build):
    response = client.get("/")
    body = response.content.decode()
    assert response.status_code == 200
    assert '<a class="skip-link" href="#main">' in body
    assert '<main id="main"' in body
    assert body.count("<h1") == 1
    assert '<script type="module"' in body
    assert "/static/dist/assets/main-" in body
    assert '<html lang="en">' in body
