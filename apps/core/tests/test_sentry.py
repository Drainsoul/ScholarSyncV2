from apps.core.sentry import scrub_event


def test_scrub_event_removes_request_and_user_pii():
    event = {
        "request": {
            "url": "https://scholarsync.example/me/profile/",
            "method": "POST",
            "data": {"full_name": "Juan Dela Cruz"},
            "cookies": {"sessionid": "abc"},
            "headers": {"Authorization": "Bearer t", "Cookie": "sessionid=abc", "User-Agent": "x"},
            "query_string": "email=juan@example.com",
        },
        "user": {"id": 42, "email": "juan@example.com", "username": "juan"},
        "message": "something broke",
    }
    scrubbed = scrub_event(event, {})
    request = scrubbed["request"]
    assert "data" not in request and "cookies" not in request and "query_string" not in request
    assert request["headers"] == {"User-Agent": "x"}
    assert scrubbed["user"] == {"id": 42}
    assert scrubbed["message"] == "something broke"


def test_scrub_event_tolerates_events_without_request_or_user():
    assert scrub_event({"message": "plain"}, {}) == {"message": "plain"}
