"""t054: the deploy-time network CLI renders the Caddyfile from the port.

deploy.sh calls exactly one subcommand, ``render``: it writes the
deterministic Caddyfile for the deployment port into the network directory
and prints the shell assignments deploy.sh evaluates (bind host is always
loopback; the fingerprint is the hash of the rendered product, never of
the generator source). The old init/read applied-state protocol is gone.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from cbrowser.network_config import (
    compute_caddyfile_sha256,
    generate_caddyfile,
)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cbrowser.network_config_cli", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _assignments(stdout: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key] = value.strip().strip("'")
    return out


def test_render_writes_caddyfile_and_prints_assignments(tmp_path: Path) -> None:
    net_dir = tmp_path / "network"
    result = _run_cli(
        "render", "--network-dir", str(net_dir), "--https-port", "56661"
    )
    assert result.returncode == 0, result.stderr
    caddyfile = net_dir / "Caddyfile"
    assert caddyfile.is_file()
    assert caddyfile.read_text(encoding="utf-8") == generate_caddyfile(56661)
    values = _assignments(result.stdout)
    assert values["BIND_HOST"] == "127.0.0.1"
    assert values["HTTPS_PORT"] == "56661"
    assert values["PUBLIC_ORIGIN"] == "https://127.0.0.1:56661"
    assert values["CADDYFILE_SHA256"] == compute_caddyfile_sha256(
        generate_caddyfile(56661)
    )
    assert "LAN" not in result.stdout


def test_render_is_idempotent_and_port_sensitive(tmp_path: Path) -> None:
    net_dir = tmp_path / "network"
    first = _run_cli(
        "render", "--network-dir", str(net_dir), "--https-port", "56661"
    )
    assert first.returncode == 0, first.stderr
    second = _run_cli(
        "render", "--network-dir", str(net_dir), "--https-port", "56661"
    )
    assert second.returncode == 0, second.stderr
    assert _assignments(first.stdout) == _assignments(second.stdout)
    assert (net_dir / "Caddyfile").read_text(encoding="utf-8") == (
        generate_caddyfile(56661)
    )
    third = _run_cli(
        "render", "--network-dir", str(net_dir), "--https-port", "58888"
    )
    assert third.returncode == 0, third.stderr
    assert _assignments(third.stdout)["CADDYFILE_SHA256"] != (
        _assignments(first.stdout)["CADDYFILE_SHA256"]
    )
    assert (net_dir / "Caddyfile").read_text(encoding="utf-8") == (
        generate_caddyfile(58888)
    )


def test_render_rejects_invalid_port(tmp_path: Path) -> None:
    net_dir = tmp_path / "network"
    result = _run_cli(
        "render", "--network-dir", str(net_dir), "--https-port", "0"
    )
    assert result.returncode == 2
    assert not (net_dir / "Caddyfile").exists()


def test_applied_state_subcommands_are_gone() -> None:
    for command in ("init", "read"):
        result = _run_cli(command, "--network-dir", "/nonexistent", "--https-port", "56661")
        assert result.returncode == 2, command
