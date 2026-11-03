"""
Live Capture Policy Agent and Selkies WebRTC Service wrapper.
Arbitrates framerate (8 static / 30 active), pause/resume on visibility,
blocks client mutations, damage motion detection, and supervisor quota.
"""

from collections.abc import Callable
import asyncio
import collections
import logging
import math
import time
from typing import Any

from .policy_rules import (
    DISALLOWED_SETTINGS_KEYS,
    MAX_HISTORY_SIZE,
    sanitize_settings_message,
    should_block_client_verb,
)
from .policy_rules import (
    iso_now as _iso_now,
)
from .policy_rules import (
    sanitize_caller as _sanitize_caller,
)

__all__ = [
    "DISALLOWED_SETTINGS_KEYS",
    "LiveCapturePolicyAgent",
    "sanitize_settings_message",
    "should_block_client_verb",
]

logger = logging.getLogger("cbrowser.stream_agent.policy")


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
        clock: Callable[[], float] = time.monotonic,
    ):
        # Injectable clock (t024 AC-014/A43): tests pass a local callable
        # instead of patching the stdlib time module object.
        self._clock = clock
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
        self.peers: dict[str, dict[str, Any]] = {}

        # Mapping between SDK peer_id and Gateway conn_id
        self._sdk_peer_to_conn: dict[str, str] = {}
        self._conn_to_sdk_peer: dict[str, str] = {}

        # Supervisor quota cap
        self._supervisor_fps_cap: float | None = None

        # Damage stats tracking
        self._last_frames_count: int = 0
        self._has_screen_motion: bool = False
        self._last_stats_time: float = self._clock()
        self.motion_fps_estimate: float = 0.0

        # Async background tasks
        self._loop_task: asyncio.Task | None = None
        self._motion_task: asyncio.Task | None = None
        self._loop_sleep = asyncio.sleep

        # Bounded action audit log
        self._action_history: collections.deque = collections.deque(
            maxlen=MAX_HISTORY_SIZE
        )

    @property
    def supervisor_fps_cap(self) -> float | None:
        """Current supervisor-imposed FPS cap, if any."""
        return self._supervisor_fps_cap

    @property
    def is_running(self) -> bool:
        """Whether background policy loops are active."""
        return self._loop_task is not None and self._motion_task is not None

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

    def has_sdk_peer_mapping(self, sdk_peer_id: str) -> bool:
        """Whether an SDK peer is currently mapped to a Gateway connection."""
        return sdk_peer_id in self._sdk_peer_to_conn

    def sdk_peer_for_conn(self, conn_id: str) -> str | None:
        """Return the SDK peer currently mapped to a Gateway connection."""
        return self._conn_to_sdk_peer.get(conn_id)

    def unregister_peer_mapping(
        self,
        sdk_peer_id: str | None = None,
        conn_id: str | None = None,
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
        self._last_input_time = self._clock()
        self._reconcile_pending = True

    def set_peer_active(
        self,
        peer_id: str,
        active: bool,
        tab_id: str | None = None,
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
            "PolicyAgent: Viewer %s active -> %s (Total registered=%d)",
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
            "PolicyAgent: Viewer %s departed (Remaining registered=%d)",
            viewer_id,
            len(self.peers),
        )

    def remove_viewer(self, viewer_id: str) -> None:
        """Remove viewer by authenticated Gateway conn_id."""
        self.remove_peer(viewer_id)

    def set_supervisor_quota(self, fps_cap: float | None) -> None:
        """
        Set or clear the supervisor overload quota cap.

        One FPS rule with the protocol layer (SupervisorQuotaPayload): a
        cap must be finite and within [min_fps, max_fps]. Out-of-rule values
        are strictly rejected with ValueError and leave the current cap
        untouched; None is the only way to clear the cap.
        """
        if fps_cap is None:
            self._supervisor_fps_cap = None
            logger.info("PolicyAgent: Supervisor quota cap cleared")
            return
        try:
            cap_val = float(fps_cap)
        except (TypeError, ValueError):
            raise ValueError(
                f"Supervisor quota must be a number, got {type(fps_cap).__name__}"
            ) from None
        if (
            not math.isfinite(cap_val)
            or cap_val < self.min_fps
            or cap_val > self.max_fps
        ):
            raise ValueError(
                "Supervisor quota must be finite and within "
                f"[{self.min_fps}, {self.max_fps}] FPS"
            )
        self._supervisor_fps_cap = cap_val
        logger.info(
            "PolicyAgent: Supervisor quota cap set to %.1f FPS",
            self._supervisor_fps_cap,
        )

    def has_active_visible_viewers(self) -> bool:
        """Return True if any authenticated viewer is currently visible."""
        return any(st.get("active", False) for st in self.peers.values())

    def selkies_video_state(self) -> tuple[int, bool]:
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

    def log_action(self, action: str, details: dict[str, Any]) -> None:
        """Log pipeline action to bounded ring buffer with ISO8601 timestamp."""
        entry = {
            "time": self._clock(),
            "timestamp": _iso_now(),
            "action": action,
            "details": details,
        }
        self._action_history.append(entry)
        logger.info("[POLICY_ACTION] %s: %s", action, details)

    @property
    def action_history(self) -> list[dict[str, Any]]:
        """Return snapshot of action history."""
        return list(self._action_history)

    async def start(self) -> None:
        """Start background reconciliation and damage monitoring loops."""
        logger.info("Starting LiveCapturePolicyAgent background tasks...")
        self._loop_task = self._start_supervised_loop(
            "reconciliation", self._reconciliation_loop
        )
        self._motion_task = self._start_supervised_loop(
            "motion", self._motion_monitor_loop
        )

    def _start_supervised_loop(self, name: str, loop_factory: Any) -> asyncio.Task:
        """Run a loop; a fatal escape is logged and restarted with backoff."""

        async def supervised() -> None:
            delay = 1.0
            while True:
                try:
                    await loop_factory()
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - loop task restarts after any fatal iteration escape
                    logger.error(
                        "%s loop exited unexpectedly (%s); restarting in %.1fs",
                        name,
                        type(exc).__name__,
                        delay,
                    )
                    await self._loop_sleep(delay)
                    delay = min(delay * 2.0, 30.0)

        task = asyncio.create_task(supervised())
        task.add_done_callback(self._report_loop_done(name))
        return task

    def _report_loop_done(self, name: str):
        def report(task: asyncio.Task) -> None:
            if task.cancelled():
                return
            error = task.exception()
            if error is not None:
                logger.error(
                    "%s loop task terminated with %s", name, type(error).__name__
                )

        return report

    async def stop(self) -> None:
        """Gracefully cancel and drain all background tasks."""
        logger.info("Stopping LiveCapturePolicyAgent background tasks...")
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
                        now = self._clock()
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
                except Exception as e:  # noqa: BLE001 - motion check query exception non-fatal to monitoring loop
                    logger.debug("Motion check exception: %s", e)
        except asyncio.CancelledError:
            pass

    async def _reconciliation_loop(self) -> None:
        """Periodic arbitration tick routing into single serialized controller."""
        while True:
            await asyncio.sleep(0.2)
            try:
                await self.reconcile_capture_state(caller="periodic_reconciliation")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - one failed arbitration tick must not stop the loop
                logger.warning(
                    "Reconciliation tick failed (%s); continuing",
                    type(exc).__name__,
                )

    async def reconcile_capture_state(
        self,
        caller: str = "",
        damage_frame_count: int | None = None,
    ) -> None:
        """
        Unified, idempotent, serialized capture state controller.
        Protected by asyncio.Lock to eliminate dual-controller race conditions.
        """
        self._reconcile_pending = False
        safe_caller = _sanitize_caller(caller)
        async with self._control_lock:
            p = self.pipeline
            now = self._clock()
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
                        "[SingleController] Capture safely paused (caller=%s)",
                        safe_caller,
                    )
                return

            # Rule 2: Has active peers, but capture is paused -> Resume capture
            if not is_capturing or self._is_paused:
                logger.info(
                    "[SingleController] Resuming capture: set_framerate(8.0) "
                    "first, then resume (caller=%s)",
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
                self._resume_time = self._clock()

                # Request IDR on resume
                if self.service and hasattr(self.service, "request_idr_for_display"):
                    await self.service.request_idr_for_display("primary")
                elif p and hasattr(p, "request_idr_frame"):
                    p.request_idr_frame()

                logger.info(
                    "[SingleController] Capture safely resumed at %.1f FPS "
                    "(caller=%s)",
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
                    "[SingleController] Policy Framerate update: %.1f FPS "
                    "(caller=%s, input=%s, motion=%s)",
                    desired_fps,
                    safe_caller,
                    has_input,
                    has_motion,
                )


def create_policy_controlled_service_class(base_cls: Any) -> Any:
    """Dynamically subclass WebRTCService to control policy."""

    class RealPolicyControlledWebRTCService(base_cls):

        def __init__(self, supervisor: Any):
            super().__init__(supervisor)
            self.policy_agent: LiveCapturePolicyAgent | None = None
            self._action_history: collections.deque = collections.deque(
                maxlen=MAX_HISTORY_SIZE
            )

        def log_pipeline_action(self, action: str, details: dict[str, Any]) -> None:
            entry = {
                "time": time.monotonic(),
                "timestamp": _iso_now(),
                "action": action,
                "details": details,
            }
            self._action_history.append(entry)
            logger.info("[ACTION_AUDIT] %s: %s", action, details)

        def _on_peer_data_message(
            self,
            msg: Any,
            display_id: str = "primary",
            conn_id: str | None = None,
        ) -> Any:
            """
            Input handler and protocol armor:
            1. Discard forbidden client tuning verbs.
            2. Sanitize SETTINGS packets to block framerate and geometry overrides.
            3. Detect keyboard, mouse, and native Chinese IME (co,end) input.
            4. Forward valid input unconditionally to input_handler.
            """
            if isinstance(msg, str):
                if should_block_client_verb(msg):
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
            if (
                isinstance(msg, str)
                and msg.startswith(("kd,", "ku,", "m,", "m2,", "sf,", "sfe,", "co,"))
                and self.policy_agent
            ):
                self.policy_agent.record_input()

            # Unconditionally pass through to X11 input handler (NO LEASE LOCK!)
            return super()._on_peer_data_message(msg, display_id, conn_id=conn_id)

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
                "Hooked handle_video_consumer_active: peer=%s, active=%s",
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
                    "Peer %s resumed while capture is active; requesting IDR",
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
            self, peer_id: str, peer: dict[str, Any] | None = None
        ) -> None:
            """Hook into peer departure."""
            logger.info("Hooked handle_peer_gone: peer=%s", peer_id)
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
