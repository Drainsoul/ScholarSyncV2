import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS = (".py", ".toml", ".yml", ".yaml", ".json", ".ts", ".html", ".cfg")
WORD = "ver" + "cel"  # spelled in two parts so this file does not match itself
SKIPPED = ("docs/", "frontend/package-lock.json")
# Branch `demo` hosts the public demo there by design (hosted demo design, docs/design/):
# its own app folder and hosting files may name the host. Everything else still may not.
DEMO_PREFIX = "apps/demo/"
DEMO_HOSTING_FILES = {
    f"{WORD}.json",
    "api/index.py",
    "requirements.txt",
    ".github/workflows/demo.yml",
    f"scripts/{WORD}_build.sh",
}


def test_no_old_host_references_in_code():
    """The old host is no longer a deployment target; nothing tracked may refer to it."""
    tracked = subprocess.run(
        ["git", "ls-files"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    offenders = []
    for name in tracked:
        if not name.endswith(EXTENSIONS) or name.startswith(SKIPPED[0]) or name == SKIPPED[1]:
            continue
        if name.startswith(DEMO_PREFIX) or name in DEMO_HOSTING_FILES:
            continue
        path = ROOT / name
        if path.is_file() and WORD in path.read_text(encoding="utf-8").lower():
            offenders.append(name)
    assert not offenders, offenders
