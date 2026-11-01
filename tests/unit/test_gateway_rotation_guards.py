"""Rotation generation pinning, expiry fail-closed, cancellation and close codes."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from cbrowser.gateway.rotation import (
    NoActiveGenerationError,
    PendingHandshake,
    RotationCoordinator,
)
from cbrowser.rtc_config.models import RtcScheduleParams
from cbrowser.rtc_config.service import RtcConfigService
from cbrowser.stream_agent.agent import StreamAgent
from cbrowser.stream_agent.protocol import (
    AgentAction,
    GatewayControlEnvelope,
    ProtocolEnvelope,
)


def _service(tmp_path, lifetime=10.0, interval=5.0, lead=2.0):
    secret = tmp_path / "turn_secret"
    secret.write_text("s" * 32, encoding="utf-8")
    return RtcConfigService(
        secret,
        ["turn:example.com:3478"],
        params=RtcScheduleParams(
            credential_lifetime_sec=lifetime,
            generation_interval_sec=interval,
            ice_restart_lead_time_sec=lead,
        ),
    )


def _coordinator(service):
    async def send_agent(_env):
        return None

    async def send_viewer(_conn, _frame):
        return None

    return RotationCoordinator(service, send_agent, send_viewer, lambda _pid: [], lambda _pid: None)


def test_expired_current_generation_fails_closed(tmp_path) -> None:
    coordinator = _coordinator(_service(tmp_path))
    coordinator.get_or_create_state("p1", now=0.0)
    assert coordinator.get_effective_generation("p1", now=1.0).generation == 1
    with pytest.raises(NoActiveGenerationError):
        coordinator.get_effective_generation("p1", now=11.0)


def test_stale_generation_offer_is_dropped(tmp_path) -> None:
    coordinator = _coordinator(_service(tmp_path))
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        coordinator._pending_offers["conn"] = PendingHandshake(future, 2, "p1")
        coordinator.handle_agent_restart_offer(
            ProtocolEnvelope(
                action=AgentAction.ICE_RESTART_OFFER,
                profile_id="p1",
                runtime_instance_id="i1",
                conn_id="conn",
                payload={"generation": 1, "sdp": "x"},
            )
        )
        assert not future.done()
        coordinator.handle_agent_restart_offer(
            ProtocolEnvelope(
                action=AgentAction.ICE_RESTART_OFFER,
                profile_id="p1",
                runtime_instance_id="i1",
                conn_id="conn",
                payload={"generation": 2, "sdp": "x"},
            )
        )
        assert future.done()
    finally:
        loop.close()


def test_new_connection_registered_as_migrated(tmp_path) -> None:
    coordinator = _coordinator(_service(tmp_path))
    state = coordinator.get_or_create_state("p1", now=0.0)
    state.in_progress_generation = coordinator.rtc_service.generate_generation(
        "p1", 2, now=1.0
    )
    coordinator.register_connection("p1", "c1", state.in_progress_generation)
    assert "c1" in state.migrated_connections


@pytest.mark.asyncio
async def test_cancel_profile_cancels_restarts_and_pending(tmp_path) -> None:
    coordinator = _coordinator(_service(tmp_path))
    state = coordinator.get_or_create_state("p1", now=0.0)
    sleeping = asyncio.create_task(asyncio.sleep(60))
    state.active_restarts["c1"] = sleeping
    offer = asyncio.get_running_loop().create_future()
    answer = asyncio.get_running_loop().create_future()
    coordinator._pending_offers["c1"] = PendingHandshake(offer, 2, "p1")
    coordinator._pending_answers["c1"] = PendingHandshake(answer, 2, "p1")

    await coordinator.cancel_profile("p1")

    assert sleeping.cancelled()
    assert offer.cancelled() and answer.cancelled()
    assert "c1" not in state.active_restarts
    assert "c1" not in coordinator._pending_offers


class _FakeGatewayWs:
    def __init__(self) -> None:
        self.closed = False
        self.sent: list[str] = []

    async def send_str(self, value: str) -> None:
        self.sent.append(value)


class _FakeUpstream:
    close_code = 4001

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


@pytest.mark.asyncio
async def test_upstream_4001_close_code_is_forwarded() -> None:
    agent = object.__new__(StreamAgent)
    agent.config = SimpleNamespace(profile_id="p1", runtime_instance_id="i1")
    agent.agent_session_id = "s1"
    agent.viewer_workers = {"c1": SimpleNamespace(generation=1)}
    agent._detached_upstreams = {}
    gateway = _FakeGatewayWs()

    await agent._upstream_reader(gateway, "c1", _FakeUpstream(), 1)

    assert gateway.sent
    envelope = json.loads(gateway.sent[-1])
    assert envelope["type"] == "close"
    assert envelope["code"] == 4001
