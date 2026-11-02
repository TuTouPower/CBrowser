"""
Unit tests for LiveCapturePolicyAgent arbitration, protocol armor, damage-gated motion,
and RealPolicyControlledWebRTCService wrapper callbacks.
Verifies all AC-003 requirements without requiring native GStreamer/WebRTC binaries.
"""

import asyncio
import json
from typing import Any

import pytest
from cbrowser.stream_agent.policy import (
    DISALLOWED_SETTINGS_KEYS,
    LiveCapturePolicyAgent,
    create_policy_controlled_service_class,
    sanitize_settings_message,
    should_block_client_verb,
)


class MockCaptureModule:
    def __init__(self):
        self.frames = 0

    def stream_stats(self) -> dict[str, Any]:
        return {
            "frames": self.frames,
            "encode_ns": 1000000,
            "pipeline_ns": 2000000,
        }


class MockMediaPipeline:
    def __init__(self, framerate: float = 8.0, capturing: bool = True):
        self.framerate: float = framerate
        self._capturing: bool = capturing
        self.capture_module = MockCaptureModule()
        self.history: list[tuple] = []
        self.idr_requested: int = 0

    def is_screen_capturing(self) -> bool:
        return self._capturing

    async def set_framerate(self, fps: float) -> None:
        self.framerate = fps
        self.history.append(("set_framerate", fps))

    async def pause_screen_capture(self) -> bool:
        self._capturing = False
        self.history.append(("pause_screen_capture",))
        return True

    async def resume_screen_capture(self) -> bool:
        self._capturing = True
        self.history.append(("resume_screen_capture",))
        return True

    def request_idr_frame(self) -> None:
        self.idr_requested += 1
        self.history.append(("request_idr_frame",))


class MockWebRTCBaseService:
    def __init__(self, supervisor: Any = None):
        self.supervisor = supervisor
        self.display_pipelines: dict[str, Any] = {}
        self.media_pipeline: Any | None = None
        self.rtc_app: Any = None
        self.input_handler: Any = None
        self.idr_calls: list[str] = []
        self.forwarded_messages: list[tuple] = []

    def setup_callbacks(self) -> None:
        pass

    async def request_idr_for_display(self, display_id: str = "primary") -> None:
        self.idr_calls.append(display_id)

    def _on_peer_data_message(
        self,
        msg: Any,
        display_id: str = "primary",
        conn_id: str | None = None,
    ) -> Any:
        self.forwarded_messages.append((msg, display_id, conn_id))
        return "forwarded"

    async def handle_session_start(
        self,
        session_peer_id: str,
        client_type: str,
        client_token: str | None = None,
        display_id: str = "primary",
        display_position: str = "right",
        fullcolor_codecs: list | None = None,
        tenbit_codecs: list | None = None,
    ) -> None:
        pass

    async def handle_peer_gone(
        self,
        peer_id: str,
        peer: dict[str, Any] | None = None,
    ) -> None:
        pass


@pytest.mark.asyncio
async def test_policy_all_hidden_pauses_capture():
    """AC-003: All viewers hidden or gone pauses screen capture."""
    pipeline = MockMediaPipeline(framerate=8.0, capturing=True)
    agent = LiveCapturePolicyAgent(media_pipeline=pipeline, min_fps=8.0, max_fps=30.0)

    # When no viewers are registered, reconcile pauses
    await agent.reconcile_capture_state(caller="test")
    assert agent._is_paused is True
    assert pipeline.is_screen_capturing() is False
    assert ("pause_screen_capture",) in pipeline.history


@pytest.mark.asyncio
async def test_policy_resume_sets_8fps_before_resume_and_requests_idr():
    """AC-003: Recovery sets 8 FPS first, then resumes, then requests IDR."""
    pipeline = MockMediaPipeline(framerate=30.0, capturing=False)
    agent = LiveCapturePolicyAgent(media_pipeline=pipeline, min_fps=8.0, max_fps=30.0)
    agent._is_paused = True

    # Register visible viewer
    agent.set_viewer_visibility("viewer_auth_1", True)
    await agent.reconcile_capture_state(caller="test_resume")

    assert agent._is_paused is False
    assert pipeline.is_screen_capturing() is True
    assert pipeline.framerate == 8.0

    # Strict ordering: set_framerate(8.0) MUST precede resume_screen_capture
    actions = [h[0] for h in pipeline.history]
    assert "set_framerate" in actions
    assert "resume_screen_capture" in actions
    assert actions.index("set_framerate") < actions.index("resume_screen_capture")


