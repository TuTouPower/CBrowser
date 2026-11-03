"""Lifecycle and identity regressions against the actual StreamAgent coordinator."""

import asyncio
from types import SimpleNamespace

import pytest
from cbrowser.stream_agent.agent import StreamAgent, ViewerWorkerEntry
from cbrowser.stream_agent.config import StreamAgentConfig
from cbrowser.stream_agent.policy import LiveCapturePolicyAgent
from cbrowser.stream_agent.protocol import GatewayRegisterResponse
from pydantic import ValidationError


def make_agent():
    return StreamAgent(
        StreamAgentConfig(
            profile_id="profile_a",
            runtime_instance_id="instance_a",
            gateway_url="ws://127.0.0.1:18800",
            agent_token="test_private_credential",
        )
    )


def test_registration_rejects_empty_session_identity():
    with pytest.raises(ValidationError):
        GatewayRegisterResponse.model_validate(
            {
                "version": "v2",
                "status": "ok",
                "profile_id": "profile_a",
                "runtime_instance_id": "instance_a",
                "agent_session_id": "",
            }
        )


def test_peer_correlation_requires_tab_and_resume_identity():
    agent = make_agent()
    service = SimpleNamespace(
        peer_manager=SimpleNamespace(
            peers={
                "sdk_a": SimpleNamespace(
                    peer_type="client",
                    tab_id="tab_a",
                    resume_key="resume_a",
                )
            }
        ),
        display_pipelines={},
    )
    agent.bind_webrtc_service(service)
    agent._correlate_sdk_peer("conn_a", "tab_a", "wrong_resume", None)
    assert "conn_a" not in agent.conn_id_to_sdk_peer_id
    agent._correlate_sdk_peer("conn_a", "tab_a", "resume_a", None)
    assert agent.conn_id_to_sdk_peer_id["conn_a"] == "sdk_a"


def test_superseded_sdk_peer_cannot_remove_replacement_viewer():
    policy = LiveCapturePolicyAgent()
    policy.set_viewer_visibility("conn", True)
    policy.register_peer_mapping("old_sdk", "conn")
    policy.register_peer_mapping("new_sdk", "conn")
    assert policy.has_sdk_peer_mapping("old_sdk") is False
    assert policy.sdk_peer_for_conn("conn") == "new_sdk"
    policy.remove_peer("old_sdk")
    assert policy.peers["conn"]["active"]


@pytest.mark.asyncio
async def test_stop_drains_owned_worker_and_reader_finalizers():
    agent = make_agent()
    started = [asyncio.Event(), asyncio.Event()]
    finalized = [asyncio.Event(), asyncio.Event()]

    async def owned_task(index):
        try:
            started[index].set()
            await asyncio.Future()
        finally:
            await asyncio.sleep(0)
            finalized[index].set()

    tasks = [asyncio.create_task(owned_task(i)) for i in range(2)]
    await asyncio.gather(*(event.wait() for event in started))
    agent.viewer_workers["conn"] = ViewerWorkerEntry(
        generation=1,
        task=tasks[0],
        queue=asyncio.Queue(),
        reader_task=tasks[1],
    )
    agent.policy.set_viewer_visibility("conn", True)
    try:
        await agent.stop()
        assert all(task.done() for task in tasks)
        assert all(event.is_set() for event in finalized)
        assert not agent.policy.peers
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_control_requires_current_registration():
    from cbrowser.stream_agent.protocol import GatewayControlEnvelope

    agent = make_agent()
    envelope = GatewayControlEnvelope(
        version="v2",
        action="supervisor_quota",
        profile_id="profile_a",
        runtime_instance_id="instance_a",
        agent_session_id="session_a",
        payload={"max_fps_cap": 15},
    )
    before = agent.policy._supervisor_fps_cap
    await agent._handle_control_packet(envelope)
    assert agent.policy.supervisor_fps_cap == before
    agent.agent_session_id = "session_a"
    await agent._handle_control_packet(envelope)
    assert agent.policy.supervisor_fps_cap == 15
    await agent.stop()


@pytest.mark.asyncio
async def test_queue_overflow_closes_gateway_viewer():
    import json

    from cbrowser.stream_agent.protocol import GatewayTunnelEnvelope

    class GatewaySocket:
        closed = False

        def __init__(self):
            self.messages = []

        async def send_str(self, message):
            self.messages.append(json.loads(message))

    agent = make_agent()
    agent.agent_session_id = "session_a"
    queue = asyncio.Queue(maxsize=1)
    queue.put_nowait("occupied")
    worker = asyncio.create_task(asyncio.sleep(60))
    agent.viewer_workers["conn_a"] = ViewerWorkerEntry(1, worker, queue)
    gateway = GatewaySocket()
    packet = GatewayTunnelEnvelope(
        version="v2",
        type="msg",
        profile_id="profile_a",
        runtime_instance_id="instance_a",
        agent_session_id="session_a",
        conn_id="conn_a",
        data="HELLO",
    )
    try:
        await agent._handle_tunnel_packet(None, gateway, packet)
        assert "conn_a" not in agent.viewer_workers
        assert worker.done()
        assert len(gateway.messages) == 1
        close = GatewayTunnelEnvelope.model_validate(gateway.messages[0])
        assert close.type == "close" and close.conn_id == "conn_a"
        assert close.code == 1013
        assert close.agent_session_id == "session_a"
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await agent.stop()


def test_missing_display_produces_safe_runtime_error(monkeypatch):
    from cbrowser.stream_agent.x11_keymap import _read_keymap

    monkeypatch.delenv("DISPLAY", raising=False)
    with pytest.raises(RuntimeError, match="X11 keyboard map query failed"):
        _read_keymap()


def test_peer_lookup_rejects_non_native_entry_shape():
    agent = make_agent()
    agent._webrtc_service = SimpleNamespace(
        rtc_app=SimpleNamespace(peer_connections={"sdk": {"pc": object()}})
    )
    agent.conn_id_to_sdk_peer_id["conn"] = "sdk"
    assert agent.get_peer_connection("conn") is None
