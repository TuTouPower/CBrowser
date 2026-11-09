"""A25: compose binds only the credential files each service declares.

Static contract guard over the tracked compose.yaml template. Runtime
acceptance (per-role in-container readability, rotation, readiness) is
Docker-gated and recorded in the adoption evidence, not asserted here.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"
DEPLOY = ROOT / "scripts" / "deploy.sh"

SECRET_ROOT = "/run/secrets"
SERVICE_NAMES = ("api", "gateway", "supervisor")

INTERP_RE = re.compile(r"\$\{[^}]*\}")
ENV_FILE_RE = re.compile(r"^\s+CBROWSER_\w+_FILE:\s*/run/secrets/(\S+)\s*$")


def _strip_interpolation(value: str) -> str:
    return INTERP_RE.sub("VAR", value)


def _service_blocks(text: str) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    buf: list[str] = []
    in_services = False
    for line in text.splitlines():
        if re.match(r"^\S", line):
            if current is not None:
                blocks[current] = buf
                current, buf = None, []
            if line.strip() == "services:":
                in_services = True
            elif in_services:
                break
            continue
        if not in_services:
            continue
        match = re.match(r"^  (\w+):\s*$", line)
        if match:
            if current is not None:
                blocks[current] = buf
            current, buf = match.group(1), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        blocks[current] = buf
    return blocks


def _section(block: list[str], name: str) -> list[str]:
    out: list[str] = []
    active = False
    for line in block:
        if not line.strip():
            if active:
                out.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if active:
            if indent > 4:
                out.append(line)
            else:
                break
        elif indent == 4 and re.match(rf"^    {name}:\s*$", line):
            active = True
    return out


def _declared_secrets(block: list[str]) -> set[str]:
    names: set[str] = set()
    for line in _section(block, "environment"):
        match = ENV_FILE_RE.match(line)
        if match:
            names.add(match.group(1))
    return names


def _secret_mounts(block: list[str]) -> tuple[bool, set[str], list[str]]:
    entire = False
    files: set[str] = set()
    modes: list[str] = []
    for line in _section(block, "volumes"):
        text = line.strip()
        if not text.startswith("- "):
            continue
        parts = _strip_interpolation(text[2:].strip()).split(":")
        if len(parts) < 2:
            continue
        dst = parts[1]
        if dst.rstrip("/") != SECRET_ROOT and not dst.startswith(SECRET_ROOT + "/"):
            continue
        mode = parts[2] if len(parts) > 2 else ""
        modes.append(mode)
        if dst.rstrip("/") == SECRET_ROOT:
            entire = True
        else:
            files.add(dst[len(SECRET_ROOT) + 1:])
    return entire, files, modes


def test_no_service_mounts_entire_secrets_directory() -> None:
    blocks = _service_blocks(COMPOSE.read_text(encoding="utf-8"))
    offenders = [name for name in SERVICE_NAMES if _secret_mounts(blocks[name])[0]]
    assert not offenders, f"services still bind the whole secrets directory: {offenders}"


def test_each_service_mounts_exactly_its_declared_secrets() -> None:
    blocks = _service_blocks(COMPOSE.read_text(encoding="utf-8"))
    for name in SERVICE_NAMES:
        declared = _declared_secrets(blocks[name])
        assert declared, f"{name} declares no secret files"
        entire, files, modes = _secret_mounts(blocks[name])
        assert not entire, f"{name} binds the whole secrets directory"
        assert files == declared, (
            f"{name} mounts {sorted(files)} but declares {sorted(declared)}"
        )
        assert modes and all(mode == "ro" for mode in modes), (
            f"{name} secret mounts are not all read-only: {modes}"
        )


def test_foreign_secret_files_are_not_mounted() -> None:
    blocks = _service_blocks(COMPOSE.read_text(encoding="utf-8"))
    declared_by_service = {n: _declared_secrets(blocks[n]) for n in SERVICE_NAMES}
    all_declared = set().union(*declared_by_service.values())
    for name in SERVICE_NAMES:
        entire, files, _ = _secret_mounts(blocks[name])
        exposed = all_declared if entire else files
        foreign = exposed - declared_by_service[name]
        assert not foreign, f"{name} can read foreign secrets: {sorted(foreign)}"
    assert "admin_password" in declared_by_service["api"]
    assert "admin_password" not in declared_by_service["gateway"]
    assert "admin_password" not in declared_by_service["supervisor"]


def test_data_root_volumes_do_not_reintroduce_secrets() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    data_default = re.search(
        r'DATA_ROOT="\$\{CBROWSER_DATA_ROOT:-([^}]*)\}"', deploy
    )
    secrets_default = re.search(
        r'SECRETS_DIR="\$\{CBROWSER_SECRETS_DIR:-([^}]*)\}"', deploy
    )
    assert data_default and secrets_default
    data_path, secrets_path = data_default.group(1), secrets_default.group(1)
    assert not data_path.startswith(secrets_path.rstrip("/") + "/")
    assert not secrets_path.startswith(data_path.rstrip("/") + "/")

    blocks = _service_blocks(COMPOSE.read_text(encoding="utf-8"))
    for name in SERVICE_NAMES:
        for line in _section(blocks[name], "volumes"):
            text = line.strip()
            if "CBROWSER_DATA_ROOT" not in text:
                continue
            parts = _strip_interpolation(text.lstrip("- ").strip()).split(":")
            assert len(parts) >= 2
            assert not parts[1].startswith(SECRET_ROOT), (
                f"{name} data volume shadows the secret mount: {text}"
            )
