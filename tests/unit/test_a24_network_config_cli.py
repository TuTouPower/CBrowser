import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from cbrowser.domain.models import NetworkAccessConfig
from cbrowser.network_config import (
    APPLIED_VERSION_FILENAME,
    CADDYFILE_FILENAME,
    build_applied_network_version,
    compute_caddyfile_sha256,
    write_applied_network_state,
)

ROOT = Path(__file__).resolve().parents[2]
EXIT_MISSING = 3
EXIT_CORRUPT = 4


def _cli(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src" / "backend")
    return subprocess.run(
        [sys.executable, "-m", "cbrowser.network_config_cli", *args],
        env=env,
        capture_output=True,
        text=True,
    )


def _parse_assignments(text):
    values = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip().strip("'")
    return values


def _write_custom_state(network_dir, port, lan_ip):
    cfg = NetworkAccessConfig(
        lan_access_enabled=lan_ip is not None,
        lan_advertised_ip=lan_ip,
        https_port=port,
    )
    ver, caddy = build_applied_network_version(cfg, version=7)
    write_applied_network_state(network_dir, ver, caddy)
    return ver, caddy


def test_init_first_run_writes_real_hash(tmp_path):
    network_dir = tmp_path / "network"
    result = _cli("init", "--network-dir", str(network_dir), "--https-port", "56661")
    assert result.returncode == 0, result.stderr
    version_path = network_dir / APPLIED_VERSION_FILENAME
    caddy_path = network_dir / CADDYFILE_FILENAME
    assert version_path.is_file()
    assert caddy_path.is_file()
    data = json.loads(version_path.read_text(encoding="utf-8"))
    caddy_text = caddy_path.read_text(encoding="utf-8")
    expected = hashlib.sha256(caddy_text.encode("utf-8")).hexdigest()
    assert data["caddyfile_sha256"] == expected
    assert data["caddyfile_sha256"] != ""
    assert data["config"]["https_port"] == 56661
    assert data["bind_host"] == "127.0.0.1"
    assert data["origin_whitelist"] == [
        "https://127.0.0.1:56661",
        "https://localhost:56661",
    ]


def test_init_custom_port_from_argument(tmp_path):
    network_dir = tmp_path / "network"
    result = _cli("init", "--network-dir", str(network_dir), "--https-port", "57000")
    assert result.returncode == 0, result.stderr
    data = json.loads(
        (network_dir / APPLIED_VERSION_FILENAME).read_text(encoding="utf-8")
    )
    assert data["config"]["https_port"] == 57000
    assert data["origin_whitelist"] == [
        "https://127.0.0.1:57000",
        "https://localhost:57000",
    ]


def test_init_keeps_applied_custom_port_and_lan(tmp_path):
    network_dir = tmp_path / "network"
    ver, caddy = _write_custom_state(network_dir, 57000, "192.168.31.76")
    before_v = (network_dir / APPLIED_VERSION_FILENAME).read_bytes()
    before_c = (network_dir / CADDYFILE_FILENAME).read_bytes()
    result = _cli("init", "--network-dir", str(network_dir), "--https-port", "56661")
    assert result.returncode == 0, result.stderr
    assert (network_dir / APPLIED_VERSION_FILENAME).read_bytes() == before_v
    assert (network_dir / CADDYFILE_FILENAME).read_bytes() == before_c
    read = _cli("read", "--network-dir", str(network_dir))
    assert read.returncode == 0, read.stderr
    values = _parse_assignments(read.stdout)
    assert values["HTTPS_PORT"] == "57000"
    assert values["BIND_HOST"] == "0.0.0.0"
    assert values["LAN_ACCESS_ENABLED"] == "1"
    assert values["LAN_ADVERTISED_IP"] == "192.168.31.76"
    assert values["PUBLIC_ORIGIN"] == "https://127.0.0.1:57000"
    assert values["CADDYFILE_SHA256"] == compute_caddyfile_sha256(caddy)
    assert ver.config.https_port == 57000


def test_read_missing_is_distinguished(tmp_path):
    result = _cli("read", "--network-dir", str(tmp_path / "empty"))
    assert result.returncode == EXIT_MISSING
    assert "missing" in result.stderr.lower()
    assert not (tmp_path / "empty" / APPLIED_VERSION_FILENAME).exists()


def test_init_partial_state_is_rejected(tmp_path):
    network_dir = tmp_path / "network"
    network_dir.mkdir()
    (network_dir / APPLIED_VERSION_FILENAME).write_text("{}", encoding="utf-8")
    result = _cli("init", "--network-dir", str(network_dir), "--https-port", "56661")
    assert result.returncode == EXIT_CORRUPT
    assert not (network_dir / CADDYFILE_FILENAME).exists()


def test_read_corrupt_variants_rejected(tmp_path):
    network_dir = tmp_path / "network"
    network_dir.mkdir()
    version_path = network_dir / APPLIED_VERSION_FILENAME
    caddy_path = network_dir / CADDYFILE_FILENAME
    caddy_path.write_text("valid caddy", encoding="utf-8")

    version_path.write_text("not json", encoding="utf-8")
    bad = _cli("read", "--network-dir", str(network_dir))
    assert bad.returncode == EXIT_CORRUPT
    assert "corrupt" in bad.stderr.lower() or "malformed" in bad.stderr.lower()

    data = {
        "version": 1,
        "config": {
            "lan_access_enabled": False,
            "lan_advertised_ip": None,
            "https_port": 56661,
        },
        "bind_host": "127.0.0.1",
        "applied_at": "2026-11-09T00:00:00+08:00",
        "caddyfile_sha256": "",
        "origin_whitelist": [
            "https://127.0.0.1:56661",
            "https://localhost:56661",
        ],
    }
    version_path.write_text(json.dumps(data), encoding="utf-8")
    empty_hash = _cli("read", "--network-dir", str(network_dir))
    assert empty_hash.returncode == EXIT_CORRUPT

    data["caddyfile_sha256"] = "0" * 64
    version_path.write_text(json.dumps(data), encoding="utf-8")
    mismatched = _cli("read", "--network-dir", str(network_dir))
    assert mismatched.returncode == EXIT_CORRUPT


def test_init_corrupt_not_silently_reset(tmp_path):
    network_dir = tmp_path / "network"
    network_dir.mkdir()
    (network_dir / APPLIED_VERSION_FILENAME).write_text("garbage", encoding="utf-8")
    (network_dir / CADDYFILE_FILENAME).write_text("garbage", encoding="utf-8")
    before = (network_dir / APPLIED_VERSION_FILENAME).read_bytes()
    result = _cli("init", "--network-dir", str(network_dir), "--https-port", "56661")
    assert result.returncode == EXIT_CORRUPT
    assert (network_dir / APPLIED_VERSION_FILENAME).read_bytes() == before


def test_read_is_deterministic_and_shell_consumable(tmp_path):
    network_dir = tmp_path / "network"
    _write_custom_state(network_dir, 58000, None)
    first = _cli("read", "--network-dir", str(network_dir))
    second = _cli("read", "--network-dir", str(network_dir))
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    script = "eval \"$1\"; printf '%s|%s|%s' \"$HTTPS_PORT\" \"$BIND_HOST\" \"$PUBLIC_ORIGIN\""
    consumed = subprocess.run(
        ["bash", "-c", script, "bash", first.stdout],
        capture_output=True,
        text=True,
    )
    assert consumed.returncode == 0, consumed.stderr
    assert consumed.stdout == "58000|127.0.0.1|https://127.0.0.1:58000"