@pytest.mark.asyncio
async def test_policy_continuous_motion_elevates_to_30_fps():
    """AC-003: Damage > 6 fps elevates target to 30 FPS without mouse/keyboard input."""
    pipeline = MockMediaPipeline(framerate=8.0, capturing=True)
    agent = LiveCapturePolicyAgent(media_pipeline=pipeline, min_fps=8.0, max_fps=30.0)
    agent.set_viewer_visibility("viewer_1", True)

    # Initialize stats baseline
    await agent.reconcile_capture_state(damage_frame_count=0)
    assert pipeline.framerate == 8.0

    # Simulate fast animation: 10 frames advance over 0.1s -> 100 fps damage
    await asyncio.sleep(0.1)
    await agent.reconcile_capture_state(damage_frame_count=10)
    assert pipeline.framerate == 30.0


@pytest.mark.asyncio
async def test_policy_static_relaxes_to_8_fps():
    """AC-003: Static screen relaxes back to 8 FPS when motion ceases."""
    pipeline = MockMediaPipeline(framerate=30.0, capturing=True)
    agent = LiveCapturePolicyAgent(
        media_pipeline=pipeline,
        min_fps=8.0,
        max_fps=30.0,
        input_cooldown_sec=0.1,  # Short cooldown for test
    )
    agent.set_viewer_visibility("viewer_1", True)
    agent.record_input()
    await agent.reconcile_capture_state()
    assert pipeline.framerate == 30.0

    # Wait for cooldown to expire and ensure static (no damage change)
    await asyncio.sleep(0.15)
    await agent.reconcile_capture_state(caller="static_check")
    assert pipeline.framerate == 8.0


@pytest.mark.asyncio
async def test_policy_background_viewer_cannot_lower_foreground():
    """AC-003: One background (hidden) viewer cannot reduce foreground viewer."""
    pipeline = MockMediaPipeline(framerate=8.0, capturing=True)
    agent = LiveCapturePolicyAgent(media_pipeline=pipeline, min_fps=8.0, max_fps=30.0)

    agent.set_viewer_visibility("viewer_foreground", True)
    agent.set_viewer_visibility("viewer_background", False)
    agent.record_input()

    await agent.reconcile_capture_state()
    assert pipeline.framerate == 30.0
    assert pipeline.is_screen_capturing() is True

    # Background viewer toggles hide/show repeatedly
    agent.set_viewer_visibility("viewer_background", False)
    await agent.reconcile_capture_state()
    assert pipeline.framerate == 30.0
    assert pipeline.is_screen_capturing() is True


@pytest.mark.asyncio
async def test_policy_supervisor_quota_enforcement_and_recovery():
    """AC-003: Supervisor quota bounds max FPS; removing quota recovers full rate."""
    pipeline = MockMediaPipeline(framerate=8.0, capturing=True)
    agent = LiveCapturePolicyAgent(media_pipeline=pipeline, min_fps=8.0, max_fps=30.0)
    agent.set_viewer_visibility("viewer_1", True)
    agent.record_input()  # Target 30

    # Enforce supervisor cap to 15 FPS
    agent.set_supervisor_quota(15.0)
    await agent.reconcile_capture_state()
    assert pipeline.framerate == 15.0

    # Enforce severe supervisor cap to 5 FPS (cannot elevate above 5)
    agent.set_supervisor_quota(5.0)
    await agent.reconcile_capture_state()
    assert pipeline.framerate == 5.0

    # Non-positive or NaN supervisor quota must be rejected
    agent.set_supervisor_quota(-1.0)
    assert agent._supervisor_fps_cap == 5.0
    agent.set_supervisor_quota(float("nan"))
    assert agent._supervisor_fps_cap == 5.0

    # Clear quota -> recovers back to active target 30
    agent.record_input()
    agent.set_supervisor_quota(None)
    await agent.reconcile_capture_state()
    assert pipeline.framerate == 30.0


def test_protocol_armor_forbidden_verbs():
    """AC-003: Forbidden client control verbs are blocked."""
    for verb in (
        "_arg_fps,30",
        "r,1920,1080",
        "s,1000",
        "_rc,crf",
        "_crf,28",
        "vb,4000",
        "ab,128",
    ):
        assert should_block_client_verb(verb) is True

    # User inputs are NOT blocked
    assert should_block_client_verb("kd,65") is False
    assert should_block_client_verb("ku,65") is False
    assert should_block_client_verb("m,500,500,0,0") is False
    assert should_block_client_verb("m2,10,20,0,0") is False
    assert should_block_client_verb("co,end,测试中文") is False


