"""E2E regression test for graceful Supervisor CLI shutdown.

Validates that SIGTERM gracefully terminates the Supervisor CLI process within 10s
without hanging on the background Docker events stream thread, and returns exit code 0.
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from e2e_env import require_e2e_env

REPO_ROOT = Path(__file__).resolve().parents[2]

from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT  # noqa: E402
from supervisor_recovery_probe.offline_fixture import RealApiProcess  # noqa: E402

pytestmark = pytest.mark.serial


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_supervisor_cli_graceful_shutdown_on_sigterm(tmp_path: Path) -> None:
    """Real Docker + Real API + Real Supervisor CLI must exit 0 on SIGTERM."""
    require_e2e_env(docker=True)

    # Image mapping from gate environment
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_SUPERVISOR_TEST_IMAGE",
    )
    browser_image = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    stream_image = env["CBROWSER_STREAM_TEST_IMAGE"]
    policy_image = (
        os.environ.get("CBROWSER_NETWORK_POLICY_IMAGE")
        or env["CBROWSER_SUPERVISOR_TEST_IMAGE"]
    )

    assert browser_image.startswith("sha256:"), (
        f"Immutable ID required: {browser_image}"
    )
    assert stream_image.startswith("sha256:"), (
        f"Immutable ID required: {stream_image}"
    )

    base = tmp_path
    keys = {}
    for name in ("supervisor", "agent", "gateway"):
        p = base / f"{name}_key"
        p.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        p.chmod(0o600)
        keys[name] = p

    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(REPO_ROOT / "src/backend"),
        PYTHONDONTWRITEBYTECODE="1",
        CBROWSER_BROWSER_IMAGE=browser_image,
        CBROWSER_STREAM_IMAGE=stream_image,
    )
    if policy_image:
        assert policy_image.startswith("sha256:")
        env["CBROWSER_NETWORK_POLICY_IMAGE"] = policy_image

    for k in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        env.pop(k, None)

    api_port = _get_free_port()
    api = RealApiProcess(
        api_port,
        base / "api.db",
        keys["supervisor"],
        REPO_ROOT,
        env,
        base / "api.log",
    )

    proc: subprocess.Popen | None = None
    out = None

    try:
        api.start()
        sup_port = _get_free_port()
        prefix = "baseline-exit-" + secrets.token_hex(4)

        for name in ("data", "data/engine", "data/geoip"):
            (base / name).mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            "-m",
            "cbrowser.supervisor",
            "--api-url",
            api.url,
            "--data-root",
            str(base / "data"),
            "--engine-cache",
            str(base / "data/engine"),
            "--geoip-cache",
            str(base / "data/geoip"),
            "--token-file",
            str(keys["supervisor"]),
            "--agent-key-file",
            str(keys["agent"]),
            "--gateway-url",
            f"ws://127.0.0.1:{DEFAULT_GATEWAY_PORT}",
            "--gateway-control-url",
            f"http://127.0.0.1:{DEFAULT_GATEWAY_PORT}",
            "--gateway-token-file",
            str(keys["gateway"]),
            "--gateway-port",
            str(DEFAULT_GATEWAY_PORT),
            "--prefix",
            prefix,
            "--host",
            "127.0.0.1",
            "--port",
            str(sup_port),
        ]

        log_path = base / "supervisor.log"
        out = log_path.open("w", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            cwd=REPO_ROOT,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
        )

        deadline = time.monotonic() + 20.0
        supervisor_ready = False
        with httpx.Client(trust_env=False) as client:
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError("Supervisor exited before readiness")
                try:
                    r = client.get(
                        f"http://127.0.0.1:{sup_port}/supervisor/v1/health",
                        headers={
                            "Authorization": "Bearer " + keys["supervisor"].read_text(
                                encoding="utf-8"
                            ).strip()
                        },
                        timeout=1.0,
                    )
                    if r.status_code == 200:
                        supervisor_ready = True
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)

        assert supervisor_ready, "Supervisor health check timed out within 20s"

        # Deterministically wait for watcher to subscribe Docker events
        expected_sub_log = f"Docker events stream subscribed for prefix={prefix}"
        deadline_sub = time.monotonic() + 10.0
        subscribed = False
        while time.monotonic() < deadline_sub:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"Supervisor exited prematurely with rc={proc.returncode}"
                )
            if log_path.is_file():
                log_text = log_path.read_text(encoding="utf-8", errors="replace")
                if expected_sub_log in log_text:
                    subscribed = True
                    break
            time.sleep(0.05)

        assert subscribed, "Docker events stream subscription log not found within 10s"

        # Send graceful shutdown signal SIGTERM
        proc.terminate()

        # Wait up to 10 seconds for graceful exit
        try:
            returncode = proc.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail(
                "Supervisor process hung after SIGTERM and had to be killed"
            )

        assert returncode == 0, (
            f"Supervisor must exit with code 0 on SIGTERM, got {returncode}"
        )

    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        if out is not None:
            out.close()
        api.stop()
