"""
Live Capture Policy Agent and Selkies WebRTC Service wrapper.
Arbitrates framerate (8 static / 30 active), pause/resume on visibility,
blocks client mutations, damage motion detection, and supervisor quota.
"""

import asyncio
import collections
import json
import logging
import math
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("cbrowser.stream_agent.policy")

# Client control verbs that mutate profile framerate, geometry, bitrate
FORBIDDEN_PEER_PREFIXES: Tuple[str, ...] = (
    "_arg_fps,",
    "r,",
    "s,",
    "_rc,",
    "_crf,",
    "vb,",
    "ab,",
)

# SETTINGS keys that clients are prohibited from overriding
DISALLOWED_SETTINGS_KEYS: Set[str] = {
    "framerate",
    "manual_width",
    "manual_height",
    "manual_resolution",
    "scaling_dpi",
    "video_streaming_mode",
    "force_aligned_resolution",
    "video_bitrate",
    "rate_control_mode",
    "video_crf",
}

# Maximum number of entries kept in action history ring buffer to prevent memory leak
MAX_HISTORY_SIZE: int = 500

_SAFE_CALLER_RE = re.compile(r"^[A-Za-z0-9_:\-]{1,64}$")


def _iso_now() -> str:
    """Return ISO8601 formatted timestamp with UTC timezone."""
    return datetime.now(timezone.utc).isoformat()


def _sanitize_caller(caller: Any) -> str:
    """Sanitize caller string to prevent log injection or arbitrary payloads."""
    if not isinstance(caller, str):
        return "unknown"
    s = caller.strip()
    if _SAFE_CALLER_RE.match(s):
        return s
    return "sanitized"


def sanitize_settings_message(msg: str) -> Optional[str]:
    """Strip framerate/geometry/bitrate overrides from client SETTINGS."""
    if not isinstance(msg, str) or not msg.startswith("SETTINGS,"):
        return msg
    try:
        payload = json.loads(msg.split(",", 1)[1])
        if not isinstance(payload, dict):
            return None
        for k in DISALLOWED_SETTINGS_KEYS:
            payload.pop(k, None)
        return "SETTINGS," + json.dumps(payload)
    except Exception:
        return None


def should_block_client_verb(msg: str) -> bool:
    """Check if message starts with forbidden client control verb."""
    if isinstance(msg, str):
        return msg.startswith(FORBIDDEN_PEER_PREFIXES)
    return False


