"""
Unit tests for StreamAgent v2 registration fields, 10-second heartbeat rhythm,
reconnect backoff (1/2/4/8/16/30), RTC config push, and credential redaction.
"""

import asyncio
import importlib.metadata
import json
import logging
import os
import secrets
from unittest.mock import patch

import pytest
from aiohttp import WSMsgType, web
from cbrowser.stream_agent.agent import (
    ReconnectBackoff,
    StreamAgent,
    resolve_selkies_version,
)
from cbrowser.stream_agent.config import StreamAgentConfig
from cbrowser.stream_agent.protocol import (
    AgentAction,
    AgentHeartbeatPayload,
    AgentRegisterPayload,
    GatewayRegisterResponse,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def unique_port():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait_until(predicate, timeout: float = 2.0) -> None:
    """Yield to the loop until predicate is true, without fixed sleeps."""

    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(poll(), timeout)


class ManualClock:
    """Deterministic sleep seam injected into the agent module."""

    def __init__(self, *, block: bool = False) -> None:
        self.delays: list[float] = []
        self.block = block
        self.sleep_started = asyncio.Event()
        self.sleep_cancelled = False
        self._release = asyncio.Event()

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        self.sleep_started.set()
        if not self.block:
            await asyncio.sleep(0)
            return
        try:
            await self._release.wait()
        except asyncio.CancelledError:
            self.sleep_cancelled = True
            raise
        self._release.clear()

    def release_one(self) -> None:
        self._release.set()


class _ClockAsyncio:
    """Delegates to asyncio except sleep, confined to the patched module."""

    def __init__(self, clock: ManualClock) -> None:
        self._clock = clock

    def __getattr__(self, name: str):
        return getattr(asyncio, name)

    async def sleep(self, delay: float) -> None:
        await self._clock.sleep(delay)


def _inject_clock(monkeypatch, module, *, block: bool = False) -> ManualClock:
    clock = ManualClock(block=block)
    monkeypatch.setattr(module, "asyncio", _ClockAsyncio(clock))
    return clock


class MockGatewayServer:
    def __init__(self, port: int):
        self.port = port
        self.app = web.Application()
        self.app.router.add_get("/stream/agent/register", self._handle_register)
        self.app.router.add_get("/upstream", self._handle_upstream)
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self.received_messages: list[dict] = []
        self.active_ws: web.WebSocketResponse | None = None
        self.reject_registration: bool = False
        self.reject_remaining: int = 0
        self.reject_reason: str = "registration_rejected"
        self.close_on_heartbeat: bool = False
        self.agent_session_id = f"sess_{secrets.token_hex(8)}"
        self.on_message_callback = None

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", self.port)
        await self.site.start()

    async def stop(self):
        if self.active_ws and not self.active_ws.closed:
            await self.active_ws.close()
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

    async def _handle_register(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.active_ws = ws

        try:
            # 1. First message must be registration envelope
            raw = await ws.receive_str()
            msg = json.loads(raw)
            self.received_messages.append(msg)

            reject = self.reject_registration or self.reject_remaining > 0
            if self.reject_remaining > 0:
                self.reject_remaining -= 1
            if reject:
                resp = GatewayRegisterResponse(
                    version="v2",
                    status="error",
                    profile_id=msg.get("profile_id", "p1"),
                    runtime_instance_id=msg.get("runtime_instance_id", "inst1"),
                    agent_session_id=self.agent_session_id,
                    error=self.reject_reason,
                )
                await ws.send_str(resp.model_dump_json())
                await ws.close(code=1008, message=b"rejected")
                return ws

            resp = GatewayRegisterResponse(
                version="v2",
                status="ok",
                profile_id=msg["profile_id"],
                runtime_instance_id=msg["runtime_instance_id"],
                agent_session_id=self.agent_session_id,
            )
            await ws.send_str(resp.model_dump_json())

            # Message pump
            async for in_msg in ws:
                if in_msg.type == WSMsgType.TEXT:
                    parsed = json.loads(in_msg.data)
                    self.received_messages.append(parsed)
                    if self.on_message_callback:
                        await self.on_message_callback(parsed, ws)
                    if (
                        self.close_on_heartbeat
                        and parsed.get("action") == AgentAction.HEARTBEAT.value
                    ):
                        await ws.close()
                        break
                elif in_msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        except Exception as exc:  # noqa: BLE001 - mock gateway pump disconnect tolerance
            logger.debug("MockGateway message pump ended: %s", type(exc).__name__)
        return ws

    async def _handle_upstream(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for _ in ws:
            pass
        return ws


@pytest.mark.asyncio
async def test_config_requires_config_version(tmp_path):
    """CBROWSER_CONFIG_VERSION is mandatory in from_env; missing fails closed."""
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text(secrets.token_urlsafe(32))
    secret_file.chmod(0o600)

    base_env = {
        "CBROWSER_PROFILE_ID": "profile_req1",
        "CBROWSER_RUNTIME_INSTANCE_ID": "instance_req1",
        "CBROWSER_GATEWAY_URL": "ws://127.0.0.1:18090",
        "CBROWSER_AGENT_SECRET_FILE": str(secret_file),
        "CBROWSER_WEBRTC_PUBLIC_IP": "127.0.0.1",
    }

    # Missing CBROWSER_CONFIG_VERSION
    with patch.dict(os.environ, base_env, clear=True), pytest.raises(
        ValueError, match="CBROWSER_CONFIG_VERSION"
    ):
        StreamAgentConfig.from_env()

    # Invalid CBROWSER_CONFIG_VERSION
    with patch.dict(
        os.environ, {**base_env, "CBROWSER_CONFIG_VERSION": "not_int"}, clear=True
    ), pytest.raises(ValueError, match="CBROWSER_CONFIG_VERSION"):
        StreamAgentConfig.from_env()

    with patch.dict(
        os.environ, {**base_env, "CBROWSER_CONFIG_VERSION": "0"}, clear=True
    ), pytest.raises(ValueError, match="CBROWSER_CONFIG_VERSION"):
        StreamAgentConfig.from_env()

    # Valid CBROWSER_CONFIG_VERSION
    with patch.dict(
        os.environ, {**base_env, "CBROWSER_CONFIG_VERSION": "3"}, clear=True
    ):
        cfg = StreamAgentConfig.from_env()
        assert cfg.config_version == 3


@pytest.mark.asyncio
async def test_config_no_longer_requires_turn_settings(tmp_path):
    """Direct media needs no TURN host/port in the Agent configuration."""
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text(secrets.token_urlsafe(32))
    secret_file.chmod(0o600)

    base_env = {
        "CBROWSER_PROFILE_ID": "profile_req1",
        "CBROWSER_RUNTIME_INSTANCE_ID": "instance_req1",
        "CBROWSER_GATEWAY_URL": "ws://127.0.0.1:18090",
        "CBROWSER_AGENT_SECRET_FILE": str(secret_file),
        "CBROWSER_CONFIG_VERSION": "1",
    }
    with patch.dict(os.environ, base_env, clear=True):
        cfg = StreamAgentConfig.from_env()
    assert not hasattr(cfg, "turn_host")
    assert not hasattr(cfg, "turn_port")


@pytest.mark.asyncio
async def test_agent_registration_payload_fields(unique_port):
    """Agent registration payload must contain all Plan 7.2 fields."""
    gw = MockGatewayServer(unique_port)
    await gw.start()

    token = secrets.token_urlsafe(32)
    cfg = StreamAgentConfig(
        profile_id="profile_reg_test",
        runtime_instance_id="inst_reg_test_01",
        gateway_url=f"ws://127.0.0.1:{unique_port}",
        agent_token=token,
        udp_mux_port=30006,
        config_version=5,
        selkies_version="2.1.0",
    )

    agent = StreamAgent(
        config=cfg,
        upstream_url=f"ws://127.0.0.1:{unique_port}/upstream",
    )

    agent_task = asyncio.create_task(agent.connect_and_run())

    try:
        await _wait_until(lambda: agent.agent_session_id is not None)

        assert agent.agent_session_id == gw.agent_session_id
        assert len(gw.received_messages) >= 1

        reg_envelope = gw.received_messages[0]
        assert reg_envelope["action"] == AgentAction.REGISTER.value
        assert reg_envelope["profile_id"] == "profile_reg_test"
        assert reg_envelope["runtime_instance_id"] == "inst_reg_test_01"

        payload = reg_envelope["payload"]
        assert payload["profile_id"] == "profile_reg_test"
        assert payload["runtime_instance_id"] == "inst_reg_test_01"
        assert payload["selkies_version"] == "2.1.0"
        assert payload["runtime_state"] == "ready"
        assert payload["udp_port"] == 30006
        assert payload["config_version"] == 5
        # Verify payload validates strictly against AgentRegisterPayload
        validated = AgentRegisterPayload.model_validate(payload)
        assert validated.selkies_version == "2.1.0"
        assert validated.runtime_state == "ready"
        assert validated.config_version == 5
        assert "turn_host" not in validated.model_dump()
    finally:
        await agent.stop()
        agent_task.cancel()
        await gw.stop()


@pytest.mark.asyncio
async def test_agent_heartbeat_10s_rhythm(unique_port, monkeypatch):
    """Agent schedules HEARTBEAT every 10 seconds through its sleep seam.

    Payload includes runtime_state and viewer_count.
    """
    import cbrowser.stream_agent.agent as agent_module

    clock = _inject_clock(monkeypatch, agent_module)
    gw = MockGatewayServer(unique_port)
    await gw.start()

    cfg = StreamAgentConfig(
        profile_id="profile_hb_test",
        runtime_instance_id="inst_hb_01",
        gateway_url=f"ws://127.0.0.1:{unique_port}",
        agent_token=secrets.token_urlsafe(32),
        udp_mux_port=30006,
        config_version=1,
        selkies_version="2.1.0",
    )

    agent = StreamAgent(
        config=cfg,
        upstream_url=f"ws://127.0.0.1:{unique_port}/upstream",
    )

    agent_task = asyncio.create_task(agent.connect_and_run())

    try:
        await _wait_until(
            lambda: len(
                [
                    m
                    for m in gw.received_messages
                    if m.get("action") == AgentAction.HEARTBEAT.value
                ]
            )
            >= 2
        )

        hb_msgs = [
            m
            for m in gw.received_messages
            if m.get("action") == AgentAction.HEARTBEAT.value
        ]
        assert len(hb_msgs) >= 2
        assert agent.heartbeat_interval == 10.0
        assert clock.delays and all(delay == 10.0 for delay in clock.delays)

        for hb in hb_msgs:
            assert hb["profile_id"] == "profile_hb_test"
            assert hb["runtime_instance_id"] == "inst_hb_01"
            assert hb["agent_session_id"] == gw.agent_session_id
            payload = hb["payload"]
            assert payload["runtime_state"] == "ready"
            assert payload["viewer_count"] == 0
            validated = AgentHeartbeatPayload.model_validate(payload)
            assert validated.runtime_state == "ready"
            assert validated.viewer_count == 0
    finally:
        await agent.stop()
        agent_task.cancel()
        await gw.stop()


@pytest.mark.asyncio
async def test_heartbeat_loop_survives_a_single_state_exception(
    unique_port, monkeypatch
):
    """One failed Selkies state read must not stop the heartbeat schedule."""
    import cbrowser.stream_agent.agent as agent_module

    clock = _inject_clock(monkeypatch, agent_module)

    class FlakyStatePolicy:
        def __init__(self) -> None:
            self.calls = 0

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

        async def reconcile_capture_state(self, *args, **kwargs) -> None:
            pass

        def remove_viewer(self, viewer_id: str) -> None:
            pass

        def unregister_peer_mapping(self, **kwargs) -> None:
            pass

        def selkies_video_state(self) -> tuple[int, bool]:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("selkies state unavailable")
            return 0, False

    gw = MockGatewayServer(unique_port)
    await gw.start()
    policy = FlakyStatePolicy()
    cfg = StreamAgentConfig(
        profile_id="profile_hb_fault",
        runtime_instance_id="inst_hb_fault",
        gateway_url=f"ws://127.0.0.1:{unique_port}",
        agent_token=secrets.token_urlsafe(32),
        udp_mux_port=30006,
        config_version=1,
        selkies_version="2.1.0",
    )
    agent = StreamAgent(
        config=cfg,
        policy_agent=policy,
        upstream_url=f"ws://127.0.0.1:{unique_port}/upstream",
    )
    agent_task = asyncio.create_task(agent.connect_and_run())
    try:
        await _wait_until(
            lambda: policy.calls >= 2
            and any(
                m.get("action") == AgentAction.HEARTBEAT.value
                for m in gw.received_messages
            )
        )
        assert policy.calls >= 2
        assert clock.delays
    finally:
        await agent.stop()
        agent_task.cancel()
        await asyncio.gather(agent_task, return_exceptions=True)
        await gw.stop()


def test_reconnect_backoff_calculation():
    """Verify backoff sequence calculates 1, 2, 4, 8, 16, 30, 30... and resets to 1."""
    backoff = ReconnectBackoff()
    assert backoff.current() == 1.0

    expected_sequence = [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]
    actual_sequence = []
    for _ in range(len(expected_sequence)):
        actual_sequence.append(backoff.step())

    assert actual_sequence == expected_sequence
    assert backoff.current() == 30.0

    # Reset resets back to 1.0
    backoff.reset()
    assert backoff.current() == 1.0
    assert backoff.step() == 1.0
    assert backoff.current() == 2.0


@pytest.mark.asyncio
async def test_agent_reconnect_backoff_on_disconnect(unique_port, monkeypatch):
    """When registration is rejected, the agent applies 1/2/4/8/16/30 backoff."""
    import cbrowser.stream_agent.agent as agent_module

    clock = _inject_clock(monkeypatch, agent_module)
    gw = MockGatewayServer(unique_port)
    gw.reject_registration = True
    await gw.start()

    cfg = StreamAgentConfig(
        profile_id="profile_backoff_test",
        runtime_instance_id="inst_backoff_01",
        gateway_url=f"ws://127.0.0.1:{unique_port}",
        agent_token=secrets.token_urlsafe(32),
        udp_mux_port=30006,
        config_version=1,
        selkies_version="2.1.0",
    )

    agent = StreamAgent(
        config=cfg,
        upstream_url=f"ws://127.0.0.1:{unique_port}/upstream",
    )

    agent_task = asyncio.create_task(agent.connect_and_run())

    try:
        await _wait_until(lambda: len(clock.delays) >= 6)
        assert clock.delays[:6] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0]
    finally:
        await agent.stop()
        agent_task.cancel()
        await asyncio.gather(agent_task, return_exceptions=True)
        await gw.stop()


@pytest.mark.asyncio
async def test_agent_backoff_resets_after_successful_registration(
    unique_port, monkeypatch
):
    """A failure, then a success, then a disconnect restarts backoff at 1.0."""
    import cbrowser.stream_agent.agent as agent_module

    clock = _inject_clock(monkeypatch, agent_module)
    gw = MockGatewayServer(unique_port)
    gw.reject_remaining = 1
    gw.close_on_heartbeat = True
    await gw.start()

    cfg = StreamAgentConfig(
        profile_id="profile_reset_test",
        runtime_instance_id="inst_reset_01",
        gateway_url=f"ws://127.0.0.1:{unique_port}",
        agent_token=secrets.token_urlsafe(32),
        udp_mux_port=30006,
        config_version=1,
        selkies_version="2.1.0",
    )

    agent = StreamAgent(
        config=cfg,
        upstream_url=f"ws://127.0.0.1:{unique_port}/upstream",
    )

    agent_task = asyncio.create_task(agent.connect_and_run())

    try:
        await _wait_until(
            lambda: len(
                [d for d in clock.delays if d != agent.heartbeat_interval]
            )
            >= 2
        )
        reconnect_delays = [
            d for d in clock.delays if d != agent.heartbeat_interval
        ]
        assert reconnect_delays[:2] == [1.0, 1.0]
        assert agent.agent_session_id is None
    finally:
        await agent.stop()
        agent_task.cancel()
        await asyncio.gather(agent_task, return_exceptions=True)
        await gw.stop()


def test_selkies_version_comes_only_from_installed_distribution(monkeypatch):
    """An environment string must not be able to misreport the running Selkies."""
    monkeypatch.setenv("CBROWSER_SELKIES_VERSION", "9.9.9")
    try:
        installed = importlib.metadata.version("selkies")
    except importlib.metadata.PackageNotFoundError:
        installed = None
    if installed is None:
        with pytest.raises(RuntimeError):
            resolve_selkies_version()
    else:
        assert resolve_selkies_version() == installed
    assert resolve_selkies_version("2.1.0") == "2.1.0"


def test_agent_default_heartbeat_interval_is_ten_seconds():
    cfg = StreamAgentConfig(
        profile_id="profile_default_hb",
        runtime_instance_id="inst_default_hb",
        gateway_url="ws://127.0.0.1:1",
        agent_token=secrets.token_urlsafe(32),
        udp_mux_port=30007,
        config_version=1,
        selkies_version="2.1.0",
    )
    agent = StreamAgent(config=cfg, upstream_url="ws://127.0.0.1:1/upstream")
    assert agent.heartbeat_interval == 10.0


class _SelkiesVideoState:
    """The Selkies WebRTCService state the arbiter reads: consumers and capture."""

    def __init__(self, paused_flags: list[bool], capturing: bool):
        self.consumers = [
            {"display_id": "primary", "video_paused": paused} for paused in paused_flags
        ]
        self.capturing = capturing
        self.display_pipelines = {"primary": self}

    def _display_consumers(self, display_id: str) -> list[dict]:
        return [
            peer
            for peer in self.consumers
            if (peer.get("display_id") or "primary") == display_id
        ]

    def is_screen_capturing(self) -> bool:
        return self.capturing


def _state_agent(port: int, profile_id: str) -> StreamAgent:
    cfg = StreamAgentConfig(
        profile_id=profile_id,
        runtime_instance_id=f"{profile_id}_inst",
        gateway_url=f"ws://127.0.0.1:{port}",
        agent_token=secrets.token_urlsafe(32),
        udp_mux_port=30008,
        config_version=1,
        selkies_version="2.1.0",
    )
    return StreamAgent(config=cfg, upstream_url=f"ws://127.0.0.1:{port}/upstream")


def _heartbeats(gw: MockGatewayServer) -> list[dict]:
    return [
        m["payload"]
        for m in gw.received_messages
        if m.get("action") == AgentAction.HEARTBEAT.value
    ]


@pytest.mark.asyncio
async def test_first_heartbeat_follows_registration_with_selkies_video_state(
    unique_port,
):
    """Supervisor readiness reads the reported state, so it must not wait 10s."""
    gw = MockGatewayServer(unique_port)
    await gw.start()
    agent = _state_agent(unique_port, "profile_hb_first")
    agent.bind_webrtc_service(_SelkiesVideoState([False, True], capturing=True))
    task = asyncio.create_task(agent.connect_and_run())
    try:
        await _wait_until(lambda: bool(_heartbeats(gw)))
        beats = _heartbeats(gw)
        assert beats, "first heartbeat must not wait a full 10s interval"
        assert agent.heartbeat_interval == 10.0
        assert beats[0]["unpaused_video_consumers"] == 1
        assert beats[0]["capture_running"] is True
    finally:
        await agent.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await gw.stop()


@pytest.mark.asyncio
async def test_heartbeat_tracks_selkies_pause_state(unique_port, monkeypatch):
    import cbrowser.stream_agent.agent as agent_module

    clock = _inject_clock(monkeypatch, agent_module, block=True)
    gw = MockGatewayServer(unique_port)
    await gw.start()
    agent = _state_agent(unique_port, "profile_hb_track")
    state = _SelkiesVideoState([False, False], capturing=True)
    agent.bind_webrtc_service(state)
    task = asyncio.create_task(agent.connect_and_run())
    try:
        await _wait_until(lambda: bool(_heartbeats(gw)))
        assert _heartbeats(gw)[0]["unpaused_video_consumers"] == 2

        state.consumers[0]["video_paused"] = True
        state.consumers[1]["video_paused"] = True
        state.capturing = False
        seen = len(_heartbeats(gw))
        clock.release_one()
        await _wait_until(lambda: len(_heartbeats(gw)) > seen)
        latest = _heartbeats(gw)[-1]
        assert latest["unpaused_video_consumers"] == 0
        assert latest["capture_running"] is False
    finally:
        await agent.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await gw.stop()


@pytest.mark.asyncio
async def test_supervised_heartbeat_task_restarts_after_fatal_exit(monkeypatch):
    """Internal supervision restarts a heartbeat loop after a fatal escape."""
    cfg = StreamAgentConfig(
        profile_id="profile_hb_restart",
        runtime_instance_id="inst_hb_restart",
        gateway_url="ws://127.0.0.1:1",
        agent_token=secrets.token_urlsafe(32),
        udp_mux_port=30006,
        config_version=1,
        selkies_version="2.1.0",
    )
    agent = StreamAgent(config=cfg, upstream_url="ws://127.0.0.1:1/upstream")
    monkeypatch.setattr(agent, "_running", True)
    monkeypatch.setattr(agent, "agent_session_id", "session_hb_restart")

    class FakeWs:
        closed = False

    attempts = {"count": 0}
    delays: list[float] = []
    blocker = asyncio.Event()

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def heartbeat(ws) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("fatal heartbeat escape")
        await blocker.wait()

    monkeypatch.setattr(agent, "_sleep_fn", fake_sleep)
    monkeypatch.setattr(agent, "_heartbeat_loop", heartbeat)
    task = agent._start_heartbeat_task(FakeWs())
    try:
        await _wait_until(lambda: attempts["count"] >= 2)
        assert attempts["count"] >= 2
        assert delays == [1.0]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
