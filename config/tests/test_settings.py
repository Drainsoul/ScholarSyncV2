import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Production refuses to start without a real SMTP URL; nothing ever connects to this one.
SMTP_URL = "smtp://localhost:25"


@pytest.mark.parametrize(
    "missing", ["DJANGO_SECRET_KEY", "DATABASE_URL", "SITE_OPERATOR_NAME", "PRIVACY_CONTACT_EMAIL"]
)
def test_settings_refuse_to_load_without_required_vars(missing, tmp_path):
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DJANGO_SECRET_KEY", "DATABASE_URL", "DJANGO_DEBUG"}
    }
    env.update(
        {
            "DJANGO_SECRET_KEY": "x" * 50,
            "SITE_OPERATOR_NAME": "ScholarSync Test",
            "PRIVACY_CONTACT_EMAIL": "privacy@scholarsync.test",
            "DATABASE_URL": "postgres://u:p@localhost:5433/db",
            "DJANGO_ALLOWED_HOSTS": "scholarsync.example",
            "DJANGO_ENV_FILE": str(tmp_path / "absent.env"),
            "EMAIL_URL": SMTP_URL,
        }
    )
    del env[missing]
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import config.settings"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert missing in result.stderr


def test_debug_defaults_to_off_when_unset(tmp_path):
    env = {key: value for key, value in os.environ.items() if key != "DJANGO_DEBUG"}
    env.update(
        {
            "DJANGO_SECRET_KEY": "x" * 50,
            "SITE_OPERATOR_NAME": "ScholarSync Test",
            "PRIVACY_CONTACT_EMAIL": "privacy@scholarsync.test",
            "DATABASE_URL": "postgres://u:p@localhost:5433/db",
            "DJANGO_ALLOWED_HOSTS": "scholarsync.example",
            "DJANGO_ENV_FILE": str(tmp_path / "absent.env"),
            "EMAIL_URL": SMTP_URL,
        }
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import config.settings as s; print(s.DEBUG)"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


_MODE_VARS = {
    "DJANGO_DEBUG",
    "DJANGO_KIT",
    "SCHOLARSYNC_EXPLORE",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "DJANGO_SECRET_KEY",
    "CODESPACE_NAME",
    "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN",
    "APP_PORT",
    "SITE_OPERATOR_NAME",
    "PRIVACY_CONTACT_EMAIL",
    "EMAIL_URL",
}


def _run_settings(tmp_path, names, _unset=(), **extra):
    env = {key: value for key, value in os.environ.items() if key not in _MODE_VARS}
    env.update(
        {
            "DJANGO_SECRET_KEY": "x" * 50,
            "SITE_OPERATOR_NAME": "ScholarSync Test",
            "PRIVACY_CONTACT_EMAIL": "privacy@scholarsync.test",
            "DATABASE_URL": "postgres://u:p@localhost:5433/db",
            "DJANGO_ENV_FILE": str(tmp_path / "absent.env"),
            "EMAIL_URL": SMTP_URL,
            **extra,
        }
    )
    if "SCHOLARSYNC_EXPLORE" not in extra and "DJANGO_DEBUG" not in extra:
        # Production needs a real host; explore refuses any other than localhost.
        env.setdefault("DJANGO_ALLOWED_HOSTS", "scholarsync.example")
    for name in _unset:
        env.pop(name, None)
    code = (
        "import json, config.settings as s; "
        f"print(json.dumps({{n: getattr(s, n) for n in {list(names)!r}}}))"
    )
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def settings_values(tmp_path, names, **env):
    result = _run_settings(tmp_path, names, **env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_explore_mode_is_http_and_localhost_only(tmp_path):
    names = [
        "ALLOWED_HOSTS",
        "SECURE_SSL_REDIRECT",
        "SECURE_HSTS_SECONDS",
        "SESSION_COOKIE_SECURE",
        "CSRF_COOKIE_SECURE",
        "KIT_ENABLED",
        "PRODUCTION",
    ]
    values = settings_values(tmp_path, names, SCHOLARSYNC_EXPLORE="true")
    assert values["ALLOWED_HOSTS"] == ["localhost", "127.0.0.1"]
    assert values["SECURE_SSL_REDIRECT"] is False
    assert values["SECURE_HSTS_SECONDS"] == 0
    assert values["SESSION_COOKIE_SECURE"] is False
    assert values["CSRF_COOKIE_SECURE"] is False
    assert values["KIT_ENABLED"] is True
    assert values["PRODUCTION"] is False


def test_explore_mode_refuses_other_hosts(tmp_path):
    result = _run_settings(
        tmp_path,
        ["ALLOWED_HOSTS"],
        SCHOLARSYNC_EXPLORE="true",
        DJANGO_ALLOWED_HOSTS="scholarsync.example",
    )
    assert result.returncode != 0
    assert "SCHOLARSYNC_EXPLORE" in result.stderr


_CODESPACE = {
    "CODESPACE_NAME": "demo",
    "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev",
}


def test_explore_allows_the_codespaces_forwarded_host(tmp_path):
    values = settings_values(
        tmp_path,
        ["ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS"],
        SCHOLARSYNC_EXPLORE="true",
        **_CODESPACE,
    )
    assert values["ALLOWED_HOSTS"][-1] == "demo-8000.app.github.dev"
    assert values["ALLOWED_HOSTS"][:2] == ["localhost", "127.0.0.1"]
    assert "https://demo-8000.app.github.dev" in values["CSRF_TRUSTED_ORIGINS"]


def test_codespaces_forwarded_host_follows_app_port(tmp_path):
    values = settings_values(
        tmp_path, ["ALLOWED_HOSTS"], SCHOLARSYNC_EXPLORE="true", APP_PORT="8010", **_CODESPACE
    )
    assert values["ALLOWED_HOSTS"][-1] == "demo-8010.app.github.dev"


def test_codespaces_variables_are_ignored_outside_explore(tmp_path):
    values = settings_values(
        tmp_path,
        ["ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS"],
        DJANGO_ALLOWED_HOSTS="scholarsync.example",
        **_CODESPACE,
    )
    assert values["ALLOWED_HOSTS"] == ["scholarsync.example"]
    assert values["CSRF_TRUSTED_ORIGINS"] == []


def test_explore_ignores_empty_codespaces_variables(tmp_path):
    values = settings_values(
        tmp_path,
        ["ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS"],
        SCHOLARSYNC_EXPLORE="true",
        CODESPACE_NAME="",
        GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN="",
    )
    assert values["ALLOWED_HOSTS"] == ["localhost", "127.0.0.1"]
    assert values["CSRF_TRUSTED_ORIGINS"] == []


def test_codespaces_refuses_the_public_explore_key(tmp_path):
    result = _run_settings(
        tmp_path,
        ["SECRET_KEY"],
        SCHOLARSYNC_EXPLORE="true",
        DJANGO_SECRET_KEY="explore-only-" + "x" * 40,
        **_CODESPACE,
    )
    assert result.returncode != 0
    assert "devcontainer" in result.stderr
    assert "docs/SETUP.md" in result.stderr


def test_codespaces_accepts_a_generated_key(tmp_path):
    values = settings_values(
        tmp_path,
        ["SECRET_KEY"],
        SCHOLARSYNC_EXPLORE="true",
        DJANGO_SECRET_KEY="codespace-" + "a" * 64,
        **_CODESPACE,
    )
    assert values["SECRET_KEY"].startswith("codespace-")


def test_explore_key_still_works_on_localhost(tmp_path):
    values = settings_values(
        tmp_path,
        ["SECRET_KEY"],
        SCHOLARSYNC_EXPLORE="true",
        DJANGO_SECRET_KEY="explore-only-" + "x" * 40,
    )
    assert values["SECRET_KEY"].startswith("explore-only-")


def test_codespaces_does_not_widen_the_explore_refusal(tmp_path):
    result = _run_settings(
        tmp_path,
        ["ALLOWED_HOSTS"],
        SCHOLARSYNC_EXPLORE="true",
        DJANGO_ALLOWED_HOSTS="demo-8000.app.github.dev",
        **_CODESPACE,
    )
    assert result.returncode != 0


def test_production_is_the_default_and_https_only(tmp_path):
    names = ["PRODUCTION", "SECURE_SSL_REDIRECT", "SECURE_HSTS_SECONDS", "SESSION_COOKIE_SECURE"]
    values = settings_values(tmp_path, names)
    assert values["PRODUCTION"] is True
    assert values["SECURE_SSL_REDIRECT"] is True
    assert values["SECURE_HSTS_SECONDS"] == 31_536_000
    assert values["SESSION_COOKIE_SECURE"] is True


def test_kit_refuses_to_load_in_production(tmp_path):
    result = _run_settings(tmp_path, ["KIT_ENABLED"], DJANGO_KIT="true")
    assert result.returncode != 0
    assert "DJANGO_KIT" in result.stderr


def test_kit_is_off_by_default_in_production(tmp_path):
    assert settings_values(tmp_path, ["KIT_ENABLED"])["KIT_ENABLED"] is False


@pytest.mark.parametrize("mode", [{"SCHOLARSYNC_EXPLORE": "true"}, {"DJANGO_DEBUG": "true"}])
def test_kit_allowed_in_explore_and_developer_modes(tmp_path, mode):
    values = settings_values(tmp_path, ["KIT_ENABLED"], DJANGO_KIT="true", **mode)
    assert values["KIT_ENABLED"] is True


def test_production_refuses_the_explore_secret_key(tmp_path):
    key = "explore-only-" + "x" * 40
    result = _run_settings(tmp_path, ["SECRET_KEY"], DJANGO_SECRET_KEY=key)
    assert result.returncode != 0
    assert "explore" in result.stderr
    explore = _run_settings(
        tmp_path, ["SECRET_KEY"], DJANGO_SECRET_KEY=key, SCHOLARSYNC_EXPLORE="true"
    )
    assert explore.returncode == 0, explore.stderr


def test_production_refuses_the_explore_storage_secret(tmp_path):
    secret = "scholarsync-explore-secret"
    result = _run_settings(tmp_path, ["S3_STORAGE"], S3_SECRET_ACCESS_KEY=secret)
    assert result.returncode != 0
    assert "public explore storage key" in result.stderr
    assert "docs/HOSTING.md" in result.stderr
    explore = _run_settings(
        tmp_path, ["S3_STORAGE"], S3_SECRET_ACCESS_KEY=secret, SCHOLARSYNC_EXPLORE="true"
    )
    assert explore.returncode == 0, explore.stderr
    developer = _run_settings(
        tmp_path, ["S3_STORAGE"], S3_SECRET_ACCESS_KEY=secret, DJANGO_DEBUG="true"
    )
    assert developer.returncode == 0, developer.stderr
    own = _run_settings(tmp_path, ["S3_STORAGE"], S3_SECRET_ACCESS_KEY="a-real-secret")
    assert own.returncode == 0, own.stderr


def test_pytest_settings_survive_the_explore_storage_secret_in_env():
    env = {**os.environ, "S3_SECRET_ACCESS_KEY": "scholarsync-explore-secret"}
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import config.test_settings"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_csrf_trusted_origins_from_env(tmp_path):
    values = settings_values(
        tmp_path,
        ["CSRF_TRUSTED_ORIGINS"],
        DJANGO_CSRF_TRUSTED_ORIGINS="https://a.example,https://b.example",
    )
    assert values["CSRF_TRUSTED_ORIGINS"] == ["https://a.example", "https://b.example"]


def test_demo_detection_needs_the_apps_module(tmp_path):
    from config.demo import demo_installed

    assert demo_installed(tmp_path) is False
    (tmp_path / "apps" / "demo" / "__pycache__").mkdir(parents=True)
    assert demo_installed(tmp_path) is False  # leftover folder only
    (tmp_path / "apps" / "demo" / "apps.py").write_text("", encoding="utf-8")
    assert demo_installed(tmp_path) is True


def test_csp_allows_the_storage_origin(tmp_path):
    values = settings_values(
        tmp_path,
        ["CONTENT_SECURITY_POLICY"],
        S3_PUBLIC_ENDPOINT_URL="http://localhost:9000/",
    )
    directives = values["CONTENT_SECURITY_POLICY"]["DIRECTIVES"]
    assert "http://localhost:9000" in directives["img-src"]
    assert "http://localhost:9000" in directives["connect-src"]


def test_csp_allows_the_bucket_subdomain_with_virtual_addressing(tmp_path):
    values = settings_values(
        tmp_path,
        ["CONTENT_SECURITY_POLICY"],
        S3_ENDPOINT_URL="https://s3.ap-southeast-1.amazonaws.com",
        S3_BUCKET="scholars",
        S3_ADDRESSING_STYLE="virtual",
    )
    directives = values["CONTENT_SECURITY_POLICY"]["DIRECTIVES"]
    origin = "https://scholars.s3.ap-southeast-1.amazonaws.com"
    assert origin in directives["img-src"]
    assert origin in directives["connect-src"]
    assert "https://s3.ap-southeast-1.amazonaws.com" not in directives["connect-src"]


def test_csp_virtual_addressing_follows_the_public_endpoint(tmp_path):
    values = settings_values(
        tmp_path,
        ["CONTENT_SECURITY_POLICY"],
        S3_ENDPOINT_URL="http://storage:9000",
        S3_PUBLIC_ENDPOINT_URL="http://localhost:9000",
        S3_BUCKET="b",
        S3_ADDRESSING_STYLE="virtual",
    )
    directives = values["CONTENT_SECURITY_POLICY"]["DIRECTIVES"]
    assert directives["connect-src"] == ["'self'", "http://b.localhost:9000"]


def test_csp_path_addressing_keeps_the_endpoint_origin(tmp_path):
    values = settings_values(
        tmp_path,
        ["CONTENT_SECURITY_POLICY"],
        S3_ENDPOINT_URL="https://acct.r2.cloudflarestorage.com",
        S3_BUCKET="scholars",
        S3_ADDRESSING_STYLE="path",
    )
    directives = values["CONTENT_SECURITY_POLICY"]["DIRECTIVES"]
    assert directives["connect-src"] == ["'self'", "https://acct.r2.cloudflarestorage.com"]


def test_storage_origin_is_absent_from_csp_when_unset(tmp_path):
    values = settings_values(tmp_path, ["CONTENT_SECURITY_POLICY", "S3_STORAGE"])
    directives = values["CONTENT_SECURITY_POLICY"]["DIRECTIVES"]
    assert directives["connect-src"] == ["'self'"]
    assert values["S3_STORAGE"]["addressing_style"] == "path"


def test_email_url_configures_smtp(tmp_path):
    values = settings_values(
        tmp_path,
        ["EMAIL_BACKEND", "EMAIL_HOST", "EMAIL_PORT"],
        EMAIL_URL="smtp://mail:1025",
    )
    assert values["EMAIL_BACKEND"] == "django.core.mail.backends.smtp.EmailBackend"
    assert values["EMAIL_HOST"] == "mail"
    assert values["EMAIL_PORT"] == 1025


def test_production_refuses_the_env_example_placeholder_key(tmp_path):
    result = _run_settings(tmp_path, ["SECRET_KEY"], DJANGO_SECRET_KEY="local-dev-only-change-me-1")
    assert result.returncode != 0
    assert "docs/HOSTING.md" in result.stderr
    ok = _run_settings(
        tmp_path, ["SECRET_KEY"], DJANGO_SECRET_KEY="local-dev-only-x", DJANGO_DEBUG="true"
    )
    assert ok.returncode == 0, ok.stderr


def test_operator_settings_default_outside_production(tmp_path):
    values = settings_values(
        tmp_path,
        ["SITE_OPERATOR_NAME", "PRIVACY_CONTACT_EMAIL", "PRIVACY_NOTICE_VERSION"],
        SCHOLARSYNC_EXPLORE="true",
        _unset=["SITE_OPERATOR_NAME", "PRIVACY_CONTACT_EMAIL"],
    )
    assert values["SITE_OPERATOR_NAME"] == "This local copy"
    assert values["PRIVACY_CONTACT_EMAIL"] == ""
    assert values["PRIVACY_NOTICE_VERSION"] == "2026-11-19"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SITE_OPERATOR_NAME", ""),
        ("SITE_OPERATOR_NAME", "   "),
        ("SITE_OPERATOR_NAME", "Example Organisation CHANGE-ME"),
        ("PRIVACY_CONTACT_EMAIL", ""),
        ("PRIVACY_CONTACT_EMAIL", "change-me@scholarsync.test"),
        ("PRIVACY_CONTACT_EMAIL", "privacy@example.org"),
        ("PRIVACY_CONTACT_EMAIL", "privacy@example.com"),
        ("PRIVACY_CONTACT_EMAIL", "privacy@mail.example.net"),
        ("PRIVACY_CONTACT_EMAIL", "privacy@example.ph"),
    ],
)
def test_production_refuses_placeholder_operator_settings(tmp_path, name, value):
    result = _run_settings(tmp_path, [name], **{name: value})
    assert result.returncode != 0
    assert name in result.stderr
    assert "docs/HOSTING.md" in result.stderr


