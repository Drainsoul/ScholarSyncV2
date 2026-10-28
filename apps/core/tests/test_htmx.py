import json

from django.http import HttpResponse

from apps.core.htmx import close_dialog, toast


def test_toast_sets_an_hx_trigger_event():
    response = toast(HttpResponse(status=204), "Saved", "success")
    assert json.loads(response["HX-Trigger"]) == {"toast": {"message": "Saved", "tone": "success"}}


def test_toast_and_close_dialog_merge():
    response = close_dialog(toast(HttpResponse(status=204), "Released", "success"))
    assert json.loads(response["HX-Trigger"]) == {
        "toast": {"message": "Released", "tone": "success"},
        "closeDialog": {},
    }
