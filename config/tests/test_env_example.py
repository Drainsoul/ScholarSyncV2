import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")


def _documented_names() -> set[str]:
    return set(re.findall(r"^([A-Z0-9_]+)=", EXAMPLE, flags=re.MULTILINE))


def test_every_setting_variable_is_documented():
    source = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    names = set(re.findall(r'env\.\w+\(\s*"([A-Z0-9_]+)"', source)) | {"SCHOLARSYNC_EXPLORE"}
    missing = sorted(names - _documented_names())
    assert not missing, f".env.example does not document: {missing}"


# The compose storage service's public key: production refuses it, so it is not a real secret.
EXPLORE_STORAGE_SECRET = "scholarsync-explore-secret"  # noqa: S105


def test_env_example_holds_no_real_secrets():
    for name in ("DJANGO_SECRET_KEY", "S3_SECRET_ACCESS_KEY", "EMAIL_URL"):
        for value in re.findall(rf"^{name}=(.*)$", EXAMPLE, flags=re.MULTILINE):
            assert value.strip() in {"", EXPLORE_STORAGE_SECRET} or "change-me" in value, (
                f"{name} looks like a real value"
            )
