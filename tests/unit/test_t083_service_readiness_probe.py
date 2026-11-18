"""t083: service_readiness_probe verdict logic, tested directly.

The deploy gate runs this probe inside the Supervisor container and
decides success from its exit code, so the four verdicts must be
exercised for real — a string-presence assertion on deploy.sh cannot
tell a probe that always answers "ready" from a working one.  A local
stub HTTP server stands in for the three services; no Docker needed.
"""

from __future__ import annotations

import importlib.util
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "service_readiness_probe",
        REPO_ROOT / "scripts" / "service_readiness_probe.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _handler_with(behavior: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D102 - keep test output quiet
            pass

        def do_GET(self):
            mode = behavior.get(self.path, "ok")
            if mode == "hang":
                time.sleep(10)
                payload = {"status": "ok"}
            elif mode == "non_ok":
                payload = {"status": "degraded"}
            elif mode == "supervisor_not_ready":
                payload = {"ready": False}
            elif mode == "supervisor_ready":
                payload = {"ready": True}
            else:
                payload = {"status": "ok"}
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


@pytest.fixture
def stub_server():
    behavior: dict[str, str] = {}
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), _handler_with(behavior)
    )
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, behavior
    finally:
        server.shutdown()
        server.server_close()


def _env_for(probe, server, monkeypatch):
    base = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setenv("CBROWSER_API_URL", base)
    monkeypatch.setenv("CBROWSER_GATEWAY_CONTROL_URL", base)
    monkeypatch.delenv("CBROWSER_SUPERVISOR_TOKEN_FILE", raising=False)
    monkeypatch.delenv("CBROWSER_SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setattr(probe, "SUPERVISOR_BASE_URL", base)


def test_all_ready_returns_zero(stub_server, monkeypatch):
    probe = _load_probe()
    server, behavior = stub_server
    behavior["/api/v1/health"] = "ok"
    behavior["/gateway/v1/health"] = "ok"
    behavior["/supervisor/v1/readiness"] = "supervisor_ready"
    _env_for(probe, server, monkeypatch)
    result = probe.run(5.0)
    assert result == {
        "ready": True,
        "reason": None,
        "services": {"api": True, "gateway": True, "supervisor": True},
    }
    assert probe.main(["service_readiness_probe.py", "wait", "5"]) == 0


def test_non_ok_api_is_listed_and_fails(stub_server, monkeypatch):
    probe = _load_probe()
    server, behavior = stub_server
    behavior["/api/v1/health"] = "non_ok"
    behavior["/gateway/v1/health"] = "ok"
    behavior["/supervisor/v1/readiness"] = "supervisor_ready"
    _env_for(probe, server, monkeypatch)
    result = probe.run(2.0)
    assert result["ready"] is False
    assert result["reason"] == "services_not_ready:api"
    assert result["services"] == {
        "api": False,
        "gateway": True,
        "supervisor": True,
    }
    assert probe.main(["service_readiness_probe.py", "wait", "2"]) == 1


def test_supervisor_not_ready_is_listed_and_fails(
    stub_server, monkeypatch
):
    # t083_test_f008: the supervisor's "ready is True" verdict must
    # be exercised too — a probe that always reported the Supervisor
    # ready would otherwise stay green.
    probe = _load_probe()
    server, behavior = stub_server
    behavior["/api/v1/health"] = "ok"
    behavior["/gateway/v1/health"] = "ok"
    behavior["/supervisor/v1/readiness"] = "supervisor_not_ready"
    _env_for(probe, server, monkeypatch)
    result = probe.run(2.0)
    assert result["ready"] is False
    assert result["reason"] == "services_not_ready:supervisor"
    assert result["services"] == {
        "api": True,
        "gateway": True,
        "supervisor": False,
    }
    assert probe.main(["service_readiness_probe.py", "wait", "2"]) == 1


def test_hanging_service_fails_within_the_deadline(
    stub_server, monkeypatch
):
    probe = _load_probe()
    server, behavior = stub_server
    behavior["/api/v1/health"] = "hang"
    behavior["/gateway/v1/health"] = "ok"
    behavior["/supervisor/v1/readiness"] = "supervisor_ready"
    _env_for(probe, server, monkeypatch)
    started = time.monotonic()
    result = probe.run(3.0)
    elapsed = time.monotonic() - started
    assert result["ready"] is False
    assert result["services"]["api"] is False
    # The verdict must land near the deadline, not after the 10 s hang.
    assert elapsed < 5.5


def test_unreachable_service_fails_fast(stub_server, monkeypatch):
    probe = _load_probe()
    server, behavior = stub_server
    behavior["/gateway/v1/health"] = "ok"
    behavior["/supervisor/v1/readiness"] = "supervisor_ready"
    _env_for(probe, server, monkeypatch)
    # Point only the API at a closed port: nothing listens on port 1.
    monkeypatch.setenv("CBROWSER_API_URL", "http://127.0.0.1:1")
    started = time.monotonic()
    result = probe.run(2.0)
    elapsed = time.monotonic() - started
    assert result["ready"] is False
    assert result["reason"] == "services_not_ready:api"
    assert result["services"]["api"] is False
    assert elapsed < 3.0


def test_bad_usage_exits_two():
    probe = _load_probe()
    assert probe.main(["service_readiness_probe.py"]) == 2
    assert (
        probe.main(["service_readiness_probe.py", "wait", "abc"]) == 2
    )
