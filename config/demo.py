"""Detect the optional demo app (spec 2026-10-30 section 5)."""

from pathlib import Path


def demo_installed(base_dir: Path) -> bool:
    """True only when the demo app's own module exists.

    A leftover folder (for example an untracked __pycache__ after deleting the tracked files)
    is not an app, so it must not count.
    """
    return (base_dir / "apps" / "demo" / "apps.py").is_file()