def test_production_accepts_real_operator_settings(tmp_path):
    values = settings_values(
        tmp_path,
        ["SITE_OPERATOR_NAME", "PRIVACY_CONTACT_EMAIL"],
        SITE_OPERATOR_NAME="Barangay Scholars Office",
        PRIVACY_CONTACT_EMAIL="dpo@scholarsync.test",
    )
    assert values["PRIVACY_CONTACT_EMAIL"] == "dpo@scholarsync.test"


def test_env_example_placeholders_fail_the_production_guard(tmp_path):
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    pairs = dict(
        re.findall(r"^(SITE_OPERATOR_NAME|PRIVACY_CONTACT_EMAIL)=(.*)$", example, re.MULTILINE)
    )
    for name, value in pairs.items():
        assert _run_settings(tmp_path, [name], **{name: value}).returncode != 0, name


@pytest.mark.parametrize(
    "hosts", ["", " , ", "*", "scholarsync.example,*", ".scholarsync.example, *"]
)
def test_production_refuses_empty_or_wildcard_allowed_hosts(tmp_path, hosts):
    result = _run_settings(tmp_path, ["ALLOWED_HOSTS"], DJANGO_ALLOWED_HOSTS=hosts)
    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr
    assert "docs/HOSTING.md" in result.stderr


