"""Every icon a template names exists in the sprite (spec §12)."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "frontend" / "src" / "icons"
SPRITE = ROOT / "static" / "dist" / "icons.svg"
USES = [
    re.compile(r"""\{%\s*icon\s+["']([a-z0-9-]+)["']"""),  # {% icon "name" %}
    re.compile(r"""\bicon=["']([a-z0-9-]+)["']"""),  # {% include … with icon="name" %}
]


def known_icons() -> set[str]:
    names = set(json.loads((ICONS / "icons.json").read_text(encoding="utf-8")))
    return names | {path.stem for path in ICONS.glob("*.svg")}


def test_every_icon_named_in_templates_is_in_the_sprite_list():
    templates = [*ROOT.glob("templates/**/*.html"), *ROOT.glob("apps/**/templates/**/*.html")]
    used = {
        name: str(path.relative_to(ROOT))
        for path in templates
        for pattern in USES
        for name in pattern.findall(path.read_text(encoding="utf-8"))
    }
    assert {name: where for name, where in used.items() if name not in known_icons()} == {}


def test_sprite_has_one_symbol_per_icon(vite_build):
    ids = re.findall(r'<symbol id="([a-z0-9-]+)"', SPRITE.read_text(encoding="utf-8"))
    assert sorted(ids) == sorted(known_icons())
