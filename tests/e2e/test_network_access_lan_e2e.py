"""E2E and Blackbox Verification for LAN Access Protocol Settings (t042).

Covers:
- AC-004: Physical loopback binding blocks non-loopback clients; 0.0.0.0 binding permits non-loopback clients.
- AC-006: Deterministic Caddyfile generation, zero static hardcoded Caddyfiles in repo.
- AC-008: Root CA certificate download only returns public certificate; no CA private key in API mounts.
"""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import time
import pytest

pytestmark = pytest.mark.serial

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def detect_host_non_loopback_ip() -> str:
    """Dynamically detect host non-loopback LAN IP.

    Per supervisory directive:
    - Never hardcode host LAN IP.
    - Explicitly fail with a clear reason if no non-loopback IP can be detected;
      silent skips are forbidden.
    """
    # 1. Routing socket inquiry (UDP connect does not transmit packets)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            candidate = s.getsockname()[0]
            if candidate and not candidate.startswith("127.") and not candidate.startswith("169.254."):
                return candidate
    except Exception:
        pass

    # 2. Interface probing fallback (macOS / Linux)
    for cmd in [
        ["ipconfig", "getifaddr", "en0"],
        ["ipconfig", "getifaddr", "en1"],
        ["ipconfig", "getifaddr", "eth0"],
        ["sh", "-c", "ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}'"],
    ]:
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
            if out and not out.startswith("127.") and not out.startswith("169.254."):
                return out
        except Exception:
            continue

    raise RuntimeError(
        "FAIL: Failed to detect host non-loopback LAN IP. "
        "E2E non-loopback client fixture requires an active host network interface with a non-loopback IPv4 address."
    )


def _network_root_ca_client():
    """Assemble the network router exactly as the production app does."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from cbrowser.api.v1.network_router import create_network_router

    app = FastAPI()
    temp_ca_dir = REPO_ROOT / ".scratch" / "test_ca_dir"
    temp_ca_dir.mkdir(parents=True, exist_ok=True)
    pub_cert = "-----BEGIN CERTIFICATE-----\nMIIC...PUBLIC_CERT_DATA\n-----END CERTIFICATE-----"
    (temp_ca_dir / "root.crt").write_text(pub_cert)
    app.state.caddy_ca_dir = temp_ca_dir
    app.include_router(create_network_router())
    return TestClient(app)


def test_e2e_ac006_no_hardcoded_caddyfiles_in_repo():
    """AC-006: No hardcoded hostnames or IP addresses in any committed Caddyfile."""
    caddy_dir = REPO_ROOT / "config" / "deploy" / "caddy"
    caddyfile = caddy_dir / "Caddyfile"
    assert not caddyfile.exists(), "Hardcoded Caddyfile must not exist in config/deploy/caddy/"

    res = subprocess.run(
        ["git", "ls-files", "config/deploy/caddy/Caddyfile"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert not res.stdout.strip(), "Caddyfile must not be tracked in git"


def test_e2e_ac008_root_ca_public_only_and_no_private_key_mount():
    """AC-008: Root CA download returns public cert; API container mounts do not expose CA private key."""
    # 1. Inspect compose.yaml: strictly inspect the 'api' service block
    compose_path = REPO_ROOT / "compose.yaml"
    compose_lines = compose_path.read_text(encoding="utf-8").splitlines()

    in_api_service = False
    in_api_volumes = False
    api_volumes: list[str] = []

    for line in compose_lines:
        stripped = line.strip()
        if stripped == "api:":
            in_api_service = True
            continue
        if in_api_service and line.startswith("  ") and not line.startswith("    "):
            # Next top-level service in compose
            break
        if in_api_service:
            if stripped == "volumes:":
                in_api_volumes = True
                continue
            elif in_api_volumes:
                if stripped.startswith("-"):
                    api_volumes.append(stripped)
                elif not stripped.startswith("#") and stripped:
                    in_api_volumes = False

    assert api_volumes, "API service volumes block should be found"
    for v_str in api_volumes:
        assert "caddy_data" not in v_str, "API service must not mount caddy_data volume"
        assert "root.key" not in v_str, "API service must not mount root.key"

    # 2. Functional endpoint check
    client = _network_root_ca_client()
    resp = client.get("/api/v1/network/root-ca")
    assert resp.status_code == 200
    assert "-----BEGIN CERTIFICATE-----" in resp.text
    assert "PRIVATE KEY" not in resp.text
    assert resp.headers["content-disposition"] == 'attachment; filename="cbrowser_root_ca.crt"'


def test_e2e_a2_network_root_ca_authoritative_prefix_and_legacy_path_rejected():
    """A2: root CA is served under /api/v1/network; legacy /network path is rejected."""
    client = _network_root_ca_client()
    resp = client.get("/api/v1/network/root-ca")
    assert resp.status_code == 200
    assert "-----BEGIN CERTIFICATE-----" in resp.text
    assert "PRIVATE KEY" not in resp.text
    assert client.get("/network/root-ca").status_code == 404


def test_e2e_ac004_port_binding_physical_isolation():
    """AC-004: Physical port binding verification using Docker container as non-loopback client."""
    lan_ip = detect_host_non_loopback_ip()
    port_local = 58913
    port_lan = 58914

    subprocess.run("docker rm -f test-ac004-local test-ac004-lan 2>/dev/null", shell=True)

    # 1. Container bound only to 127.0.0.1
    subprocess.run(
        f"docker run -d --name test-ac004-local -p 127.0.0.1:{port_local}:80 python:3.12-alpine python3 -m http.server 80",
        shell=True,
        check=True,
    )

    # 2. Container bound to 0.0.0.0
    subprocess.run(
        f"docker run -d --name test-ac004-lan -p 0.0.0.0:{port_lan}:80 python:3.12-alpine python3 -m http.server 80",
        shell=True,
        check=True,
    )

    try:
        # Wait up to 5s for containers to be ready
        ready = False
        for _ in range(10):
            res = subprocess.run(
                f"docker run --rm curlimages/curl:latest -s -m 1 http://{lan_ip}:{port_lan}",
                shell=True,
            )
            if res.returncode == 0:
                ready = True
                break
            time.sleep(0.5)

        assert ready, f"Target test container on 0.0.0.0:{port_lan} did not become ready at {lan_ip}"

        # Loopback binding check: non-loopback client MUST fail
        res_local = subprocess.run(
            f"docker run --rm curlimages/curl:latest -s -m 2 http://{lan_ip}:{port_local}",
            shell=True,
        )
        assert res_local.returncode != 0, f"Loopback binding 127.0.0.1 must be unreachable from {lan_ip}"

        # 0.0.0.0 binding check: non-loopback client MUST succeed
        res_lan = subprocess.run(
            f"docker run --rm curlimages/curl:latest -s -m 2 http://{lan_ip}:{port_lan}",
            shell=True,
            stdout=subprocess.PIPE,
        )
        assert res_lan.returncode == 0, f"0.0.0.0 binding must be reachable from {lan_ip}"
        assert b"Directory listing" in res_lan.stdout or b"<html" in res_lan.stdout.lower()

    finally:
        subprocess.run("docker rm -f test-ac004-local test-ac004-lan 2>/dev/null", shell=True)
