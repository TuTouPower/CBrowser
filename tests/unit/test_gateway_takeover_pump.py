"""t031 Gateway takeover pump: real app, real websocket, stub API.

Review t031_test_f001 (Gateway half): no test ever drove the
HUMAN_INPUT_TAKEOVER pump branch in gateway/server.py -- a dropped or
misrouted envelope would have stayed green. This file registers a real
Stream Agent against the real Gateway app (stub API client only) and
asserts the forward call and the pump's survival of a failed report.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from cbrowser.gateway.config import GatewayConfig
from cbrowser.gateway.server import create_gateway_app
from cbrowser.stream_agent.protocol import (
    AgentHumanInputTakeoverEnvelope,
    AgentRegisterEnvelope,
    AgentRegisterPayload,
    HumanInputTakeoverPayload,
)
from cbrowser.shared.agent_credentials import AgentCredentials


class _StubApi:
    """Stand-in for GatewayApiClient: records takeover reports."""

    def __init__(self, fail_first: bool = False):
        self.calls: list[tuple[str, str | None, str]] = []
        self.fail_first = fail_first

    async def get_profile_runtime(self, profile_id: str):
        return {"runtime_instance_id": "inst-1"}

    async def close(self) -> None:
        return None

    async def report_human_takeover(
        self, profile_id: str, conn_id: str | None, input_kind: str
    ):
        self.calls.append((profile_id, conn_id, input_kind))
        if self.fail_first and len(self.calls) == 1:
            return None
        return {"owner": "user"}


def _gateway_client(tmp_path: Path, api: _StubApi) -> TestClient:
    key_file = tmp_path / "agent.key"
    key_file.write_text("k" * 40, encoding="utf-8")
    key_file.chmod(0o600)
    token_file = tmp_path / "gateway.token"
    token_file.write_text("t" * 40, encoding="utf-8")
    token_file.chmod(0o600)
    api_token_file = tmp_path / "api.token"
    api_token_file.write_text("a" * 40, encoding="utf-8")
    api_token_file.chmod(0o600)
    config = GatewayConfig(
        agent_key_file=key_file,
        gateway_token_file=token_file,
        api_url="http://127.0.0.1:1",
        api_token_file=api_token_file,
        viewer_grant_key_file=api_token_file,
    )
    app = create_gateway_app(config, api_client=api)
    return TestClient(TestServer(app))


async def _register(ws, session_holder: dict) -> None:
    register = AgentRegisterEnvelope(
        profile_id="p1",
        runtime_instance_id="inst-1",
        payload=AgentRegisterPayload(
            hostname="test",
            profile_id="p1",
            runtime_instance_id="inst-1",
            udp_port=30006,
            selkies_version="2.1.0",
            runtime_state="ready",
            config_version=1,
        ),
    )
    await ws.send_str(register.model_dump_json())
    ack_raw = await asyncio.wait_for(ws.receive_str(), timeout=5)
    ack = json.loads(ack_raw)
    assert ack["status"] == "ok"
    session_holder["session_id"] = ack["agent_session_id"]


async def _wait_for_calls(api: _StubApi, count: int) -> None:
    for _ in range(100):
        if len(api.calls) >= count:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"expected {count} report calls, got {api.calls}")


@pytest.mark.asyncio
async def test_pump_forwards_takeover_to_api(tmp_path: Path):
    api = _StubApi()
    client = _gateway_client(tmp_path, api)
    await client.start_server()
    try:
        token = AgentCredentials(tmp_path / "agent.key").token_for(
            "p1", "inst-1"
        )
        ws = await client.ws_connect(
            "/stream/agent/register"
            "?profile_id=p1&runtime_instance_id=inst-1",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            holder: dict = {}
            await _register(ws, holder)
            takeover = AgentHumanInputTakeoverEnvelope(
                profile_id="p1",
                runtime_instance_id="inst-1",
                agent_session_id=holder["session_id"],
                payload=HumanInputTakeoverPayload(
                    input_kind="key", viewer_conn_id="conn-9"
                ),
            )
            await ws.send_str(takeover.model_dump_json())
            await _wait_for_calls(api, 1)
            assert api.calls == [("p1", "conn-9", "key")]
        finally:
            await ws.close()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pump_survives_failed_report(tmp_path: Path):
    api = _StubApi(fail_first=True)
    client = _gateway_client(tmp_path, api)
    await client.start_server()
    try:
        token = AgentCredentials(tmp_path / "agent.key").token_for(
            "p1", "inst-1"
        )
        ws = await client.ws_connect(
            "/stream/agent/register"
            "?profile_id=p1&runtime_instance_id=inst-1",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            holder: dict = {}
            await _register(ws, holder)
            for kind in ("key", "wheel"):
                takeover = AgentHumanInputTakeoverEnvelope(
                    profile_id="p1",
                    runtime_instance_id="inst-1",
                    agent_session_id=holder["session_id"],
                    payload=HumanInputTakeoverPayload(
                        input_kind=kind, viewer_conn_id="conn-9"
                    ),
                )
                await ws.send_str(takeover.model_dump_json())
            # The second report proves the pump kept running after the
            # first report failed (logged, never fatal).
            await _wait_for_calls(api, 2)
            assert api.calls == [
                ("p1", "conn-9", "key"),
                ("p1", "conn-9", "wheel"),
            ]
        finally:
            await ws.close()
    finally:
        await client.close()
