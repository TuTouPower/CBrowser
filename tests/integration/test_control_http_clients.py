"""t031 CLI control + Gateway client against a stub HTTP API server."""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from cbrowser.agent_executor.session import ExecutorSession, SessionError
from cbrowser.gateway.api_client import GatewayApiClient


class _StubHandler(BaseHTTPRequestHandler):
    """Canned control responses; records every request."""

    responses: list[dict] = []
    seen: list[dict] = []

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 - stdlib name
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode() or "{}")
        except ValueError:
            payload = {}
        self.seen.append({"path": self.path, "body": payload})
        if self.path.endswith("/control/takeover"):
            self._send(200, {"owner": "user", "generation": 2})
            return
        if self.responses:
            status, body = self.responses.pop(0)
            self._send(status, body)
            return
        self._send(404, {"detail": "no canned response"})

    def log_message(self, *args):  # silence stderr
        pass


@pytest.fixture
def stub_server():
    _StubHandler.responses = []
    _StubHandler.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
async def test_cli_claim_handoff_round_trip_and_stale_fence(stub_server):
    port = stub_server
    _StubHandler.responses = [
        (200, {"owner": "agent", "generation": 1}),
        (200, {"owner": "agent", "generation": 2}),
        # Stale: server returns an older generation than known.
        (200, {"owner": "agent", "generation": 1}),
    ]
    session = ExecutorSession(
        endpoint=f"ws://127.0.0.1:{port}/api/v1/automation/profiles/p1/cdp",
        token="cbat_test",
        profile_id="p1",
        runtime_instance_id="inst-1",
    )
    state = await session.control_claim()
    assert state["generation"] == 1
    state = await session.control_handoff("permission")
    assert state["generation"] == 2
    with pytest.raises(SessionError) as exc:
        await session.control_claim()
    assert exc.value.error_code == "control_stale_generation"
    # Both calls carried this session's id.
    bodies = [entry["body"] for entry in _StubHandler.seen]
    assert all(b.get("agent_session_id") for b in bodies)


@pytest.mark.asyncio
async def test_cli_claim_conflict_maps_to_control_conflict(stub_server):
    # t069: the stub serves the API's real wire shape — the app-level
    # HTTPException handler converts the route's detail dict into the
    # unified ErrorResponse (error = the conflict code). The pre-t069
    # stub served the raw {"detail": {"code": ...}} shape, which the
    # strict client now treats as a protocol error.
    _StubHandler.responses = [
        (
            409,
            {
                "error": "control_reclaim_blocked",
                "message": "Control was taken over; an explicit human "
                "restore is required before an agent may claim again",
                "retryable": False,
            },
        ),
    ]
    session = ExecutorSession(
        endpoint=f"ws://127.0.0.1:{stub_server}/api/v1/automation/profiles/p1/cdp",
        token="cbat_test",
        profile_id="p1",
        runtime_instance_id="inst-1",
    )
    with pytest.raises(SessionError) as exc:
        await session.control_claim()
    assert exc.value.error_code == "control_conflict"
    assert "control_reclaim_blocked" in str(exc.value)


@pytest.mark.asyncio
async def test_gateway_client_reports_takeover(stub_server, tmp_path):
    token_file = tmp_path / "gateway.txt"
    token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    token_file.chmod(0o600)
    client = GatewayApiClient(
        f"http://127.0.0.1:{stub_server}", token_file
    )
    result = await client.report_human_takeover("p1", "conn-9", "key")
    assert result is not None
    assert result["owner"] == "user"
    assert result["generation"] == 2
    assert _StubHandler.seen[-1]["path"].endswith(
        "/internal/gateway/profiles/p1/control/takeover"
    )
    assert _StubHandler.seen[-1]["body"]["input_kind"] == "key"
    assert _StubHandler.seen[-1]["body"]["conn_id"] == "conn-9"
