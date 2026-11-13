"""t055 A10: CDP close code is passed through only when the peer closes.

The websockets close_code semantics were verified by experiment
(.scratch/spike_close_code.py, websockets 17.4): the peer's code must be
read BEFORE the local close (after a local close websockets reports our
own 1000 when the peer never closed), and a client-initiated disconnect
must not propagate a code.

Also covers AC-004: the Supervisor CDP proxy rejects a session whose
observed state is still "starting" (health unknown after restore).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from cbrowser.api.v1 import automation_router as router_module
from cbrowser.api.v1.automation_router import automation_router
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.path_validator import PathValidator
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocket, WebSocketDisconnect

PROFILE = "prof_t055"
TOKEN = "auto-token-t055"


class _FakeUpstream:
    """Controllable websockets-client stand-in for automation_router.

    close() deliberately overwrites close_code with our own 1000 even
    when the peer already closed: this is stricter than the real
    websockets library (spike scenario 3: a peer 4403 survives a local
    close), and it pins AC-007's read-before-close order — production
    code that read the code after close() would see 1000 instead of
    the peer's 4403.
    """

    def __init__(
        self,
        *,
        close_code=None,
        messages=None,
        block_forever: bool = False,
        close_error: Exception | None = None,
    ) -> None:
        self.close_code = close_code
        self._messages = list(messages or [])
        self._block_forever = block_forever
        self._close_error = close_error
        self.sent: list = []
        self.closed = False

    async def send(self, message) -> None:
        self.sent.append(message)

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for message in self._messages:
            yield message
        if self._block_forever:
            await asyncio.Event().wait()

    async def close(self) -> None:
        self.closed = True
        # See the class docstring: always overwrite, so the read order
        # in production code is observable through this fake.
        self.close_code = 1000
        if self._close_error is not None:
            raise self._close_error


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(automation_router)

    async def _allow(token, profile_id, client_ip=None):
        return (True, None)

    async def _token_id(token):
        return "token-1"

    app.state.auth_service = SimpleNamespace(
        authorize_automation=_allow,
        resolve_automation_token_id=_token_id,
    )
    app.state.coordinator = SimpleNamespace(
        is_enabled=lambda: True,
        supervisor_url="ws://supervisor.invalid",
    )
    app.state.supervisor_token = SecretStr("supervisor-token")
    app.state.control_service = None
    app.state.automation_tunnels = None
    app.state.trusted_proxy_cidrs = []
    return app


def _patch_upstream(monkeypatch, upstream: _FakeUpstream):
    async def _connect(url, additional_headers=None, **kwargs):
        return upstream

    monkeypatch.setattr(
        router_module, "websockets", SimpleNamespace(connect=_connect)
    )


def _close_spy(monkeypatch):
    calls: list[tuple[int, str | None]] = []
    orig_close = WebSocket.close

    async def _spy(self, code: int = 1000, reason: str | None = None):
        calls.append((code, reason))
        await orig_close(self, code=code, reason=reason)

    monkeypatch.setattr(WebSocket, "close", _spy)
    return calls


def test_client_disconnect_first_does_not_propagate_close_code(monkeypatch):
    """AC-007: client leaves first -> no 4403 is sent to the client."""
    upstream = _FakeUpstream(close_code=4403, block_forever=True)
    _patch_upstream(monkeypatch, upstream)
    calls = _close_spy(monkeypatch)

    with TestClient(_app()) as client:
        with client.websocket_connect(
            f"/api/v1/automation/profiles/{PROFILE}/cdp",
            headers={"Authorization": f"Bearer {TOKEN}"},
        ):
            pass  # disconnect immediately

    assert upstream.closed is True
    assert not any(code == 4403 for code, _ in calls)


def test_peer_close_code_is_propagated_to_client(monkeypatch):
    """AC-007: peer closes 4403 -> the client receives WebSocketDisconnect 4403."""
    upstream = _FakeUpstream(close_code=4403)
    _patch_upstream(monkeypatch, upstream)

    with TestClient(_app()) as client:
        with client.websocket_connect(
            f"/api/v1/automation/profiles/{PROFILE}/cdp",
            headers={"Authorization": f"Bearer {TOKEN}"},
        ) as websocket:
            with pytest.raises(WebSocketDisconnect) as caught:
                websocket.receive_text()

    assert caught.value.code == 4403


def test_upstream_close_error_does_not_block_client_close(monkeypatch):
    """AC-007: a failing upstream.close() still delivers the peer code."""
    upstream = _FakeUpstream(
        close_code=4403, close_error=RuntimeError("close broke")
    )
    _patch_upstream(monkeypatch, upstream)

    with TestClient(_app()) as client:
        with client.websocket_connect(
            f"/api/v1/automation/profiles/{PROFILE}/cdp",
            headers={"Authorization": f"Bearer {TOKEN}"},
        ) as websocket:
            with pytest.raises(WebSocketDisconnect) as caught:
                websocket.receive_text()

    assert upstream.closed is True
    assert caught.value.code == 4403


# ---------------------------------------------------------------------------
# AC-004: Supervisor CDP proxy rejects a not-yet-running session.
# ---------------------------------------------------------------------------


def test_cdp_proxy_rejects_starting_session(tmp_path: Path):
    """AC-004: a restored session stuck at 'starting' gets CDP close 4404."""
    root = tmp_path / "data"
    root.mkdir(parents=True)
    token = "s" * 40
    token_file = tmp_path / "token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    core = SimpleNamespace(
        _token_file=token_file,
        socket_root=None,
        _sessions={
            "p1": SimpleNamespace(
                runtime_instance_id="i1", observed_state="starting"
            )
        },
        docker=SimpleNamespace(validator=PathValidator(root)),
    )
    app = create_control_app(core=core, token_file=token_file)

    with TestClient(app, base_url="http://supervisor") as client:
        with client.websocket_connect(
            "/supervisor/v1/profiles/p1/cdp",
            headers={"Authorization": f"bearer {token}"},
        ) as websocket:
            with pytest.raises(WebSocketDisconnect) as caught:
                websocket.receive_text()

    assert caught.value.code == 4404