def test_production_refuses_unset_allowed_hosts(tmp_path):
    result = _run_settings(tmp_path, ["ALLOWED_HOSTS"], _unset=["DJANGO_ALLOWED_HOSTS"])
    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr


def test_developer_mode_allows_empty_allowed_hosts(tmp_path):
    values = settings_values(
        tmp_path, ["ALLOWED_HOSTS"], DJANGO_DEBUG="true", DJANGO_ALLOWED_HOSTS=""
    )
    assert values["ALLOWED_HOSTS"] == []


def test_explore_ignores_csrf_trusted_origins_from_env(tmp_path):
    values = settings_values(
        tmp_path,
        ["CSRF_TRUSTED_ORIGINS"],
        SCHOLARSYNC_EXPLORE="true",
        DJANGO_CSRF_TRUSTED_ORIGINS="https://evil.example",
    )
    assert values["CSRF_TRUSTED_ORIGINS"] == []


def test_explore_trusts_only_the_codespaces_origin(tmp_path):
    values = settings_values(
        tmp_path,
        ["CSRF_TRUSTED_ORIGINS"],
        SCHOLARSYNC_EXPLORE="true",
        DJANGO_CSRF_TRUSTED_ORIGINS="https://evil.example",
        DJANGO_SECRET_KEY="codespace-" + "a" * 64,
        **_CODESPACE,
    )
    assert values["CSRF_TRUSTED_ORIGINS"] == ["https://demo-8000.app.github.dev"]


