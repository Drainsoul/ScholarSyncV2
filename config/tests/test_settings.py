import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


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
        ["CONTENT_SECURITY_POLICY_REPORT_ONLY"],
        S3_PUBLIC_ENDPOINT_URL="http://localhost:9000/",
    )
    directives = values["CONTENT_SECURITY_POLICY_REPORT_ONLY"]["DIRECTIVES"]
    assert "http://localhost:9000" in directives["img-src"]
    assert "http://localhost:9000" in directives["connect-src"]


def test_storage_origin_is_absent_from_csp_when_unset(tmp_path):
    values = settings_values(tmp_path, ["CONTENT_SECURITY_POLICY_REPORT_ONLY", "S3_STORAGE"])
    directives = values["CONTENT_SECURITY_POLICY_REPORT_ONLY"]["DIRECTIVES"]
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
    assert values["PRIVACY_NOTICE_VERSION"] == "2026-10-30"


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
