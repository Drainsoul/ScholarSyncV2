import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS = (".py", ".toml", ".yml", ".yaml", ".json", ".ts", ".html", ".cfg")
WORD = "ver" + "cel"  # spelled in two parts so this file does not match itself
SKIPPED = ("docs/", "frontend/package-lock.json")


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
        path = ROOT / name
        if path.is_file() and WORD in path.read_text(encoding="utf-8").lower():
            offenders.append(name)
    assert not offenders, offenders


def test_spike_leftovers_stay_git_ignored():
    """Until the M1 spike teardown (M3.5 Task 11), its local files must not be committable."""
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "." + WORD + "/" in lines
    assert ".env.spike" in lines