@pytest.mark.parametrize(
    ("mode", "value", "expected"),
    [
        ({}, "", "production"),
        ({"SCHOLARSYNC_EXPLORE": "true"}, "", "local"),
        ({}, "staging", "staging"),
    ],
)
def test_blank_sentry_environment_uses_the_mode_default(tmp_path, mode, value, expected):
    env = {key: v for key, v in os.environ.items() if key not in _MODE_VARS}
    env.update(
        {
            "DJANGO_SECRET_KEY": "x" * 50,
            "SITE_OPERATOR_NAME": "ScholarSync Test",
            "PRIVACY_CONTACT_EMAIL": "privacy@scholarsync.test",
            "DATABASE_URL": "postgres://u:p@localhost:5433/db",
            "DJANGO_ENV_FILE": str(tmp_path / "absent.env"),
            "EMAIL_URL": SMTP_URL,
            "SENTRY_DSN": "https://key@sentry.io/1",
            "SENTRY_ENVIRONMENT": value,
            **mode,
        }
    )
    if not mode:
        env["DJANGO_ALLOWED_HOSTS"] = "scholarsync.example"
    code = (
        "import apps.core.sentry as m; "
        "m.init_sentry = lambda **kw: print(kw['environment']); "
        "import config.settings"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


@pytest.mark.parametrize(
    "value", ["", "   ", "console://", "memory://", "dummy://", "file:///tmp/mail"]
)
def test_production_refuses_an_email_url_that_never_delivers(tmp_path, value):
    result = _run_settings(tmp_path, ["EMAIL_BACKEND"], EMAIL_URL=value)
    assert result.returncode != 0
    assert "EMAIL_URL" in result.stderr
    assert "docs/HOSTING.md" in result.stderr


def test_production_refuses_an_unset_email_url(tmp_path):
    result = _run_settings(tmp_path, ["EMAIL_BACKEND"], _unset=["EMAIL_URL"])
    assert result.returncode != 0
    assert "EMAIL_URL" in result.stderr


@pytest.mark.parametrize("mode", [{"SCHOLARSYNC_EXPLORE": "true"}, {"DJANGO_DEBUG": "true"}])
def test_blank_email_url_prints_to_the_console_outside_production(tmp_path, mode):
    values = settings_values(tmp_path, ["EMAIL_BACKEND"], EMAIL_URL="", **mode)
    assert values["EMAIL_BACKEND"] == "django.core.mail.backends.console.EmailBackend"


@pytest.mark.parametrize(("value", "expected"), [("", 0), ("  ", 0), ("2", 2)])
def test_trusted_proxy_count_treats_blank_as_the_default(tmp_path, value, expected):
    values = settings_values(tmp_path, ["ALLAUTH_TRUSTED_PROXY_COUNT"], TRUSTED_PROXY_COUNT=value)
    assert values["ALLAUTH_TRUSTED_PROXY_COUNT"] == expected


# environs keeps values read from the .env file out of os.environ, so the settings must treat a
# value there exactly like the same value in the process environment.
def _env_file(tmp_path, text):
    path = tmp_path / "local.env"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_blank_email_url_in_the_env_file_prints_to_the_console(tmp_path):
    values = settings_values(
        tmp_path,
        ["EMAIL_BACKEND"],
        DJANGO_DEBUG="true",
        DJANGO_ENV_FILE=_env_file(tmp_path, "EMAIL_URL=\n"),
        _unset=["EMAIL_URL"],
    )
    assert values["EMAIL_BACKEND"] == "django.core.mail.backends.console.EmailBackend"


def test_blank_email_url_in_the_env_file_is_refused_in_production(tmp_path):
    result = _run_settings(
        tmp_path,
        ["EMAIL_BACKEND"],
        DJANGO_ENV_FILE=_env_file(tmp_path, "EMAIL_URL=\n"),
        _unset=["EMAIL_URL"],
    )
    assert result.returncode != 0
    assert "EMAIL_URL is blank" in result.stderr


def test_blank_trusted_proxy_count_in_the_env_file_is_the_default(tmp_path):
    values = settings_values(
        tmp_path,
        ["ALLAUTH_TRUSTED_PROXY_COUNT"],
        DJANGO_ENV_FILE=_env_file(tmp_path, "TRUSTED_PROXY_COUNT=\n"),
        _unset=["TRUSTED_PROXY_COUNT"],
    )
    assert values["ALLAUTH_TRUSTED_PROXY_COUNT"] == 0


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("DATABASE_URL=postgres://u:p@db.example.org:5432/db", "DATABASE_URL connects to"),
        ("EMAIL_URL=smtp://mail.example.org:25", "EMAIL_URL sends mail to mail.example.org"),
    ],
)
def test_production_checks_plaintext_urls_from_the_env_file(tmp_path, line, message):
    name = line.split("=", 1)[0]
    result = _run_settings(
        tmp_path, ["DEBUG"], DJANGO_ENV_FILE=_env_file(tmp_path, line + "\n"), _unset=[name]
    )
    assert result.returncode != 0
    assert message in result.stderr


