"""t031 StreamAgent takeover flush: envelope shape + pending semantics."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from cbrowser.stream_agent.agent import StreamAgent
from cbrowser.stream_agent.protocol import validate_agent_envelope


class _FakeWs:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    async def send_str(self, text: str) -> None:
        self.sent.append(text)


def _bare_agent(ws=None) -> StreamAgent:
    agent = StreamAgent.__new__(StreamAgent)
    agent._gw_ws = ws
    agent._pending_takeovers = []
    agent.config = SimpleNamespace(
        profile_id="p1", runtime_instance_id="inst-1"
    )
    agent.agent_session_id = "stream-1"
    agent.log = SimpleNamespace(warning=lambda *a, **k: None)
    return agent


@pytest.mark.asyncio
async def test_flush_sends_valid_takeover_envelope():
    ws = _FakeWs()
    agent = _bare_agent(ws)
    agent._pending_takeovers.append(
        {"conn_id": "conn-7", "input_kind": "mouse_button"}
    )
    await agent._flush_takeovers()
    assert agent._pending_takeovers == []
    assert len(ws.sent) == 1
    envelope = validate_agent_envelope(json.loads(ws.sent[0]))
    assert envelope.action == "human_input_takeover"
    assert envelope.profile_id == "p1"
    assert envelope.runtime_instance_id == "inst-1"
    assert envelope.payload.input_kind == "mouse_button"
    assert envelope.payload.viewer_conn_id == "conn-7"


@pytest.mark.asyncio
async def test_report_queues_without_gateway_and_flushes_later():
    agent = _bare_agent(ws=None)
    agent.report_human_takeover("conn-1", "key")
    assert agent._pending_takeovers == [
        {"conn_id": "conn-1", "input_kind": "key"}
    ]
    # Gateway comes up: the pending report is flushed on next call.
    ws = _FakeWs()
    agent._gw_ws = ws
    await agent._flush_takeovers()
    assert agent._pending_takeovers == []
    assert len(ws.sent) == 1
    envelope = validate_agent_envelope(json.loads(ws.sent[0]))
    assert envelope.payload.input_kind == "key"


@pytest.mark.asyncio
async def test_flush_keeps_pending_on_send_failure():
    class _FailingWs:
        closed = False

        async def send_str(self, text: str) -> None:
            raise RuntimeError("socket closed")

    agent = _bare_agent(_FailingWs())
    agent._pending_takeovers.append({"conn_id": "conn-1", "input_kind": "wheel"})
    await agent._flush_takeovers()
    # Failed send stays pending for the next flush (never dropped).
    assert agent._pending_takeovers == [
        {"conn_id": "conn-1", "input_kind": "wheel"}
    ]