def test_protocol_armor_settings_sanitization():
    """AC-003: Client SETTINGS overrides for framerate, geometry are stripped."""
    payload = {
        "framerate": 60,
        "manual_width": 2560,
        "manual_height": 1440,
        "manual_resolution": "2560x1440",
        "scaling_dpi": 192,
        "video_streaming_mode": True,
        "video_bitrate": 8000,
        "rate_control_mode": "cbr",
        "video_crf": 18,
        "other_harmless_flag": "preserved",
    }
    raw = "SETTINGS," + json.dumps(payload)
    sanitized = sanitize_settings_message(raw)
    assert sanitized is not None
    data = json.loads(sanitized.split(",", 1)[1])

    for forbidden in DISALLOWED_SETTINGS_KEYS:
        assert forbidden not in data
    assert data.get("other_harmless_flag") == "preserved"


@pytest.mark.asyncio
async def test_service_wrapper_integration_and_callbacks():
    """Verify RealPolicyControlledWebRTCService wrapper hooks, callbacks."""
    ServiceClass = create_policy_controlled_service_class(MockWebRTCBaseService)
    svc = ServiceClass(supervisor=None)

    agent = LiveCapturePolicyAgent(min_fps=8.0, max_fps=30.0)
    agent.bind_service(svc)
    assert svc.policy_agent is agent

    pipeline = MockMediaPipeline(framerate=8.0, capturing=True)
    svc.display_pipelines["primary"] = pipeline
    svc.media_pipeline = pipeline

    # Test dynamic pipeline resolution via property
    assert agent.pipeline is pipeline

    # Test peer mapping registration (SDK peer <-> Gateway conn_id)
    agent.register_peer_mapping("sdk_peer_123", "gateway_conn_456")
    agent.set_viewer_visibility("gateway_conn_456", True)

    assert agent.has_active_visible_viewers() is True
    assert "gateway_conn_456" in agent.peers

    # Test _on_peer_data_message blocks forbidden verbs
    ret_blocked = svc._on_peer_data_message(
        "_arg_fps,60", display_id="primary", conn_id="sdk_peer_123"
    )
    assert ret_blocked is None
    assert len(svc.forwarded_messages) == 0

    # Test native Chinese IME input passes through unconditionally
    ret_ime = svc._on_peer_data_message(
        "co,end,你好世界", display_id="primary", conn_id="sdk_peer_123"
    )
    assert ret_ime == "forwarded"
    assert len(svc.forwarded_messages) == 1
    assert svc.forwarded_messages[0][0] == "co,end,你好世界"

    # Input recorded should trigger reconcile to 30 FPS
    await agent.reconcile_capture_state(caller="ime_test")
    assert pipeline.framerate == 30.0

    # Test peer departure via handle_peer_gone unregisters viewer
    await svc.handle_peer_gone("sdk_peer_123")
    assert "gateway_conn_456" not in agent.peers
    assert agent.has_active_visible_viewers() is False
    assert pipeline.is_screen_capturing() is False


@pytest.mark.asyncio
async def test_policy_stop_drains_background_tasks():
    """Verify agent stop cleanly cancels and awaits background tasks."""
    agent = LiveCapturePolicyAgent()
    await agent.start()
    assert agent._loop_task is not None
    assert agent._motion_task is not None

    await agent.stop()
    assert agent._loop_task is None
    assert agent._motion_task is None


def test_action_history_bounded():
    """Verify action history ring buffer is bounded to MAX_HISTORY_SIZE."""
    agent = LiveCapturePolicyAgent()
    for i in range(600):
        agent.log_action("test_action", {"index": i})
    assert len(agent.action_history) == 500
    assert agent.action_history[-1]["details"]["index"] == 599


def test_recreated_pipeline_dynamic_resolution():
    """Verify policy agent dynamically tracks recreated pipelines in service."""
    ServiceClass = create_policy_controlled_service_class(MockWebRTCBaseService)
    svc = ServiceClass(supervisor=None)
    agent = LiveCapturePolicyAgent()
    agent.bind_service(svc)

    pipe1 = MockMediaPipeline(framerate=8.0)
    svc.display_pipelines["primary"] = pipe1
    assert agent.pipeline is pipe1

    # SDK destroys and recreates primary pipeline
    pipe2 = MockMediaPipeline(framerate=8.0)
    svc.display_pipelines["primary"] = pipe2
    assert agent.pipeline is pipe2