def test_developer_settings_load_from_a_copy_of_the_env_example(tmp_path):
    """The documented setup: `cp .env.example .env`, then migrate and runserver."""
    values = settings_values(
        tmp_path,
        ["DEBUG", "EMAIL_BACKEND", "ALLAUTH_TRUSTED_PROXY_COUNT"],
        DJANGO_ENV_FILE=str(ROOT / ".env.example"),
        _unset=["DJANGO_SECRET_KEY", "SITE_OPERATOR_NAME", "PRIVACY_CONTACT_EMAIL", "EMAIL_URL"],
    )
    assert values == {
        "DEBUG": True,
        "EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend",
        "ALLAUTH_TRUSTED_PROXY_COUNT": 0,
    }


def test_test_settings_load_with_a_copy_of_the_env_example():
    """pytest forces production mode; a developer's .env from .env.example must not break it."""
    env = {key: value for key, value in os.environ.items() if key not in _MODE_VARS}
    env.pop("DATABASE_URL", None)
    env["DJANGO_ENV_FILE"] = str(ROOT / ".env.example")
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import config.test_settings as s; print(s.KIT_ENABLED)"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_production_refuses_a_wildcard_first_host_without_site_url(tmp_path):
    result = _run_settings(
        tmp_path, ["SITE_URL"], DJANGO_ALLOWED_HOSTS=".scholarsync.example", SITE_URL=""
    )
    assert result.returncode != 0
    assert "SITE_URL" in result.stderr
    assert "docs/HOSTING.md" in result.stderr