class LiveCapturePolicyAgent:
    """
    Arbitrates video capture state for a single profile.
    - Locks video_streaming_mode = False (damage-gated).
    - Starts at 8 FPS upon resume (set8 before resume_screen_capture).
    - Elevates to 30 FPS when motion (>6 fps damage) or user input is observed.
    - Relaxes to 8 FPS when static.
    - Pauses capture completely when all viewers are hidden or gone.
    - Applies supervisor quota cap (min(quota, target)).
    - Tracks viewers via authenticated Gateway conn_id (single authority).
    """

    def __init__(
        self,
        service: Any = None,
        media_pipeline: Any = None,
        min_fps: float = 8.0,
        max_fps: float = 30.0,
        input_cooldown_sec: float = 2.0,
    ):
        self.service = service
        self._explicit_pipeline = media_pipeline
        self.min_fps = float(min_fps)
        self.max_fps = float(max_fps)
        self.input_cooldown_sec = float(input_cooldown_sec)

        self._control_lock = asyncio.Lock()
        self._is_paused = False
        self._current_fps = self.min_fps
        self._last_input_time: float = 0.0
        # Input events only mark this flag; the periodic reconciler applies it.
        # Creating one task per mouse move would flood the loop during drags.
        self._reconcile_pending: bool = False
        self._last_motion_time: float = 0.0
        self._resume_time: float = 0.0

        # Gateway authenticated viewers: conn_id -> {"active": bool, "tab_id": str}
        self.peers: Dict[str, Dict[str, Any]] = {}

        # Mapping between SDK peer_id and Gateway conn_id
        self._sdk_peer_to_conn: Dict[str, str] = {}
        self._conn_to_sdk_peer: Dict[str, str] = {}

        # Supervisor quota cap
        self._supervisor_fps_cap: Optional[float] = None

        # Damage stats tracking
        self._last_frames_count: int = 0
        self._has_screen_motion: bool = False
        self._last_stats_time: float = time.monotonic()
        self.motion_fps_estimate: float = 0.0

        # Async background tasks
        self._loop_task: Optional[asyncio.Task] = None
        self._motion_task: Optional[asyncio.Task] = None

        # Bounded action audit log
        self._action_history: collections.deque = collections.deque(
            maxlen=MAX_HISTORY_SIZE
        )

    @property
    def pipeline(self) -> Any:
        """
        Dynamically resolve active media pipeline.
        Always inspects service display_pipelines first so recreated pipelines
        are not shadowed by older pinned references.
        """
        if self.service is not None:
            dp = getattr(self.service, "display_pipelines", None)
            if dp is not None:
                if isinstance(dp, dict):
                    p = dp.get("primary")
                    if p is not None:
                        return p
                elif hasattr(dp, "__getitem__"):
                    try:
                        p = dp["primary"]
                        if p is not None:
                            return p
                    except (KeyError, TypeError, IndexError):
                        pass
            mp = getattr(self.service, "media_pipeline", None)
            if mp is not None:
                return mp
        if self._explicit_pipeline is not None:
            return self._explicit_pipeline
        return None

    def set_pipeline(self, pipeline: Any) -> None:
        """Explicitly set fallback media pipeline instance."""
        self._explicit_pipeline = pipeline

    def bind_service(self, service: Any) -> None:
        """Explicit hook to bind Selkies WebRTCService to this policy agent."""
        self.service = service
        service.policy_agent = self
        dp = getattr(service, "display_pipelines", None)
        if dp is not None:
            if isinstance(dp, dict) and "primary" in dp:
                self._explicit_pipeline = dp["primary"]
            elif hasattr(dp, "__getitem__"):
                try:
                    self._explicit_pipeline = dp["primary"]
                except (KeyError, TypeError, IndexError):
                    pass
        elif hasattr(service, "media_pipeline") and service.media_pipeline:
            self._explicit_pipeline = service.media_pipeline

    def register_peer_mapping(self, sdk_peer_id: str, conn_id: str) -> None:
        """Map SDK signaling peer_id to Gateway authenticated conn_id."""
        self.unregister_peer_mapping(sdk_peer_id=sdk_peer_id)
        self.unregister_peer_mapping(conn_id=conn_id)
        self._sdk_peer_to_conn[sdk_peer_id] = conn_id
        self._conn_to_sdk_peer[conn_id] = sdk_peer_id

    def unregister_peer_mapping(
        self,
        sdk_peer_id: Optional[str] = None,
        conn_id: Optional[str] = None,
    ) -> None:
        """Unmap SDK peer_id and Gateway conn_id."""
        if sdk_peer_id:
            c_id = self._sdk_peer_to_conn.pop(sdk_peer_id, None)
            if c_id:
                self._conn_to_sdk_peer.pop(c_id, None)
        if conn_id:
            p_id = self._conn_to_sdk_peer.pop(conn_id, None)
            if p_id:
                self._sdk_peer_to_conn.pop(p_id, None)

    def record_input(self) -> None:
        """Mark that a user input event (keyboard, mouse, IME) just occurred.

        The periodic reconciler consumes the pending flag, so high-frequency
        mouse input never creates one asyncio task per message.
        """
        self._last_input_time = time.monotonic()
        self._reconcile_pending = True

    def set_peer_active(
        self,
        peer_id: str,
        active: bool,
        tab_id: Optional[str] = None,
    ) -> None:
        """
        Record viewer visibility. Gateway conn_id is the primary identity.
        If an SDK peer_id is provided, resolve it to conn_id if mapped.
        """
        viewer_id = self._sdk_peer_to_conn.get(peer_id, peer_id)
        if viewer_id not in self.peers:
            self.peers[viewer_id] = {"active": active, "tab_id": tab_id or "unknown"}
        else:
            self.peers[viewer_id]["active"] = active
            if tab_id:
                self.peers[viewer_id]["tab_id"] = tab_id
        logger.info(
            "[%s] PolicyAgent: Viewer %s active -> %s (Total registered=%d)",
            _iso_now(),
            viewer_id,
            active,
            len(self.peers),
        )

    def set_viewer_visibility(self, viewer_id: str, is_visible: bool) -> None:
        """Set visibility for an authenticated Gateway viewer conn_id."""
        self.set_peer_active(viewer_id, is_visible)

    def remove_peer(self, peer_id: str) -> None:
        """Remove a viewer by SDK peer_id or Gateway conn_id."""
        viewer_id = self._sdk_peer_to_conn.get(peer_id, peer_id)
        self.peers.pop(viewer_id, None)
        self.unregister_peer_mapping(sdk_peer_id=peer_id, conn_id=viewer_id)
        logger.info(
            "[%s] PolicyAgent: Viewer %s departed (Remaining registered=%d)",
            _iso_now(),
            viewer_id,
            len(self.peers),
        )

    def remove_viewer(self, viewer_id: str) -> None:
        """Remove viewer by authenticated Gateway conn_id."""
        self.remove_peer(viewer_id)

    def set_supervisor_quota(self, fps_cap: Optional[float]) -> None:
        """
        Set or clear supervisor overload quota cap.
        Validates that quota is a positive, non-NaN finite number <= max_fps.
        """
        if fps_cap is not None:
            try:
                cap_val = float(fps_cap)
            except (ValueError, TypeError):
                logger.warning(
                    "[%s] PolicyAgent: Ignored invalid supervisor quota: %s",
                    _iso_now(),
                    fps_cap,
                )
                return

            if math.isnan(cap_val) or math.isinf(cap_val) or cap_val <= 0:
                logger.warning(
                    "[%s] PolicyAgent: Ignored non-positive/NaN supervisor quota: %s",
                    _iso_now(),
                    cap_val,
                )
                return

            bounded_cap = min(cap_val, self.max_fps)
            self._supervisor_fps_cap = bounded_cap
            logger.info(
                "[%s] PolicyAgent: Supervisor quota cap set to %.1f FPS",
                _iso_now(),
                self._supervisor_fps_cap,
            )
        else:
            self._supervisor_fps_cap = None
            logger.info("[%s] PolicyAgent: Supervisor quota cap cleared", _iso_now())

    def has_active_visible_viewers(self) -> bool:
        """Return True if any authenticated viewer is currently visible."""
        return any(st.get("active", False) for st in self.peers.values())

    def selkies_video_state(self) -> Tuple[int, bool]:
        """Unpaused primary video consumers and capture state, read from Selkies.

        Peer pause flags are set only by Selkies STOP_VIDEO/START_VIDEO handling.
        """
        consumers_of = getattr(self.service, "_display_consumers", None)
        consumers = consumers_of("primary") if consumers_of else []
        unpaused = sum(1 for peer in consumers if not peer.get("video_paused", False))
        p = self.pipeline
        capturing = bool(
            p is not None
            and hasattr(p, "is_screen_capturing")
            and p.is_screen_capturing()
        )
        return unpaused, capturing

    def log_action(self, action: str, details: Dict[str, Any]) -> None:
        """Log pipeline action to bounded ring buffer with ISO8601 timestamp."""
        entry = {
            "time": time.monotonic(),
            "timestamp": _iso_now(),
            "action": action,
            "details": details,
        }
        self._action_history.append(entry)
        logger.info("[%s] [POLICY_ACTION] %s: %s", _iso_now(), action, details)

    @property
    def action_history(self) -> List[Dict[str, Any]]:
        """Return snapshot of action history."""
        return list(self._action_history)

    async def start(self) -> None:
        """Start background reconciliation and damage monitoring loops."""
        logger.info(
            "[%s] Starting LiveCapturePolicyAgent background tasks...", _iso_now()
        )
        self._loop_task = asyncio.create_task(self._reconciliation_loop())
        self._motion_task = asyncio.create_task(self._motion_monitor_loop())

    async def stop(self) -> None:
        """Gracefully cancel and drain all background tasks."""
        logger.info(
            "[%s] Stopping LiveCapturePolicyAgent background tasks...", _iso_now()
        )
        tasks_to_cancel = []
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            tasks_to_cancel.append(self._loop_task)
        if self._motion_task and not self._motion_task.done():
            self._motion_task.cancel()
            tasks_to_cancel.append(self._motion_task)

        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        self._loop_task = None
        self._motion_task = None

    async def _motion_monitor_loop(self) -> None:
        """
        Damage-gated cumulative frame delta monitoring:
        Polls capture_module.stream_stats() without invoking rates().
        """
        try:
            while True:
                await asyncio.sleep(0.5)
                p = self.pipeline
                if not p:
                    continue
                is_capturing = (
                    p.is_screen_capturing()
                    if hasattr(p, "is_screen_capturing")
                    else not self._is_paused
                )
                if not is_capturing or not getattr(p, "capture_module", None):
                    self._has_screen_motion = False
                    continue

                try:
                    module = p.capture_module
                    if hasattr(module, "stream_stats"):
                        totals = module.stream_stats()
                        now = time.monotonic()
                        elapsed = now - self._last_stats_time
                        if totals and "frames" in totals and elapsed > 0.1:
                            cur_frames = totals["frames"]
                            delta = cur_frames - self._last_frames_count
                            self._last_frames_count = cur_frames
                            self._last_stats_time = now

                            fps = delta / elapsed
                            self.motion_fps_estimate = round(fps, 1)

                            if fps >= 6.0:
                                self._last_motion_time = now
                                self._has_screen_motion = True
                            else:
                                self._has_screen_motion = False
                except Exception as e:
                    logger.debug("[%s] Motion check exception: %s", _iso_now(), e)
        except asyncio.CancelledError:
            pass

    async def _reconciliation_loop(self) -> None:
        """Periodic arbitration tick routing into single serialized controller."""
        try:
            while True:
                await asyncio.sleep(0.2)
                await self.reconcile_capture_state(caller="periodic_reconciliation")
        except asyncio.CancelledError:
            pass

    async def reconcile_capture_state(
        self,
        caller: str = "",
        damage_frame_count: Optional[int] = None,
    ) -> None:
        """
        Unified, idempotent, serialized capture state controller.
        Protected by asyncio.Lock to eliminate dual-controller race conditions.
        """
        self._reconcile_pending = False
        safe_caller = _sanitize_caller(caller)
        async with self._control_lock:
            p = self.pipeline
            now = time.monotonic()
            active_peers = [pid for pid, st in self.peers.items() if st.get("active")]
            has_visible = len(active_peers) > 0

            # Determine whether pipeline is capturing
            is_capturing = True
            if p and hasattr(p, "is_screen_capturing"):
                is_capturing = p.is_screen_capturing()
            else:
                is_capturing = not self._is_paused

            # Rule 1: No active peers -> Pause capture if running
            if not has_visible:
                if is_capturing or not self._is_paused:
                    self.log_action(
                        "pause_screen_capture",
                        {
                            "reason": "all_peers_inactive_or_gone",
                            "caller": safe_caller,
                            "total_peers": len(self.peers),
                            "active_peers": 0,
                        },
                    )
                    if p and hasattr(p, "pause_screen_capture"):
                        await p.pause_screen_capture()
                    self._is_paused = True
                    logger.info(
                        "[%s] [SingleController] Capture safely paused (caller=%s)",
                        _iso_now(),
                        safe_caller,
                    )
                return

            # Rule 2: Has active peers, but capture is paused -> Resume capture
            if not is_capturing or self._is_paused:
                logger.info(
                    "[%s] [SingleController] Resuming capture: set_framerate(8.0) "
                    "first, then resume (caller=%s)",
                    _iso_now(),
                    safe_caller,
                )
                self.log_action(
                    "set_framerate",
                    {
                        "framerate": self.min_fps,
                        "reason": f"resume ({safe_caller})",
                        "pipeline_was_capturing": False,
                    },
                )
                if p and hasattr(p, "set_framerate"):
                    await p.set_framerate(self.min_fps)
                self._current_fps = self.min_fps

                self.log_action(
                    "resume_screen_capture",
                    {
                        "reason": f"resume ({safe_caller})",
                    },
                )
                if p and hasattr(p, "resume_screen_capture"):
                    await p.resume_screen_capture()
                self._is_paused = False
                self._resume_time = time.monotonic()

                # Request IDR on resume
                if self.service and hasattr(self.service, "request_idr_for_display"):
                    await self.service.request_idr_for_display("primary")
                elif p and hasattr(p, "request_idr_frame"):
                    p.request_idr_frame()

                logger.info(
                    "[%s] [SingleController] Capture safely resumed at %.1f FPS "
                    "(caller=%s)",
                    _iso_now(),
                    self.min_fps,
                    safe_caller,
                )
                return

            # Rule 3: Capture is currently running -> Reconcile dynamic 8/30 FPS
            has_input = (now - self._last_input_time) < self.input_cooldown_sec
            has_motion = (
                now - self._last_motion_time
            ) < self.input_cooldown_sec or self._has_screen_motion

            # Support external damage_frame_count injection in tests/simulations
            if damage_frame_count is not None:
                if self._last_stats_time > 0:
                    dt = now - self._last_stats_time
                    if dt > 0.05:
                        dframes = damage_frame_count - self._last_frames_count
                        damage_fps = dframes / dt
                        if damage_fps >= 6.0:
                            has_motion = True
                self._last_frames_count = damage_frame_count
                self._last_stats_time = now

            desired_fps = self.max_fps if (has_input or has_motion) else self.min_fps

            # Supervisor quota cap (min only)
            if self._supervisor_fps_cap is not None:
                desired_fps = min(desired_fps, self._supervisor_fps_cap)

            if abs(desired_fps - self._current_fps) > 0.1:
                self.log_action(
                    "set_framerate",
                    {
                        "framerate": desired_fps,
                        "reason": (
                            f"dynamic_rate (caller={safe_caller}, "
                            f"input={has_input}, motion={has_motion})"
                        ),
                        "pipeline_was_capturing": True,
                    },
                )
                if p and hasattr(p, "set_framerate"):
                    await p.set_framerate(desired_fps)
                self._current_fps = desired_fps
                logger.info(
                    "[%s] [SingleController] Policy Framerate update: %.1f FPS "
                    "(caller=%s, input=%s, motion=%s)",
                    _iso_now(),
                    desired_fps,
                    safe_caller,
                    has_input,
                    has_motion,
                )


