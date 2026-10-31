import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerignore_keeps_secrets_and_local_state_out():
    lines = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    required = {
        ".env",
        ".env.*",
        ".venv",
        "frontend/node_modules",
        "static/dist",
        "staticfiles",
        "STATE.md",
        "CLAUDE.local.md",
        ".git",
    }
    assert required <= lines, sorted(required - lines)


def test_entrypoint_is_lf_and_run_through_sh():
    assert b"\r" not in (ROOT / "docker" / "entrypoint.sh").read_bytes()
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]' in dockerfile


def test_every_compose_port_is_loopback_only():
    lines = (ROOT / "compose.yaml").read_text(encoding="utf-8").splitlines()
    ports: list[str] = []
    in_ports = False
    indent = 0
    for line in lines:
        stripped = line.strip()
        if stripped == "ports:":
            in_ports, indent = True, len(line) - len(line.lstrip())
            continue
        if in_ports:
            if stripped.startswith("- "):
                ports.append(stripped[2:].strip())
            elif (
                stripped
                and not stripped.startswith("#")
                and len(line) - len(line.lstrip()) <= indent
            ):
                in_ports = False
    assert ports, "compose.yaml publishes no ports"
    assert all(re.match(r'^"127\.0\.0\.1:', port) for port in ports), ports


def _service_block(path: str, name: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    match = re.search(rf"^  {name}:\n(.*?)(?=^  \S|^\S|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    assert match, f"{name} not found in {path}"
    return match.group(1)


def test_only_web_prepares_the_database():
    entrypoint = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")
    assert 'if [ "${SKIP_PREPARE:-0}" != "1" ]' in entrypoint
    assert entrypoint.index("SKIP_PREPARE") < entrypoint.index("manage.py prepare")
    for path in ("compose.yaml", "compose.production.yaml"):
        assert 'SKIP_PREPARE: "1"' in _service_block(path, "worker"), path
        assert "SKIP_PREPARE" not in _service_block(path, "web"), path


def test_production_compose_forces_a_safe_mode():
    text = (ROOT / "compose.production.yaml").read_text(encoding="utf-8")
    forced = re.search(r"^x-forced: &forced\n((?:  .*\n)+)", text, flags=re.MULTILINE)
    assert forced
    for line in ('DJANGO_DEBUG: "false"', 'SCHOLARSYNC_EXPLORE: "false"', 'DJANGO_KIT: "false"'):
        assert line in forced.group(1)
    for service in ("web", "worker"):
        assert "*forced" in _service_block("compose.production.yaml", service)
