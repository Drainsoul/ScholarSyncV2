import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("missing", ["DJANGO_SECRET_KEY", "DATABASE_URL"])
def test_settings_refuse_to_load_without_required_vars(missing, tmp_path):
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DJANGO_SECRET_KEY", "DATABASE_URL", "DJANGO_DEBUG"}
    }
    env.update(
        {
            "DJANGO_SECRET_KEY": "x" * 50,
            "DATABASE_URL": "postgres://u:p@localhost:5433/db",
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
            "DATABASE_URL": "postgres://u:p@localhost:5433/db",
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


def _kit_env(tmp_path, **extra):
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DJANGO_DEBUG", "DJANGO_KIT", "VERCEL_ENV"}
    }
    env.update(
        {
            "DJANGO_SECRET_KEY": "x" * 50,
            "DATABASE_URL": "postgres://u:p@localhost:5433/db",
            "DJANGO_ENV_FILE": str(tmp_path / "absent.env"),
            **extra,
        }
    )
    return env


def _kit_enabled(env):
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import config.settings as s; print(s.KIT_ENABLED)"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_kit_refuses_to_load_in_production(tmp_path):
    result = _kit_enabled(_kit_env(tmp_path, DJANGO_KIT="true", VERCEL_ENV="production"))
    assert result.returncode != 0
    assert "DJANGO_KIT" in result.stderr


def test_kit_is_off_by_default_and_allowed_on_previews(tmp_path):
    assert _kit_enabled(_kit_env(tmp_path)).stdout.strip() == "False"
    preview = _kit_enabled(_kit_env(tmp_path, DJANGO_KIT="true", VERCEL_ENV="preview"))
    assert preview.stdout.strip() == "True"