def test_production_accepts_a_wildcard_first_host_with_site_url(tmp_path):
    values = settings_values(
        tmp_path,
        ["SITE_URL"],
        DJANGO_ALLOWED_HOSTS=".scholarsync.example",
        SITE_URL="https://scholarsync.example/",
    )
    assert values["SITE_URL"] == "https://scholarsync.example"


def test_production_refuses_a_non_https_site_url(tmp_path):
    result = _run_settings(tmp_path, ["SITE_URL"], SITE_URL="http://scholarsync.example")
    assert result.returncode != 0
    assert "SITE_URL" in result.stderr


def test_site_url_defaults_to_the_first_host_in_production(tmp_path):
    values = settings_values(tmp_path, ["SITE_URL"])
    assert values["SITE_URL"] == "https://scholarsync.example"


def test_developer_mode_allows_an_http_site_url(tmp_path):
    values = settings_values(
        tmp_path, ["SITE_URL"], DJANGO_DEBUG="true", SITE_URL="http://127.0.0.1:8000"
    )
    assert values["SITE_URL"] == "http://127.0.0.1:8000"


CSP_NAMES = ["CONTENT_SECURITY_POLICY", "CONTENT_SECURITY_POLICY_REPORT_ONLY"]
CSP_UNSET = ["CSP_REPORT_ONLY", "VITE_DEV_MODE"]


