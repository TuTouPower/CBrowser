"""
Unit tests for StreamAgent policy, protocol, config, and security boundary.
Does not require GStreamer or WebRTC native binaries on host.
"""

import pytest
from cbrowser.stream_agent.config import StreamAgentConfig
from cbrowser.stream_agent.policy import (
    LiveCapturePolicyAgent,
    sanitize_settings_message,
    should_block_client_verb,
)
from cbrowser.stream_agent.protocol import AgentAction, ProtocolEnvelope


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
    assert agent._is_paused is True
    assert pipeline.is_paused is True


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

    assert agent._is_paused is False
    assert pipeline.is_paused is False

    # Check order: set_fps(8.0) MUST come before resume
    actions = [h[0] for h in pipeline.history]
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
    env = ProtocolEnvelope(
        action=AgentAction.REGISTER,
        profile_id="test_profile",
        runtime_instance_id="instance_test",
        payload={"udp_port": 30006},
    )
    dumped = env.model_dump_json()
    assert "test_profile" in dumped
    assert "register" in dumped


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
