import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INLINE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>|\sstyle=|<style\b|\son[a-z]+=", re.IGNORECASE)


def test_templates_have_no_inline_script_or_style():
    offenders = [
        f"{path.relative_to(ROOT)}: {match.group(0).strip()}"
        for path in [*ROOT.glob("templates/**/*.html"), *ROOT.glob("apps/**/templates/**/*.html")]
        for match in INLINE.finditer(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