def test_csp_is_enforced_by_default(tmp_path):
    values = settings_values(tmp_path, CSP_NAMES, _unset=CSP_UNSET)
    assert values["CONTENT_SECURITY_POLICY"] is not None
    assert values["CONTENT_SECURITY_POLICY_REPORT_ONLY"] is None


def test_csp_is_report_only_with_the_vite_dev_server(tmp_path):
    values = settings_values(
        tmp_path, CSP_NAMES, _unset=["CSP_REPORT_ONLY"], DJANGO_DEBUG="true", VITE_DEV_MODE="true"
    )
    assert values["CONTENT_SECURITY_POLICY"] is None
    assert values["CONTENT_SECURITY_POLICY_REPORT_ONLY"] is not None


def test_csp_report_only_can_be_asked_for_while_debugging(tmp_path):
    values = settings_values(tmp_path, CSP_NAMES, _unset=["VITE_DEV_MODE"], CSP_REPORT_ONLY="true")
    assert values["CONTENT_SECURITY_POLICY"] is None
    assert values["CONTENT_SECURITY_POLICY_REPORT_ONLY"] is not None


def test_csp_lets_forms_reach_google_when_google_sign_in_is_on(tmp_path):
    """The Google button posts to /accounts/google/login/, which redirects to Google: browsers
    apply form-action to that redirect."""
    values = settings_values(
        tmp_path, ["CONTENT_SECURITY_POLICY"], GOOGLE_CLIENT_ID="id", GOOGLE_CLIENT_SECRET="x"
    )
    assert (
        "https://accounts.google.com"
        in values["CONTENT_SECURITY_POLICY"]["DIRECTIVES"]["form-action"]
    )
    off = settings_values(tmp_path, ["CONTENT_SECURITY_POLICY"], _unset=["GOOGLE_CLIENT_ID"])
    assert off["CONTENT_SECURITY_POLICY"]["DIRECTIVES"]["form-action"] == ["'self'"]


