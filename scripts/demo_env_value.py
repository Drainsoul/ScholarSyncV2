"""Print one value from the settings file the host's CLI pulls (branch `demo`, docs/hosted-demo.md).

Usage: python scripts/demo_env_value.py NAME FILE

The deploy job reads only the direct database URL this way, instead of sourcing the whole file into
the shell: nothing else is exported, and a `$`, backtick or backslash in a value stays literal.
A missing or empty value (a variable marked Sensitive comes back empty) fails with a message.
"""

import json
import sys
from pathlib import Path


def value(name: str, text: str) -> str:
    for line in text.splitlines():
        key, sep, raw = line.partition("=")
        if not sep or key.strip() != name:
            continue
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] == '"':
            # Written JSON-style: "..." with backslash escapes.
            return str(json.loads(raw))
        if len(raw) >= 2 and raw[0] == raw[-1] == "'":
            return raw[1:-1]
        return raw
    return ""


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    name, path = argv[1], Path(argv[2])
    found = value(name, path.read_text(encoding="utf-8"))
    if not found:
        print(
            f"{name} is missing or empty in {path.name} (is it marked Sensitive?).", file=sys.stderr
        )
        return 1
    sys.stdout.write(found)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
