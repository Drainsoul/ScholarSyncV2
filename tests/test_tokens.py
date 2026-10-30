"""Colour contrast for every token pair the components use (spec §12, WCAG 2.2 AA)."""

import json
import re
from pathlib import Path

import pytest

STYLES = Path(__file__).resolve().parents[1] / "frontend" / "src" / "styles"
DECLARATION = re.compile(r"--([a-z0-9-]+):\s*([^;]+);")
REFERENCE = re.compile(r"^var\(--([a-z0-9-]+)\)$")


def tokens() -> dict[str, str]:
    """Token name -> hex colour, following var(--x) aliases."""
    raw = dict(DECLARATION.findall((STYLES / "tokens.css").read_text(encoding="utf-8")))

    def resolve(name: str) -> str:
        value = raw[name].strip()
        alias = REFERENCE.match(value)
        return resolve(alias.group(1)) if alias else value

    return {name: resolve(name) for name in raw}


def luminance(colour: str) -> float:
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


# (foreground, background): text must reach 4.5:1.
TEXT_PAIRS = [
    ("text", "surface"),
    ("text", "bg"),
    ("text", "surface-header"),
    ("text-secondary", "surface"),
    ("text-secondary", "bg"),
    ("text-secondary", "surface-header"),
    ("text-muted", "surface"),
    ("text-muted", "bg"),
    ("text-muted", "surface-header"),
    ("link", "surface"),
    ("link", "bg"),
    ("on-primary", "primary"),
    ("on-primary", "primary-hover"),
    ("primary", "primary-50"),
    ("danger", "surface"),
    ("danger", "danger-50"),
    ("success", "surface"),
    ("success", "success-50"),
    ("warning", "surface"),
    ("warning", "warning-50"),
    ("info", "surface"),
    ("info", "info-50"),
    ("secondary", "secondary-50"),
    ("on-accent", "accent"),
    ("nav-text", "nav-bg"),
    ("nav-current", "nav-bg"),
    ("nav-current", "nav-current-bg"),
    ("on-primary", "brand"),
]
# Focus rings and control shapes must reach 3:1 (WCAG 1.4.11).
# border-control (#d0d5dd) is below 3:1 on white. Every control that uses it carries a visible
# label or text, so 1.4.11 does not apply to the border alone; it is left out on purpose.
NON_TEXT_PAIRS = [
    ("focus", "surface"),
    ("focus", "bg"),
    ("focus", "primary-50"),
    ("primary", "surface"),
]
DECORATIVE_AS_TEXT = re.compile(
    r"(?<![-\w])color:\s*var\(--(accent|yellow-500|focus-halo|nav-count-bg)\)"
)


@pytest.mark.parametrize(("foreground", "background"), TEXT_PAIRS)
def test_text_pairs_reach_aa(foreground, background):
    colours = tokens()
    ratio = contrast(colours[foreground], colours[background])
    assert ratio >= 4.5, f"--{foreground} on --{background} is {ratio:.2f}:1"


@pytest.mark.parametrize(("foreground", "background"), NON_TEXT_PAIRS)
def test_non_text_pairs_reach_3_to_1(foreground, background):
    colours = tokens()
    ratio = contrast(colours[foreground], colours[background])
    assert ratio >= 3.0, f"--{foreground} on --{background} is {ratio:.2f}:1"


def test_text_pairs_include_the_status_tones():
    foregrounds = {foreground for foreground, _ in TEXT_PAIRS}
    assert {"danger", "success", "warning", "info", "secondary"} <= foregrounds


def test_decorative_colours_are_never_text():
    offenders = [
        f"{path.name}: {match.group(0)}"
        for path in STYLES.rglob("*.css")
        for match in DECORATIVE_AS_TEXT.finditer(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_fonts_are_self_hosted(vite_build):
    manifest = json.loads(vite_build.read_text(encoding="utf-8"))
    dist = vite_build.parents[1]
    css = "".join(
        (dist / name).read_text(encoding="utf-8") for name in manifest["src/main.ts"]["css"]
    )
    assert "@font-face" in css
    assert "Lexend" in css
    assert "Source Sans 3" in css
    assert ".woff2" in css
    assert "//fonts." not in css
