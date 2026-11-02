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


def test_explore_compose_takes_a_per_codespace_key():
    block = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert 'DJANGO_SECRET_KEY: "${EXPLORE_SECRET_KEY:-explore-only-' in block


def test_devcontainer_generates_a_key_and_keeps_ports_private():
    import json

    config = json.loads((ROOT / ".devcontainer" / "devcontainer.json").read_text(encoding="utf-8"))
    assert "explore-key.sh" in config["postCreateCommand"]
    start = config["postStartCommand"]
    assert start.index("explore-key.sh") < start.index("docker compose")
    assert "--env-file .devcontainer/explore.env" in start
    for port in ("8000", "8025"):
        assert config["portsAttributes"][port]["visibility"] == "private"
    assert config["otherPortsAttributes"] == {"onAutoForward": "ignore"}
    assert b"\r" not in (ROOT / ".devcontainer" / "explore-key.sh").read_bytes()
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".devcontainer/explore.env" in ignored


def test_production_web_is_published_on_loopback_by_default():
    block = _service_block("compose.production.yaml", "web")
    assert '- "127.0.0.1:${APP_PORT:-8000}:8000"' in block
    assert "ports:" not in _service_block("compose.production.yaml", "worker")


def test_dockerfile_sets_ownership_without_a_recursive_chown():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "chown -R" not in dockerfile
    assert "COPY --chown=scholarsync . ." in dockerfile
    assert dockerfile.index("useradd") < dockerfile.index("COPY --chown=scholarsync")
    assert "USER scholarsync" in dockerfile
