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


def test_npm_lockfile_includes_linux_native_binaries():
    """Vercel and CI build on linux-x64. A lockfile written over an existing Windows
    node_modules can omit other platforms' optional packages, and then `npm ci` fails there."""
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text())
    packages = lock["packages"]
    for name in (
        "node_modules/@rolldown/binding-linux-x64-gnu",
        "node_modules/lightningcss-linux-x64-gnu",
    ):
        assert name in packages, name
