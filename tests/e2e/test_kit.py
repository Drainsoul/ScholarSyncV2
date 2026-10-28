import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

LOADED_FONTS = """async () => {
  await document.fonts.ready;
  return [...document.fonts]
    .filter((font) => font.status === "loaded")
    .map((font) => font.family.replaceAll('"', ""));
}"""


def test_kit_renders_under_an_enforced_csp(page: Page, live_server, vite_build, console_errors):
    response = page.goto(f"{live_server.url}/_kit/")
    assert response is not None
    assert response.ok
    assert "content-security-policy" in response.headers
    expect(page.get_by_role("heading", level=1)).to_have_text("Design kit")
    families = page.evaluate(LOADED_FONTS)
    assert "Inter" in families
    assert "Poppins" in families
    assert page.request.get(f"{live_server.url}/static/dist/icons.svg").ok
    assert console_errors == []
