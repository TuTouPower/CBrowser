"""
Live in-process StreamAgent adapter and WebRTCService wrapper for Selkies 2.1.0.

Key Design:
1. Single Idempotent Serialized Capture Controller:
   - All pause, resume, and framerate changes route through `reconcile_capture_state()`
     protected by an `asyncio.Lock()` to eliminate dual-controller race conditions.
   - `handle_video_consumer_active`, `handle_consumers_changed`, `handle_peer_gone`, and
     the periodic `_reconciliation_loop` all invoke the same unified arbitration method.
   - When capture resumes from paused state, `pipeline.set_framerate(8.0)` is awaited and
     logged BEFORE `pipeline.resume_screen_capture()`.
   - Dynamic framerate changes are serialized with capture transitions so set8 and resume
     cannot be interleaved with concurrent 30 FPS updates.
   - Every physical API invocation is recorded in `_action_history` with full details.
   - No artificial 600ms grace period lock: low-FPS lock on recovery is removed; pipeline
     starts at 8 FPS upon resume and elevates naturally upon real motion or input.
   - Pausing preserves the real pipeline state; UDS fields reflect actual underlying status.

2. Protocol Armor (Preventing Profile Setting Mutation):
   - Overrides `_on_peer_data_message`:
     - Discards '_arg_fps,', 'r,', 's,', '_rc,', '_crf,', 'vb,', 'ab,' from clients.
     - Strips 'video_streaming_mode', 'framerate', 'manual_width', 'manual_height', 'scaling_dpi'
       from 'SETTINGS,' packets so clients cannot enable Turbo mode or alter geometry.
     - Unconditionally passes all keyboard ('kd,', 'ku,'), mouse ('m,', 'b,', 'w,'), and IME ('co,')
       messages to `input_handler` without acquiring any lease lock.

3. Damage-Gated Screen Motion Signal:
   - Locks `video_streaming_mode = False`.
   - Polls `capture_module.stream_stats()` totals['frames'] delta directly without calling `rates()`.
   - Real continuous motion generates multiple damage frames per second (> 6.0 fps).
   - Static scene generates 0 damage frames.
   - Low-frequency blink (0.5Hz) generates momentary 1-frame spikes, relaxing safely to 8 FPS.
"""
import asyncio
import json
import logging
import os
import sys
import time
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("live_policy_agent")

from selkies.webrtc_mode import WebRTCService
from selkies.webrtc_media_pipeline import MediaPipelinePixel

CONTROL_UDS_PATH = "/tmp/capture_policy_agent.sock"

