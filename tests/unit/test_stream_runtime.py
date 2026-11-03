"""
Unit tests for StreamAgent policy, protocol, config, and security boundary.
Does not require GStreamer or WebRTC native binaries on host.
"""

import asyncio

import pytest
from cbrowser.stream_agent.config import StreamAgentConfig
from cbrowser.stream_agent.policy import (
    LiveCapturePolicyAgent,
    sanitize_settings_message,
    should_block_client_verb,
)
from cbrowser.stream_agent.protocol import AgentAction, AgentRegisterEnvelope


async def _wait_until(predicate, timeout: float = 2.0) -> None:
    """Yield to the loop until predicate is true, without fixed sleeps."""

    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(poll(), timeout)


class ManualClock:
    """Deterministic sleep seam injected into the policy module."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        await asyncio.sleep(0)


class _ClockAsyncio:
    def __init__(self, clock: ManualClock) -> None:
        self._clock = clock

    def __getattr__(self, name: str):
        return getattr(asyncio, name)

    async def sleep(self, delay: float) -> None:
        await self._clock.sleep(delay)


def _inject_clock(monkeypatch) -> ManualClock:
    import cbrowser.stream_agent.policy as policy_module

    clock = ManualClock()
    monkeypatch.setattr(policy_module, "asyncio", _ClockAsyncio(clock))
    return clock


class MockMediaPipeline:
    def __init__(self):
        self.framerate: float = 8.0
        self.is_paused: bool = False
        self.history = []

    async def set_framerate(self, fps: float):
        self.framerate = fps
        self.history.append(("set_fps", fps))

    async def pause_screen_capture(self):
        self.is_paused = True
        self.history.append(("pause",))

    async def resume_screen_capture(self):
        self.is_paused = False
        self.history.append(("resume",))


@pytest.mark.asyncio
async def test_policy_initial_state_and_pause_when_no_viewers():
    pipeline = MockMediaPipeline()
    agent = LiveCapturePolicyAgent(media_pipeline=pipeline, min_fps=8.0, max_fps=30.0)

    # When no viewers are registered, reconcile should pause screen capture
    await agent.reconcile_capture_state()
    assert agent.has_active_visible_viewers() is False
    assert pipeline.is_paused is True
    assert agent.action_history[-1]["action"] == "pause_screen_capture"


@pytest.mark.asyncio
async def test_policy_resume_sets_min_fps_before_resume():
    pipeline = MockMediaPipeline()
    agent = LiveCapturePolicyAgent(media_pipeline=pipeline, min_fps=8.0, max_fps=30.0)

    # Initially paused
    await agent.reconcile_capture_state()
    pipeline.history.clear()

    # Add visible viewer
    agent.set_viewer_visibility("viewer_1", True)
    await agent.reconcile_capture_state()

    assert pipeline.is_paused is False

    # Check order: set_fps(8.0) MUST come before resume
    actions = [h[0] for h in pipeline.history]
    logged_actions = [entry["action"] for entry in agent.action_history[-2:]]
    assert logged_actions == ["set_framerate", "resume_screen_capture"]
    assert "set_fps" in actions
    assert "resume" in actions
    assert actions.index("set_fps") < actions.index("resume")
    assert pipeline.framerate == 8.0


@pytest.mark.asyncio
async def test_policy_elevates_on_user_input():
    pipeline = MockMediaPipeline()
    agent = LiveCapturePolicyAgent(media_pipeline=pipeline, min_fps=8.0, max_fps=30.0)
    agent.set_viewer_visibility("viewer_1", True)
    await agent.reconcile_capture_state()
    assert pipeline.framerate == 8.0

    # User input recorded
    agent.record_input()
    await agent.reconcile_capture_state()
    assert pipeline.framerate == 30.0


@pytest.mark.asyncio
async def test_policy_supervisor_quota_caps_framerate():
    pipeline = MockMediaPipeline()
    agent = LiveCapturePolicyAgent(media_pipeline=pipeline, min_fps=8.0, max_fps=30.0)
    agent.set_viewer_visibility("viewer_1", True)
    agent.record_input()  # Target 30 FPS

    # Set supervisor quota to 15 FPS
    agent.set_supervisor_quota(15.0)
    await agent.reconcile_capture_state()

    assert pipeline.framerate == 15.0


def test_forbidden_client_verbs():
    assert should_block_client_verb("_arg_fps,30") is True
    assert should_block_client_verb("r,1920,1080") is True
    assert should_block_client_verb("s,1000") is True
    assert should_block_client_verb("kd,KeyA") is False
    assert should_block_client_verb("m,100,200") is False


def test_sanitize_settings_packet():
    raw = 'SETTINGS,{"framerate": 60, "manual_width": 2560, "other": "ok"}'
    sanitized = sanitize_settings_message(raw)
    assert sanitized is not None
    assert "60" not in sanitized
    assert "2560" not in sanitized
    assert "other" in sanitized


def test_protocol_envelope_serialization():
    env = AgentRegisterEnvelope(
        profile_id="test_profile",
        runtime_instance_id="instance_test",
        payload={
            "hostname": "stream-a",
            "profile_id": "test_profile",
            "runtime_instance_id": "instance_test",
            "udp_port": 30006,
            "selkies_version": "2.1.0",
            "runtime_state": "ready",
            "config_version": 1,
        },
    )
    dumped = env.model_dump_json()
    assert "test_profile" in dumped
    assert AgentAction.REGISTER.value in dumped


def test_config_validation_and_repr():
    # Valid config
    cfg = StreamAgentConfig(
        profile_id="p123",
        runtime_instance_id="instance_test",
        gateway_url="ws://127.0.0.1:18082",
        agent_token="super_secret_token",
        udp_mux_port=30006,
    )
    # Check repr does NOT leak agent_token
    rep = repr(cfg)
    assert "super_secret_token" not in rep
    assert "***" in rep

    # Invalid profile_id
    with pytest.raises(ValueError):
        StreamAgentConfig(
            profile_id="invalid/profile/path",
            runtime_instance_id="instance_test",
            gateway_url="ws://127.0.0.1:18082",
            agent_token="token",
        )

    # Invalid UDP port
    with pytest.raises(ValueError):
        StreamAgentConfig(
            profile_id="p123",
            runtime_instance_id="instance_test",
            gateway_url="ws://127.0.0.1:18082",
            agent_token="token",
            udp_mux_port=80,  # Below 1024
        )


@pytest.mark.asyncio
async def test_reconciliation_loop_survives_a_single_tick_exception(monkeypatch):
    """A failed arbitration tick is isolated; later ticks still run."""
    clock = _inject_clock(monkeypatch)
    pipeline = MockMediaPipeline()
    agent = LiveCapturePolicyAgent(media_pipeline=pipeline, min_fps=8.0, max_fps=30.0)
    calls = {"count": 0}
    original = agent.reconcile_capture_state

    async def flaky_tick(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("tick failed")
        return await original(*args, **kwargs)

    monkeypatch.setattr(agent, "reconcile_capture_state", flaky_tick)
    await agent.start()
    try:
        await _wait_until(lambda: calls["count"] >= 2)
        assert calls["count"] >= 2
        assert clock.delays
    finally:
        await agent.stop()


@pytest.mark.asyncio
async def test_supervised_policy_loop_restarts_after_fatal_exit(monkeypatch):
    """A fatal loop escape is restarted by the public start lifecycle."""
    clock = _inject_clock(monkeypatch)
    agent = LiveCapturePolicyAgent(media_pipeline=MockMediaPipeline())
    attempts = {"count": 0}
    blocker = asyncio.Event()

    async def fatal_then_block() -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("fatal loop escape")
        await blocker.wait()

    async def quiet_motion_loop() -> None:
        await blocker.wait()

    monkeypatch.setattr(agent, "_reconciliation_loop", fatal_then_block)
    monkeypatch.setattr(agent, "_motion_monitor_loop", quiet_motion_loop)
    await agent.start()
    try:
        await _wait_until(lambda: attempts["count"] >= 2)
        assert attempts["count"] >= 2
        assert clock.delays == [1.0]
    finally:
        await agent.stop()
