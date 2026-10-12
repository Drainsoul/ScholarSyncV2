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


def test_scrub_event_removes_frame_variables_and_breadcrumb_data():
    event = {
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "stacktrace": {
                        "frames": [
                            {"function": "save_profile", "vars": {"email": "juan@example.com"}},
                            {"function": "inner"},
                        ]
                    },
                }
            ]
        },
        "breadcrumbs": {
            "values": [
                {
                    "category": "query",
                    "message": "SELECT …",
                    "data": {"params": ["juan@example.com"]},
                },
                {"category": "log", "message": "saved"},
            ]
        },
    }
    scrubbed = scrub_event(event, {})
    frames = scrubbed["exception"]["values"][0]["stacktrace"]["frames"]
    assert all("vars" not in frame for frame in frames)
    assert [frame["function"] for frame in frames] == ["save_profile", "inner"]
    crumbs = scrubbed["breadcrumbs"]["values"]
    assert all("data" not in crumb for crumb in crumbs)
    assert [crumb["category"] for crumb in crumbs] == ["query", "log"]


def test_init_sentry_never_collects_locals_bodies_or_pii():
    import sentry_sdk

    from apps.core.sentry import init_sentry

    try:
        init_sentry(dsn="https://public@o0.ingest.sentry.io/0", environment="test", release=None)
        options = sentry_sdk.get_client().options
        collection = options["data_collection"]
        assert collection["user_info"] is False
        assert collection["cookies"] == {"mode": "off"}
        assert collection["http_bodies"] == []
        assert collection["url_query_params"] == {"mode": "off"}
        assert collection["database_query_data"] is False
        assert collection["stack_frame_variables"] is False
        assert collection["http_headers"]["request"]["mode"] == "allowlist"
        assert options["include_local_variables"] is False
        assert options["max_request_body_size"] == "never"
        assert options["before_send"] is scrub_event
    finally:
        sentry_sdk.init()  # reset to a disabled client so other tests never report