class RealPolicyControlledWebRTCService(WebRTCService):
    FORBIDDEN_PEER_PREFIXES = ("_arg_fps,", "r,", "s,", "_rc,", "_crf,", "vb,", "ab,")

    def __init__(self, supervisor):
        super().__init__(supervisor)
        self.policy_agent: Optional['LiveCapturePolicyAgent'] = None
        self._action_history = []

    def log_pipeline_action(self, action: str, details: Dict[str, Any]):
        entry = {
            "time": time.monotonic(),
            "action": action,
            "details": details
        }
        self._action_history.append(entry)
        logger.info("[ACTION_AUDIT] %s: %s", action, details)

    def _on_peer_data_message(self, msg: Any, display_id: str = "primary", conn_id: Optional[str] = None) -> Any:
        if isinstance(msg, str):
            if msg.startswith(self.FORBIDDEN_PEER_PREFIXES):
                logger.debug("Policy Guard: Blocked client verb: %s", msg.split(",")[0])
                return None
            if msg.startswith("SETTINGS,"):
                try:
                    payload = json.loads(msg.split(",", 1)[1])
                    for k in ("framerate", "manual_width", "manual_height", "manual_resolution",
                              "scaling_dpi", "video_streaming_mode"):
                        payload.pop(k, None)
                    msg = "SETTINGS," + json.dumps(payload)
                except Exception:
                    return None

        # Track user input activity from real peer data channel
        if isinstance(msg, str) and msg.startswith(("kd,", "ku,", "m,", "b,", "w,", "co,")):
            if self.policy_agent:
                self.policy_agent.record_input()

        # Unconditionally pass through to X11 input handler (NO EXCLUSIVE LEASE!)
        return super()._on_peer_data_message(msg, display_id, conn_id=conn_id)

    async def handle_session_start(
        self, session_peer_id: str, client_type: str, client_token: Optional[str] = None,
        display_id: str = "primary", display_position: str = "right",
        fullcolor_codecs: Optional[list] = None,
        tenbit_codecs: Optional[list] = None,
    ) -> None:
        """Register newly joined peer as initially active in Policy Agent."""
        if self.policy_agent:
            self.policy_agent.set_peer_active(session_peer_id, True)
        await super().handle_session_start(
            session_peer_id, client_type, client_token=client_token,
            display_id=display_id, display_position=display_position,
            fullcolor_codecs=fullcolor_codecs, tenbit_codecs=tenbit_codecs
        )

    def setup_callbacks(self) -> None:
        super().setup_callbacks()
        self.rtc_app.on_video_consumer_active = self.handle_video_consumer_active
        self.rtc_app.on_consumers_changed = self.handle_consumers_changed

    async def handle_video_consumer_active(self, peer_id: str, display_id: str, active: bool) -> None:
        """Hook into official STOP_VIDEO / START_VIDEO data-channel verbs."""
        logger.info("Hooked handle_video_consumer_active: peer=%s, active=%s", peer_id, active)
        display_id = display_id or "primary"
        # Update peer's RTP sender
        peer = self.rtc_app.peer_connections.get(peer_id) if self.rtc_app else None
        if peer:
            peer["video_paused"] = not active
            sender = peer.get("video_sender")
            if sender is not None:
                sender._enabled = active

        # Delegate state tracking to Policy Agent
        if self.policy_agent:
            self.policy_agent.set_peer_active(peer_id, active)

        pipeline = self.display_pipelines.get(display_id)
        if active and pipeline and pipeline.is_screen_capturing():
            logger.info("Peer %s resumed while capture is already active; requesting IDR without disrupting framerate", peer_id)
            await self.request_idr_for_display(display_id)

        # Route all pause/resume decisions through the single serialized controller
        if self.policy_agent:
            await self.policy_agent.reconcile_capture_state(caller="handle_video_consumer_active")

    async def handle_consumers_changed(self, display_id: str) -> None:
        """A peer joined or left a display's consumer set."""
        display_id = display_id or "primary"
        pipeline = self.display_pipelines.get(display_id)
        if pipeline and pipeline.is_screen_capturing():
            await self.request_idr_for_display(display_id)

        # Route all pause/resume decisions through the single serialized controller
        if self.policy_agent:
            await self.policy_agent.reconcile_capture_state(caller="handle_consumers_changed")

    async def handle_peer_gone(self, peer_id: str, peer: Optional[Dict[str, Any]] = None) -> None:
        """Hook into peer departure."""
        logger.info("Hooked handle_peer_gone: peer=%s", peer_id)
        if self.policy_agent:
            self.policy_agent.remove_peer(peer_id)
        await super().handle_peer_gone(peer_id, peer)
        if self.policy_agent:
            await self.policy_agent.reconcile_capture_state(caller="handle_peer_gone")

    async def _resume_display_capture(self, display_id: str, pipeline: MediaPipelinePixel,
                                      why: str, idr_always: bool = False) -> None:
        """Route external resume calls into the single serialized controller."""
        if self.policy_agent:
            await self.policy_agent.reconcile_capture_state(caller=f"_resume_display_capture:{why}")


