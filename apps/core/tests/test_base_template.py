import json
import re


def test_htmx_config_is_locked_down(client, vite_build):
    body = client.get("/").content.decode()
    match = re.search(r"<meta name=\"htmx-config\" content='([^']+)'>", body)
    assert match
    config = json.loads(match.group(1))
    assert config == {
        "allowEval": False,
        "allowScriptTags": False,
        "includeIndicatorStyles": False,
        "selfRequestsOnly": True,
        "historyCacheSize": 0,
        "refreshOnHistoryMiss": True,
    }


def test_body_sends_the_csrf_token_with_htmx_requests(client, vite_build):
    body = client.get("/").content.decode()
    match = re.search(r"<body hx-headers='([^']+)'>", body)
    assert match
    headers = json.loads(match.group(1))
    assert len(headers["X-CSRFToken"]) >= 32


def test_toast_region_and_template_exist(client, vite_build):
    body = client.get("/").content.decode()
    assert (
        '<div id="toasts" class="toasts" role="status" aria-live="polite" data-toast-region>'
        in body
    )
    assert '<template id="toast-template">' in body


def test_the_dialog_has_its_own_toast_region(client, vite_build):
    """A modal dialog makes the rest of the page inert, so toasts shown while it is open go here."""
    body = client.get("/").content.decode()
    dialog = re.search(r'<dialog id="app-dialog".*?</dialog>', body, re.DOTALL)
    assert dialog
    assert (
        '<div class="toasts" role="status" aria-live="polite" data-toast-region></div>'
        in dialog.group()
    )
