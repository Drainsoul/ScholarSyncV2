import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "vercel.json").read_text())


def test_vercel_region_is_singapore():
    assert CONFIG["regions"] == ["sin1"]


def test_vercel_function_bundles_both_runtime_manifests():
    include = CONFIG["functions"]["config/wsgi.py"]["includeFiles"]
    assert "static/dist/.vite/manifest.json" in include
    assert "staticfiles/staticfiles.json" in include


def test_static_files_are_cached_immutably():
    rules = {rule["source"]: rule["headers"] for rule in CONFIG["headers"]}
    assert {"key": "Cache-Control", "value": "public, max-age=31536000, immutable"} in rules[
        "/static/(.*)"
    ]


def test_vercelignore_keeps_local_and_private_files_out_of_deploys():
    lines = (ROOT / ".vercelignore").read_text().split()
    for pattern in (
        ".env",
        ".env.*",
        ".venv/",
        "frontend/node_modules/",
        "staticfiles/",
        "static/dist/",
        "STATE.md",
        "CLAUDE.local.md",
        ".superpowers/",
        ".claude/",
        "docs/",
    ):
        assert pattern in lines, pattern