class LiveCapturePolicyAgent:
    def __init__(self, service: RealPolicyControlledWebRTCService):
        self.service = service
        self.service.policy_agent = self
        # peer_id -> {"active": bool, "tab_id": str}
        self.peers: Dict[str, Dict[str, Any]] = {}
        self.last_input_time = 0.0
        self.last_motion_time = 0.0
        self.resume_time = 0.0
        self.current_fps = 8.0
        self.idle_timeout = 2.0
        self._control_lock = asyncio.Lock()

        self._loop_task: Optional[asyncio.Task] = None
        self._motion_task: Optional[asyncio.Task] = None
        self._uds_server: Optional[asyncio.Server] = None
        
        self._last_frames_count = 0
        self._has_screen_motion = False
        self._last_stats_time = time.monotonic()
        self.motion_fps_estimate = 0.0

    @property
    def pipeline(self) -> Optional[MediaPipelinePixel]:
        return self.service.media_pipeline

    def record_input(self):
        self.last_input_time = time.monotonic()
        # Prompt quick framerate evaluation without waiting for reconciliation loop
        asyncio.get_event_loop().call_soon(
            lambda: asyncio.create_task(self.reconcile_capture_state(caller="record_input"))
        )

    def set_peer_active(self, peer_id: str, active: bool):
        tab_id = self.service._peer_tabs.get(peer_id, "unknown")
        self.peers[peer_id] = {"active": active, "tab_id": tab_id}
        logger.info("PolicyAgent: Peer %s (tab=%s) active -> %s (Total peers=%d)",
                    peer_id, tab_id, active, len(self.peers))

    def remove_peer(self, peer_id: str):
        self.peers.pop(peer_id, None)
        logger.info("PolicyAgent: Peer %s departed (Remaining peers=%d)", peer_id, len(self.peers))

    async def start(self):
        logger.info("Starting LiveCapturePolicyAgent...")
        self._loop_task = asyncio.create_task(self._reconciliation_loop())
        self._motion_task = asyncio.create_task(self._motion_monitor_loop())
        await self._start_control_server()

    async def stop(self):
        if self._loop_task: self._loop_task.cancel()
        if self._motion_task: self._motion_task.cancel()
        if self._uds_server: self._uds_server.close()

    async def reconcile_capture_state(self, caller: str = ""):
        """
        Unified, idempotent, serialized capture state controller.
        Protected by asyncio.Lock to prevent dual-controller race conditions.
        """
        async with self._control_lock:
            p = self.pipeline
            if not p or not p.is_media_pipeline_running():
                return

            now = time.monotonic()
            active_peers = [pid for pid, st in self.peers.items() if st.get("active")]
            is_capturing = p.is_screen_capturing()

            # Rule 1: No active peers (all hidden or disconnected) -> Pause capture if running
            if not active_peers:
                if is_capturing:
                    self.service.log_pipeline_action("pause_screen_capture", {
                        "reason": "all_peers_inactive_or_gone",
                        "caller": caller,
                        "total_peers": len(self.peers),
                        "active_peers": 0
                    })
                    stopped = await p.pause_screen_capture()
                    logger.info("[SingleController] Capture safely paused: stopped=%s (caller=%s)", stopped, caller)
                return

            # Rule 2: Has active peers, but capture is paused/stopped -> Resume capture
            if not is_capturing:
                logger.info("[SingleController] Resuming capture: set_framerate(8.0) first, then resume (caller=%s)", caller)
                # Set 8.0 FPS FIRST and record wrap action
                self.service.log_pipeline_action("set_framerate", {
                    "framerate": 8.0,
                    "reason": f"resume ({caller})",
                    "pipeline_was_capturing": False
                })
                await p.set_framerate(8.0)
                self.current_fps = 8.0

                # Resume screen capture and record wrap action
                self.service.log_pipeline_action("resume_screen_capture", {
                    "reason": f"resume ({caller})"
                })
                restarted = await p.resume_screen_capture()
                self.resume_time = time.monotonic()

                # Request IDR for display to ensure video starts immediately
                await self.service.request_idr_for_display("primary")
                logger.info("[SingleController] Capture safely resumed at 8.0 FPS (restarted=%s, caller=%s)", restarted, caller)
                return

            # Rule 3: Capture is currently running -> Reconcile dynamic 8/30 FPS
            has_input = (now - self.last_input_time) < self.idle_timeout
            has_motion = (now - self.last_motion_time) < self.idle_timeout

            desired_fps = 30.0 if (has_input or has_motion) else 8.0

            if desired_fps != self.current_fps and p.is_screen_capturing():
                self.service.log_pipeline_action("set_framerate", {
                    "framerate": desired_fps,
                    "reason": f"dynamic_rate (caller={caller}, input={has_input}, motion={has_motion})",
                    "pipeline_was_capturing": True
                })
                await p.set_framerate(desired_fps)
                self.current_fps = desired_fps
                logger.info("[SingleController] Policy Framerate update: %.1f -> %.1f FPS (caller=%s, input=%s, motion=%s, motion_est=%.1f)",
                            self.current_fps, desired_fps, caller, has_input, has_motion, self.motion_fps_estimate)

    async def _start_control_server(self):
        if os.path.exists(CONTROL_UDS_PATH):
            try: os.unlink(CONTROL_UDS_PATH)
            except OSError: pass

        async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            try:
                line = await reader.readline()
                if not line: return
                req = json.loads(line.decode())
                cmd = req.get("cmd")
                resp = {"status": "ok"}
                p = self.pipeline
                if cmd == "record_input":
                    self.record_input()
                elif cmd == "get_state":
                    active_peers = [pid for pid, st in self.peers.items() if st.get("active")]
                    resp = {
                        "status": "ok",
                        "current_fps": self.current_fps,
                        "pipeline_fps": getattr(p, "framerate", None) if p else None,
                        "is_screen_capturing": p.is_screen_capturing() if p else False,
                        "has_screen_motion": self._has_screen_motion,
                        "motion_fps_estimate": self.motion_fps_estimate,
                        "total_peers": len(self.peers),
                        "active_peers": len(active_peers),
                        "peer_details": self.peers,
                        "action_history": list(self.service._action_history)
                    }
                writer.write(json.dumps(resp).encode() + b"\n")
                await writer.drain()
            except Exception as e:
                logger.warning("UDS Control error: %s", e)
            finally:
                writer.close()

        self._uds_server = await asyncio.start_unix_server(handle_client, path=CONTROL_UDS_PATH)
        logger.info("Policy Control UDS listening on %s", CONTROL_UDS_PATH)

    async def _motion_monitor_loop(self):
        """
        Damage-gated cumulative frame delta monitoring:
        Reads capture_module.stream_stats() without invoking rates(), keeping official window intact.
        """
        while True:
            await asyncio.sleep(0.5)
            p = self.pipeline
            if not p or not p.is_screen_capturing() or not getattr(p, "capture_module", None):
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
                            self.last_motion_time = now
                            self._has_screen_motion = True
                        else:
                            self._has_screen_motion = False
            except Exception as e:
                logger.debug("Motion check exception: %s", e)

    async def _reconciliation_loop(self):
        """Periodic arbitration tick routing into the single serialized controller."""
        while True:
            await asyncio.sleep(0.2)
            await self.reconcile_capture_state(caller="periodic_reconciliation")