def create_policy_controlled_service_class(base_cls: Any) -> Any:
    """Dynamically subclass WebRTCService to control policy."""

    class RealPolicyControlledWebRTCService(base_cls):
        FORBIDDEN_PEER_PREFIXES = FORBIDDEN_PEER_PREFIXES

        def __init__(self, supervisor: Any):
            super().__init__(supervisor)
            self.policy_agent: Optional[LiveCapturePolicyAgent] = None
            # Set by StreamAgent; pushes Gateway RTC config once RTCApp exists.
            self.rtc_ready_hook: Optional[Any] = None
            self._action_history: collections.deque = collections.deque(
                maxlen=MAX_HISTORY_SIZE
            )

        async def initialize_components(self) -> None:
            await super().initialize_components()
            # Stream-side TURN comes only from Gateway through the Agent;
            # Selkies' own RTC config monitors must not start or replace it.
            self.monitoring_utils_used = {}
            if self.rtc_ready_hook is not None:
                self.rtc_ready_hook()

        def mon_rtc_config(
            self, stun_servers: Any, turn_servers: Any, rtc_config: Any
        ) -> None:
            logger.debug("[%s] Ignored Selkies RTC config monitor update", _iso_now())

        def log_pipeline_action(self, action: str, details: Dict[str, Any]) -> None:
            entry = {
                "time": time.monotonic(),
                "timestamp": _iso_now(),
                "action": action,
                "details": details,
            }
            self._action_history.append(entry)
            logger.info("[%s] [ACTION_AUDIT] %s: %s", _iso_now(), action, details)

        def _on_peer_data_message(
            self,
            msg: Any,
            display_id: str = "primary",
            conn_id: Optional[str] = None,
        ) -> Any:
            """
            Input handler and protocol armor:
            1. Discard forbidden client tuning verbs.
            2. Sanitize SETTINGS packets to block framerate and geometry overrides.
            3. Detect keyboard, mouse, and native Chinese IME (co,end) input.
            4. Forward valid input unconditionally to input_handler.
            """
            if isinstance(msg, str):
                if msg.startswith(self.FORBIDDEN_PEER_PREFIXES):
                    logger.debug(
                        "[%s] Policy Guard: Blocked client verb: %s",
                        _iso_now(),
                        msg.split(",")[0],
                    )
                    return None
                if msg.startswith("SETTINGS,"):
                    sanitized = sanitize_settings_message(msg)
                    if not sanitized:
                        return None
                    msg = sanitized

            # Track user input activity (including native Chinese IME co,end)
            if isinstance(msg, str) and msg.startswith(
                ("kd,", "ku,", "m,", "m2,", "sf,", "sfe,", "co,")
            ):
                if self.policy_agent:
                    self.policy_agent.record_input()

            # Unconditionally pass through to X11 input handler (NO LEASE LOCK!)
            return super()._on_peer_data_message(msg, display_id, conn_id=conn_id)

        async def handle_session_start(
            self,
            session_peer_id: str,
            client_type: str,
            client_token: Optional[str] = None,
            display_id: str = "primary",
            display_position: str = "right",
            fullcolor_codecs: Optional[list] = None,
            tenbit_codecs: Optional[list] = None,
        ) -> None:
            """
            SDK session start: registers the peer connection with base service.
            Does NOT invent ghost viewers; visibility comes from mapped Selkies peers.
            Updates pipeline reference when display_pipelines becomes available.
            """
            await super().handle_session_start(
                session_peer_id,
                client_type,
                client_token=client_token,
                display_id=display_id,
                display_position=display_position,
                fullcolor_codecs=fullcolor_codecs,
                tenbit_codecs=tenbit_codecs,
            )
            if (
                self.policy_agent
                and hasattr(self, "display_pipelines")
                and "primary" in self.display_pipelines
            ):
                self.policy_agent.set_pipeline(self.display_pipelines["primary"])

        def setup_callbacks(self) -> None:
            """Ensure Selkies rtc_app callbacks hook into our policy controller."""
            super().setup_callbacks()
            if hasattr(self, "rtc_app") and self.rtc_app:
                self.rtc_app.on_video_consumer_active = (
                    self.handle_video_consumer_active
                )
                self.rtc_app.on_consumers_changed = self.handle_consumers_changed

        async def handle_video_consumer_active(
            self, peer_id: str, display_id: str, active: bool
        ) -> None:
            """
            Data-channel STOP_VIDEO / START_VIDEO:
            Only gates this specific peer's video RTP sender.
            Does NOT invent SDK ghost viewers in Policy Agent without mapping.
            """
            logger.info(
                "[%s] Hooked handle_video_consumer_active: peer=%s, active=%s",
                _iso_now(),
                peer_id,
                active,
            )
            display_id = display_id or "primary"
            peer = self.rtc_app.peer_connections.get(peer_id) if self.rtc_app else None
            if peer:
                peer["video_paused"] = not active
                sender = peer.get("video_sender")
                if sender is not None:
                    sender._enabled = active

            pipeline = (
                self.display_pipelines.get(display_id)
                if hasattr(self, "display_pipelines")
                else None
            )
            if (
                active
                and pipeline
                and hasattr(pipeline, "is_screen_capturing")
                and pipeline.is_screen_capturing()
            ):
                logger.info(
                    "[%s] Peer %s resumed while capture is active; requesting IDR",
                    _iso_now(),
                    peer_id,
                )
                await self.request_idr_for_display(display_id)

            if self.policy_agent:
                # ONLY update mapped Gateway viewer; never create unmapped SDK ghosts
                mapped_conn = self.policy_agent._sdk_peer_to_conn.get(peer_id)
                if mapped_conn and mapped_conn in self.policy_agent.peers:
                    self.policy_agent.set_viewer_visibility(mapped_conn, active)
                await self.policy_agent.reconcile_capture_state(
                    caller="handle_video_consumer_active"
                )

        async def handle_consumers_changed(self, display_id: str) -> None:
            """A peer joined or left a display's consumer set."""
            display_id = display_id or "primary"
            pipeline = (
                self.display_pipelines.get(display_id)
                if hasattr(self, "display_pipelines")
                else None
            )
            if (
                pipeline
                and hasattr(pipeline, "is_screen_capturing")
                and pipeline.is_screen_capturing()
            ):
                await self.request_idr_for_display(display_id)

            if self.policy_agent:
                await self.policy_agent.reconcile_capture_state(
                    caller="handle_consumers_changed"
                )

        async def handle_peer_gone(
            self, peer_id: str, peer: Optional[Dict[str, Any]] = None
        ) -> None:
            """Hook into peer departure."""
            logger.info("[%s] Hooked handle_peer_gone: peer=%s", _iso_now(), peer_id)
            if self.policy_agent:
                mapped_conn = self.policy_agent._sdk_peer_to_conn.get(peer_id)
                if mapped_conn:
                    self.policy_agent.remove_viewer(mapped_conn)
            await super().handle_peer_gone(peer_id, peer)
            if self.policy_agent:
                await self.policy_agent.reconcile_capture_state(
                    caller="handle_peer_gone"
                )

        async def _resume_display_capture(
            self,
            display_id: str,
            pipeline: Any,
            why: str,
            idr_always: bool = False,
        ) -> None:
            """Route external resume calls into single serialized policy controller."""
            if self.policy_agent:
                await self.policy_agent.reconcile_capture_state(
                    caller=f"_resume_display_capture:{why}"
                )

    return RealPolicyControlledWebRTCService