def test_vite_dev_mode_is_report_only_even_with_the_example_line(tmp_path):
    """A .env copied from .env.example must not undo the Vite dev server's report-only CSP."""
    values = settings_values(
        tmp_path, CSP_NAMES, DJANGO_DEBUG="true", VITE_DEV_MODE="true", CSP_REPORT_ONLY="false"
    )
    assert values["CONTENT_SECURITY_POLICY"] is None
    assert values["CONTENT_SECURITY_POLICY_REPORT_ONLY"] is not None


def _refused(tmp_path, **env):
    result = _run_settings(tmp_path, ["DEBUG"], **env)
    return result.returncode != 0, result.stderr


def test_production_refuses_plaintext_smtp_to_another_host(tmp_path):
    refused, stderr = _refused(tmp_path, EMAIL_URL="smtp://mail.example.org:25")
    assert refused
    assert "EMAIL_URL sends mail to mail.example.org unencrypted" in stderr
    assert "ALLOW_PLAINTEXT_SERVICES" in stderr


@pytest.mark.parametrize(
    "url",
    [
        "submission://u:p@smtp.example.org:587",
        "smtp://u:p@smtp.example.org:587?tls=true",
        "smtp://u:p@smtp.example.org:465?ssl=true",
    ],
)
def test_production_accepts_encrypted_smtp_to_another_host(tmp_path, url):
    refused, stderr = _refused(tmp_path, EMAIL_URL=url)
    assert not refused, stderr


def test_unknown_email_scheme_is_refused_with_a_sentence(tmp_path):
    # smtp+tls:// was once in the docs; dj-email-url doesn't know it and returned no backend.
    refused, stderr = _refused(tmp_path, EMAIL_URL="smtp+tls://u:p@smtp.example.org:587")
    assert refused
    assert "EMAIL_URL's scheme isn't recognised" in stderr
    assert "KeyError" not in stderr


def test_production_refuses_http_storage_to_another_host(tmp_path):
    refused, stderr = _refused(tmp_path, S3_ENDPOINT_URL="http://files.example.org:9000")
    assert refused
    assert "S3_ENDPOINT_URL uses http://" in stderr


def test_production_refuses_database_without_tls_to_another_host(tmp_path):
    refused, stderr = _refused(tmp_path, DATABASE_URL="postgres://u:p@db.example.org:5432/x")
    assert refused
    assert "DATABASE_URL" in stderr and "sslmode" in stderr
    ok, _ = _refused(
        tmp_path, DATABASE_URL="postgres://u:p@db.example.org:5432/x?sslmode=verify-full"
    )
    assert not ok


def test_production_refuses_clamd_on_another_host(tmp_path):
    refused, stderr = _refused(tmp_path, CLAMAV_HOST="clamd.example.org")
    assert refused
    assert "CLAMAV_HOST is clamd.example.org" in stderr
    ok, stderr = _refused(tmp_path, CLAMAV_HOST="clamav")
    assert not ok, stderr


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "db", "host.docker.internal"])
def test_plaintext_allowed_for_loopback_and_service_names(tmp_path, host):
    refused, stderr = _refused(
        tmp_path,
        EMAIL_URL=f"smtp://{host}:25",
        S3_ENDPOINT_URL=f"http://{host}:9000",
        DATABASE_URL=f"postgres://u:p@{host}:5432/x",
    )
    assert not refused, stderr


def test_allow_plaintext_services_opts_out(tmp_path):
    refused, stderr = _refused(
        tmp_path, EMAIL_URL="smtp://mail.internal.example:25", ALLOW_PLAINTEXT_SERVICES="true"
    )
    assert not refused, stderr


def test_numeric_validator_removed(tmp_path):
    values = settings_values(tmp_path, ["AUTH_PASSWORD_VALIDATORS"])
    names = [item["NAME"] for item in values["AUTH_PASSWORD_VALIDATORS"]]
    assert "django.contrib.auth.password_validation.NumericPasswordValidator" not in names
