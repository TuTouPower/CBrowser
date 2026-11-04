"""t027 integration tests: Gateway health route and the in-container
readiness probe executed against the real Supervisor control app.

The probe (scripts/supervisor_readiness_probe.py) is the exact file the
deploy script pipes into the Supervisor container; here it runs as a
subprocess against a real control app served over HTTP, with a stub core
behind it.  No Docker is involved; real-container execution is t032's.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import uvicorn
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.protocol import (
    ProfileReadiness,
    ReadinessResponse,
    ReconcileAllResponse,
)

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts" / "supervisor_readiness_probe.py"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _StubCore:
    def __init__(self, readiness: ReadinessResponse, *, fail_reconcile: bool = False):
        self._readiness = readiness
        self._fail_reconcile = fail_reconcile
        self.reconcile_calls = 0

    async def reconcile_all(self) -> ReconcileAllResponse:
        self.reconcile_calls += 1
        if self._fail_reconcile:
            raise RuntimeError("docker unavailable")
        return ReconcileAllResponse(scanned=1, profiles=["p1"])

    async def readiness(self) -> ReadinessResponse:
        return self._readiness


async def _serve_control_app(core: _StubCore, token_file: Path) -> tuple[uvicorn.Server, asyncio.Task, int]:
    app = create_control_app(core=core, token_file=token_file)
    port = _free_port()
    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    assert server.started
    return server, task, port


def _run_probe_sync(
    port: int, token_file: Path, deadline: str
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "CBROWSER_SUPERVISOR_URL": f"http://127.0.0.1:{port}",
        "CBROWSER_SUPERVISOR_TOKEN_FILE": str(token_file),
    }
    return subprocess.run(
        [sys.executable, str(PROBE), "verify", deadline],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


async def _run_probe(
    port: int, token_file: Path, deadline: str
) -> subprocess.CompletedProcess[str]:
    # Off the event loop: the control app is served by this same loop and
    # must stay responsive while the probe subprocess runs.
    return await asyncio.to_thread(_run_probe_sync, port, token_file, deadline)


@pytest.fixture()
def token_file(tmp_path: Path) -> Path:
    path = tmp_path / "supervisor_key"
    path.write_text("t" * 64, encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.mark.asyncio
async def test_probe_ready_when_all_profiles_converged(
    token_file: Path,
) -> None:
    core = _StubCore(
        ReadinessResponse(
            ready=True,
            profiles=[ProfileReadiness(profile_id="p1", ready=True)],
        )
    )
    server, task, port = await _serve_control_app(core, token_file)
    try:
        result = await _run_probe(port, token_file, "10")
    finally:
        server.should_exit = True
        await task
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ready"] is True
    assert payload["profiles"][0]["profile_id"] == "p1"
    assert core.reconcile_calls == 1


@pytest.mark.asyncio
async def test_probe_reports_unready_profiles_with_diagnostics(
    token_file: Path,
) -> None:
    core = _StubCore(
        ReadinessResponse(
            ready=False,
            reason="profiles_not_converged",
            profiles=[
                ProfileReadiness(
                    profile_id="p-stuck",
                    ready=False,
                    diagnostics=["browser_not_registered"],
                )
            ],
        )
    )
    server, task, port = await _serve_control_app(core, token_file)
    try:
        result = await _run_probe(port, token_file, "1")
    finally:
        server.should_exit = True
        await task
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ready"] is False
    assert payload["profiles"][0]["profile_id"] == "p-stuck"
    assert payload["profiles"][0]["diagnostics"] == ["browser_not_registered"]


@pytest.mark.asyncio
async def test_probe_report_mode_never_reconciles(token_file: Path) -> None:
    """Report mode is the read-only diagnostics path used after a failed
    `compose up --wait`: a single readiness snapshot, no reconcile."""
    core = _StubCore(
        ReadinessResponse(
            ready=False,
            reason="profiles_not_converged",
            profiles=[
                ProfileReadiness(
                    profile_id="p-stuck",
                    ready=False,
                    diagnostics=["stream_not_registered"],
                )
            ],
        )
    )
    server, task, port = await _serve_control_app(core, token_file)
    try:
        env = {
            **os.environ,
            "CBROWSER_SUPERVISOR_URL": f"http://127.0.0.1:{port}",
            "CBROWSER_SUPERVISOR_TOKEN_FILE": str(token_file),
        }
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(PROBE), "report"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        server.should_exit = True
        await task
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["profiles"][0]["diagnostics"] == ["stream_not_registered"]
    assert core.reconcile_calls == 0


@pytest.mark.asyncio
async def test_probe_reconcile_failure_is_not_ready(token_file: Path) -> None:
    core = _StubCore(ReadinessResponse(ready=True), fail_reconcile=True)
    server, task, port = await _serve_control_app(core, token_file)
    try:
        result = await _run_probe(port, token_file, "1")
    finally:
        server.should_exit = True
        await task
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ready"] is False
    assert payload["reason"].startswith("reconcile_request_failed")
