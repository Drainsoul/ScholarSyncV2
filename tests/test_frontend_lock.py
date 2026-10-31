import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_npm_lockfile_includes_linux_native_binaries():
    """CI and the Docker build run on linux-x64. A lockfile written over an existing Windows
    node_modules can omit other platforms' optional packages, and then `npm ci` fails there."""
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text())
    packages = lock["packages"]
    for name in (
        "node_modules/@rolldown/binding-linux-x64-gnu",
        "node_modules/lightningcss-linux-x64-gnu",
    ):
        assert name in packages, name
