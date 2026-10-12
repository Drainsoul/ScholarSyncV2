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
