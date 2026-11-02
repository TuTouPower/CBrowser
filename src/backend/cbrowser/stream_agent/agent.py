"""
StreamAgent core coordinator and service runtime.
Connects outbound to Stream Gateway and manages the WebRTC signaling bridge.
"""

import asyncio
import importlib.metadata
import json
import logging
import os
import socket
import sys
import urllib.parse
from datetime import UTC, datetime
from typing import Any

import aiohttp
from aiohttp import WSMsgType

from .config import StreamAgentConfig
from .messaging import (
    build_heartbeat_envelope,
    build_register_envelope,
    build_register_payload,
    inject_controller_token,
    iso_now,
    normalize_close_code,
    parse_hello_metadata,
    tunnel_close_envelope,
    tunnel_message_envelope,
)
from .policy import (
    LiveCapturePolicyAgent,
    create_policy_controlled_service_class,
)
from .protocol import (
    MAX_STREAM_FRAME_SIZE,
    AgentAction,
    AgentHeartbeatPayload,
    GatewayControlEnvelope,
    GatewayRegisterResponse,
    GatewayTunnelEnvelope,
)

logger = logging.getLogger("stream_agent.core")

MAX_PAYLOAD_SIZE = 1024 * 1024
IO_TIMEOUT = 10.0
QUEUE_MAX_SIZE = 100
HEARTBEAT_INTERVAL = 30.0
# Keep the loopback Selkies session alive after a viewer tunnel closes so the
# official client can resume it with the same resume_key. The server-side hold
# is only 3s and is skipped entirely on a clean close; 10s covers the frontend's
# 5s reconnect window with margin without keeping abandoned sessions forever.
RESUME_GRACE_SECONDS = 10.0


class ISO8601Formatter(logging.Formatter):
    """Formats log record timestamps as strict ISO 8601 with UTC timezone."""

    def formatTime(
        self, record: logging.LogRecord, datefmt: str | None = None
    ) -> str:
        dt = datetime.fromtimestamp(record.created, UTC)
        return dt.isoformat()


def setup_service_logging(level: int = logging.INFO) -> None:
    """Configures root logger with ISO 8601 formatter."""
    formatter = ISO8601Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def _sanitize_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc += f":{parsed.port}"
            return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except ValueError:
        pass
    return url


class GatewayRegistrationError(RuntimeError):
    """Raised when registration handshake with Gateway fails or is rejected."""


BACKOFF_SCHEDULE: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0, 30.0)


class ReconnectBackoff:
    """Manages reconnect backoff delay: 1, 2, 4, 8, 16, 30, 30... seconds."""

    def __init__(
        self,
        steps: tuple[float, ...] = BACKOFF_SCHEDULE,
        max_delay: float = 30.0,
    ):
        self.steps = steps
        self.max_delay = max_delay
        self._index = 0

    def current(self) -> float:
        if self._index < len(self.steps):
            return self.steps[self._index]
        return self.max_delay

    def step(self) -> float:
        delay = self.current()
        if self._index < len(self.steps) - 1:
            self._index += 1
        else:
            self._index = len(self.steps) - 1
        return delay

    def reset(self) -> None:
        self._index = 0


def resolve_selkies_version(configured_version: str | None = None) -> str:
    """Report the installed Selkies distribution; tests may inject a version."""
    if configured_version:
        return configured_version
    try:
        return importlib.metadata.version("selkies")
    except importlib.metadata.PackageNotFoundError:
        raise RuntimeError("selkies distribution is not installed") from None


class ViewerWorkerEntry:
    """Tracks dedicated upstream worker with generation ownership."""

    def __init__(
        self,
        generation: int,
        task: asyncio.Task,
        queue: asyncio.Queue,
        reader_task: asyncio.Task | None = None,
        upstream_ws: aiohttp.ClientWebSocketResponse | None = None,
        tab_id: str | None = None,
        resume_key: str | None = None,
    ):
        self.generation = generation
        self.task = task
        self.queue = queue
        self.reader_task = reader_task
        self.upstream_ws = upstream_ws
        self.tab_id = tab_id
        self.resume_key = resume_key


class DetachedUpstream:
    """Selkies session kept open briefly after its viewer tunnel closed."""

    def __init__(
        self,
        upstream_ws: aiohttp.ClientWebSocketResponse,
        reader_task: asyncio.Task,
        timer_task: asyncio.Task,
    ):
        self.upstream_ws = upstream_ws
        self.reader_task = reader_task
        self.timer_task = timer_task


class StreamAgent:
    def __init__(
        self,
        config: StreamAgentConfig,
        policy_agent: LiveCapturePolicyAgent | None = None,
        upstream_url: str = "ws://127.0.0.1:18081",
        resume_grace_seconds: float = RESUME_GRACE_SECONDS,
    ):
        self.config = config
        self.policy = policy_agent or LiveCapturePolicyAgent(
            min_fps=config.min_fps,
            max_fps=config.max_fps,
        )
        self.upstream_url = upstream_url
        self.agent_session_id: str | None = None
        self._running = False
        self._gw_ws: aiohttp.ClientWebSocketResponse | None = None
        self._webrtc_service: Any = None

        # Monotonic generation counter preventing stale worker identity collision
        self._generation_counter = 0
        self.viewer_workers: dict[str, ViewerWorkerEntry] = {}
        self.conn_id_to_sdk_peer_id: dict[str, str] = {}
        self._detached_upstreams: dict[tuple[str, str], DetachedUpstream] = {}
        self._detached_generations: set[tuple[str, int]] = set()
        self._resume_grace_seconds = resume_grace_seconds
        self._backoff = ReconnectBackoff()
        self.heartbeat_interval: float = 10.0
        self._heartbeat_task: asyncio.Task | None = None
        self._sleep_fn = asyncio.sleep

    @property
    def viewer_queues(self) -> dict[str, asyncio.Queue]:
        return {k: v.queue for k, v in self.viewer_workers.items()}

    @property
    def viewer_tasks(self) -> dict[str, asyncio.Task]:
        return {k: v.task for k, v in self.viewer_workers.items()}

    def bind_webrtc_service(self, service: Any) -> None:
        """Binds WebRTCService and explicitly registers with policy_agent."""
        self._webrtc_service = service
        self.policy.bind_service(service)

    @property
    def peer_connections(self) -> dict[str, Any]:
        """Lookup peer_connections directly from Selkies service if available."""
        if (
            self._webrtc_service
            and hasattr(self._webrtc_service, "rtc_app")
            and self._webrtc_service.rtc_app
        ):
            return getattr(self._webrtc_service.rtc_app, "peer_connections", {})
        return {}

    def get_peer_connection(self, conn_id: str) -> Any | None:
        """Lookup RTCPeerConnection by gateway conn_id via mapped SDK peer ID."""
        sdk_peer_id = self.conn_id_to_sdk_peer_id.get(conn_id)
        if not sdk_peer_id:
            return None
        entry = self.peer_connections.get(sdk_peer_id)
        if entry is None:
            return None

        # Selkies 2.1.0 RTCApp._start_rtc_pipeline stores dict['peer_conn'].
        return entry.get("peer_conn") if isinstance(entry, dict) else None

    async def connect_and_run(self) -> None:
        """Outbound registration loop to Stream Gateway."""
        self._running = True
        query = urllib.parse.urlencode(
            {
                "profile_id": self.config.profile_id,
                "runtime_instance_id": self.config.runtime_instance_id,
            }
        )
        url = f"{self.config.gateway_url}/stream/agent/register?{query}"
        headers = {
            "Authorization": f"Bearer {self.config.agent_token.get_secret_value()}"
        }

        # Start policy background loops
        await self.policy.start()

        while self._running:
            try:
                logger.info(
                    "Connecting to Gateway at %s...",
                    _sanitize_url(url),
                )
                async with (
                    aiohttp.ClientSession() as session,
                    session.ws_connect(
                        url,
                        headers=headers,
                        max_msg_size=MAX_STREAM_FRAME_SIZE,
                        timeout=IO_TIMEOUT,
                        heartbeat=HEARTBEAT_INTERVAL,
                    ) as ws,
                ):
                    self._gw_ws = ws
                    logger.info(
                        "Connected to Gateway. Registering profile...",
                    )

                    selkies_ver = resolve_selkies_version(
                        self.config.selkies_version
                    )
                    reg_payload = build_register_payload(
                        self.config, socket.gethostname(), selkies_ver
                    )
                    reg_envelope = build_register_envelope(
                        self.config, reg_payload, iso_now()
                    )
                    await asyncio.wait_for(
                        ws.send_str(reg_envelope.model_dump_json()),
                        timeout=IO_TIMEOUT,
                    )
                    resp = await asyncio.wait_for(ws.receive(), timeout=IO_TIMEOUT)
                    if resp.type != WSMsgType.TEXT:
                        raise GatewayRegistrationError(
                            "Gateway registration: expected text response"
                        )

                    if len(resp.data.encode("utf-8")) > MAX_PAYLOAD_SIZE:
                        raise GatewayRegistrationError("Registration ACK oversized")

                    raw_ack = json.loads(resp.data)
                    ack = GatewayRegisterResponse.model_validate(raw_ack)
                    if ack.status != "ok":
                        err_detail = ack.error or "unknown"
                        raise GatewayRegistrationError(
                            f"Gateway registration rejected: {err_detail}"
                        )

                    if (
                        ack.profile_id != self.config.profile_id
                        or ack.runtime_instance_id
                        != self.config.runtime_instance_id
                    ):
                        raise GatewayRegistrationError(
                            "Registration ACK identity mismatch"
                        )

                    self.agent_session_id = ack.agent_session_id
                    self._backoff.reset()
                    logger.info(
                        "StreamAgent registered with Gateway",
                    )

                    # Start application heartbeat task
                    self._heartbeat_task = self._start_heartbeat_task(ws)

                    # Message pump
                    async for msg in ws:
                        if msg.type == WSMsgType.TEXT:
                            await self._handle_gateway_envelope(
                                session, ws, msg.data
                            )
                        elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                            logger.warning(
                                "Gateway connection closed or errored",
                            )
                            break
            except asyncio.CancelledError:
                break
            except GatewayRegistrationError as e:
                logger.error("%s", e)
            except Exception as e:  # noqa: BLE001 - gateway connection or registration transport failure retried via backoff
                logger.warning(
                    "Gateway connection error (%s)",
                    type(e).__name__,
                )
            finally:
                if self._heartbeat_task and not self._heartbeat_task.done():
                    self._heartbeat_task.cancel()
                    self._heartbeat_task = None
                self.agent_session_id = None
                await self._cleanup_all_viewers(caller="gateway_disconnect")

            if not self._running:
                break
            delay = self._backoff.step()
            logger.info("Reconnecting in %.1fs (backoff)...", delay)
            await self._sleep_fn(delay)

    def _start_heartbeat_task(
        self, ws: aiohttp.ClientWebSocketResponse
    ) -> asyncio.Task:
        async def supervised() -> None:
            delay = 1.0
            while self._running and not ws.closed:
                try:
                    await self._heartbeat_loop(ws)
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 - loop task restarts after any fatal iteration escape
                    logger.error(
                        "Heartbeat loop exited unexpectedly (%s); restarting in %.1fs",
                        type(e).__name__,
                        delay,
                    )
                    await self._sleep_fn(delay)
                    delay = min(delay * 2.0, 30.0)

        task = asyncio.create_task(supervised())
        task.add_done_callback(self._on_loop_task_done("heartbeat"))
        return task

    def _on_loop_task_done(self, name: str):
        def report(task: asyncio.Task) -> None:
            if task.cancelled():
                return
            error = task.exception()
            if error is not None:
                logger.error(
                    "%s loop task terminated with %s",
                    name,
                    type(error).__name__,
                )
            elif self._running and self.agent_session_id:
                logger.warning("%s loop task stopped while agent is running", name)

        return report

    async def _heartbeat_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Send HEARTBEAT right after registration, then every 10 seconds.

        Supervisor readiness reads the reported Selkies video state through
        Gateway, so the first report must not wait a full interval.
        """
        while self._running and self.agent_session_id and not ws.closed:
            try:
                unpaused, capturing = self.policy.selkies_video_state()
                hb_payload = AgentHeartbeatPayload(
                    runtime_state="ready",
                    viewer_count=len(self.viewer_workers),
                    unpaused_video_consumers=unpaused,
                    capture_running=capturing,
                )
                hb_envelope = build_heartbeat_envelope(
                    self.config,
                    self.agent_session_id,
                    hb_payload,
                    iso_now(),
                )
                await ws.send_str(hb_envelope.model_dump_json())
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - one failed heartbeat must not stop the schedule
                logger.warning(
                    "Heartbeat send failed (%s); retrying next interval",
                    type(e).__name__,
                )
            await self._sleep_fn(self.heartbeat_interval)

    async def _drain_workers(self, workers: list[ViewerWorkerEntry]) -> None:
        """Await owned tasks and sockets after invalidating their generations."""
        current = asyncio.current_task()
        tasks = {
            task
            for worker in workers
            for task in (worker.task, worker.reader_task)
            if task is not None and task is not current
        }
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(
            *(
                worker.upstream_ws.close()
                for worker in workers
                if worker.upstream_ws and not worker.upstream_ws.closed
            ),
            return_exceptions=True,
        )

    async def _cleanup_all_viewers(
        self, caller: str = "disconnect", *, detach: bool = True
    ) -> None:
        """Invalidate generations before draining or detaching viewers.

        A Gateway disconnect is exactly the reconnect case this path serves:
        the page's signaling socket dropped and the official client is about to
        come back with the same resume_key. Keep those Selkies sessions alive
        for the resume grace window. Agent shutdown closes them immediately.
        """
        if detach:
            for conn_id in list(self.viewer_workers):
                await self._detach_viewer(conn_id, caller=caller, reconcile=False)
        else:
            workers = list(self.viewer_workers.values())
            conn_ids = list(self.viewer_workers)
            self.viewer_workers.clear()
            for conn_id in conn_ids:
                sdk_id = self.conn_id_to_sdk_peer_id.pop(conn_id, None)
                self.policy.unregister_peer_mapping(
                    sdk_peer_id=sdk_id, conn_id=conn_id
                )
                self.policy.remove_viewer(conn_id)
            await self._drain_workers(workers)
        await self.policy.reconcile_capture_state(caller=caller)

    async def _detach_viewer(
        self,
        conn_id: str,
        *,
        caller: str = "viewer_tunnel_close",
        reconcile: bool = True,
    ) -> None:
        """Drop the viewer but keep its Selkies upstream open for resume."""
        worker = self.viewer_workers.pop(conn_id, None)
        sdk_id = self.conn_id_to_sdk_peer_id.pop(conn_id, None)
        if sdk_id:
            self.policy.unregister_peer_mapping(
                sdk_peer_id=sdk_id, conn_id=conn_id
            )
        self.policy.remove_viewer(conn_id)

        keep = bool(
            worker
            and worker.tab_id
            and worker.resume_key
            and worker.upstream_ws
            and not worker.upstream_ws.closed
            and worker.reader_task
            and not worker.reader_task.done()
        )
        if not keep:
            if worker:
                await self._drain_workers([worker])
            if reconcile:
                await self.policy.reconcile_capture_state(caller=caller)
            return

        assert worker is not None
        assert worker.upstream_ws is not None
        assert worker.reader_task is not None
        assert worker.tab_id is not None and worker.resume_key is not None
        key = (worker.tab_id, worker.resume_key)
        previous = self._detached_upstreams.pop(key, None)
        if previous is not None:
            await self._close_detached(previous)

        self._detached_generations.add((conn_id, worker.generation))
        if worker.task and not worker.task.done():
            worker.task.cancel()
            await asyncio.gather(worker.task, return_exceptions=True)
        else:
            self._detached_generations.discard((conn_id, worker.generation))

        timer = asyncio.create_task(
            self._expire_detached(key, worker.upstream_ws, worker.reader_task)
        )
        self._detached_upstreams[key] = DetachedUpstream(
            worker.upstream_ws, worker.reader_task, timer
        )
        logger.info(
            "Viewer tunnel closed; holding Selkies session for %.0fs resume",
            self._resume_grace_seconds,
        )
        if reconcile:
            await self.policy.reconcile_capture_state(caller=caller)

    async def _expire_detached(
        self,
        key: tuple[str, str],
        upstream_ws: aiohttp.ClientWebSocketResponse,
        reader_task: asyncio.Task,
    ) -> None:
        try:
            await asyncio.sleep(self._resume_grace_seconds)
            entry = self._detached_upstreams.get(key)
            if entry is None or entry.upstream_ws is not upstream_ws:
                return
            self._detached_upstreams.pop(key, None)
            await self._close_detached(entry, cancel_timer=False)
        except asyncio.CancelledError:
            pass

    async def _close_detached(
        self, entry: DetachedUpstream, *, cancel_timer: bool = True
    ) -> None:
        if cancel_timer and entry.timer_task and not entry.timer_task.done():
            entry.timer_task.cancel()
        if not entry.upstream_ws.closed:
            try:
                await entry.upstream_ws.close()
            except Exception as exc:  # noqa: BLE001 - best-effort closing of detached upstream websocket
                logger.debug(
                    "Failed closing detached upstream ws: %s", type(exc).__name__
                )
        if entry.reader_task and not entry.reader_task.done():
            entry.reader_task.cancel()
            await asyncio.gather(entry.reader_task, return_exceptions=True)

    async def _close_all_detached_upstreams(self) -> None:
        entries = list(self._detached_upstreams.values())
        self._detached_upstreams.clear()
        await asyncio.gather(
            *(self._close_detached(entry) for entry in entries),
            return_exceptions=True,
        )

    def _release_detached_upstream(
        self, upstream_ws: aiohttp.ClientWebSocketResponse
    ) -> None:
        for key, entry in list(self._detached_upstreams.items()):
            if entry.upstream_ws is upstream_ws:
                self._detached_upstreams.pop(key, None)
                if entry.timer_task and not entry.timer_task.done():
                    entry.timer_task.cancel()
                break

    async def _handle_gateway_envelope(
        self,
        session: aiohttp.ClientSession,
        gw_ws: aiohttp.ClientWebSocketResponse,
        raw_data: str,
    ) -> None:
        """Parses and validates incoming envelope models before any state mutation."""
        try:
            # 1. Size boundary check before JSON parse
            raw_bytes = raw_data.encode("utf-8")
            if len(raw_bytes) > MAX_PAYLOAD_SIZE:
                logger.warning("Incoming envelope exceeded size limit")
                return

            raw_dict = json.loads(raw_data)
            if not isinstance(raw_dict, dict):
                logger.warning("Invalid envelope format")
                return

            # 2. Strict model validation
            if "type" in raw_dict:
                envelope = GatewayTunnelEnvelope.model_validate(raw_dict)
                await self._handle_tunnel_packet(session, gw_ws, envelope)
            elif "action" in raw_dict:
                envelope = GatewayControlEnvelope.model_validate(raw_dict)
                await self._handle_control_packet(envelope)
            else:
                logger.warning("Unknown envelope structure")

        except Exception as e:  # noqa: BLE001 - gateway message dispatch error isolated from websocket loop
            logger.error(
                "Error processing gateway message: %s",
                type(e).__name__,
            )

    async def _handle_tunnel_packet(
        self,
        session: aiohttp.ClientSession,
        gw_ws: aiohttp.ClientWebSocketResponse,
        envelope: GatewayTunnelEnvelope,
    ) -> None:
        # Validate profile, instance, and session matching
        if envelope.profile_id != self.config.profile_id:
            logger.warning("Profile mismatch in tunnel envelope")
            return
        if envelope.runtime_instance_id != self.config.runtime_instance_id:
            logger.warning("Instance mismatch in tunnel envelope")
            return
        if (
            not self.agent_session_id
            or envelope.agent_session_id != self.agent_session_id
        ):
            logger.warning("Stale agent_session_id in tunnel envelope")
            return

        conn_id = envelope.conn_id
        pkt_type = envelope.type

        if pkt_type == "open":
            if conn_id in self.viewer_workers:
                await self._terminate_viewer(conn_id, caller="viewer_replacement")
            self._generation_counter += 1
            gen = self._generation_counter

            queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
            task = asyncio.create_task(
                self._viewer_upstream_worker(session, gw_ws, conn_id, queue, gen)
            )
            self.viewer_workers[conn_id] = ViewerWorkerEntry(
                generation=gen,
                task=task,
                queue=queue,
            )

            self.policy.set_viewer_visibility(conn_id, True)
            await self.policy.reconcile_capture_state(caller="viewer_tunnel_open")

        elif pkt_type == "msg":
            worker = self.viewer_workers.get(conn_id)
            if worker and not worker.task.done():
                try:
                    worker.queue.put_nowait(envelope)
                except asyncio.QueueFull:
                    logger.warning("Viewer queue full, terminating")
                    await self._terminate_viewer(conn_id, caller="queue_full")
                    close = tunnel_close_envelope(
                        profile_id=self.config.profile_id,
                        runtime_instance_id=self.config.runtime_instance_id,
                        session_id=self.agent_session_id,
                        conn_id=conn_id,
                        code=1013,
                        reason="Viewer queue full",
                    )
                    await asyncio.wait_for(
                        gw_ws.send_str(close.model_dump_json()), timeout=IO_TIMEOUT
                    )

        elif pkt_type == "close":
            await self._detach_viewer(conn_id)

    async def _handle_control_packet(
        self,
        envelope: GatewayControlEnvelope,
    ) -> None:
        if envelope.profile_id != self.config.profile_id:
            logger.warning("Profile mismatch in control envelope")
            return
        if envelope.runtime_instance_id != self.config.runtime_instance_id:
            logger.warning("Instance mismatch in control envelope")
            return
        if (
            not self.agent_session_id
            or envelope.agent_session_id != self.agent_session_id
        ):
            logger.warning(
                "Stale agent_session_id in control envelope"
            )
            return

        if envelope.action == AgentAction.SUPERVISOR_QUOTA:
            quota = envelope.payload
            self.policy.set_supervisor_quota(quota.max_fps_cap)
            await self.policy.reconcile_capture_state(caller="supervisor_quota")

    async def _terminate_viewer(self, conn_id: str, caller: str = "close") -> None:
        """Terminates viewer worker, cleans up peer mapping and notifies policy."""
        worker = self.viewer_workers.pop(conn_id, None)
        sdk_id = self.conn_id_to_sdk_peer_id.pop(conn_id, None)
        if sdk_id:
            self.policy.unregister_peer_mapping(sdk_peer_id=sdk_id, conn_id=conn_id)
        self.policy.remove_viewer(conn_id)
        if worker:
            await self._drain_workers([worker])
        await self.policy.reconcile_capture_state(caller=caller)

    async def _viewer_upstream_worker(
        self,
        session: aiohttp.ClientSession,
        gw_ws: aiohttp.ClientWebSocketResponse,
        conn_id: str,
        queue: asyncio.Queue,
        generation: int,
    ) -> None:
        """Dedicated per-viewer worker: connects to loopback Selkies WebSocket."""
        upstream_ws = None
        upstream_reader_task = None
        tab_id: str | None = None
        resume_key: str | None = None

        try:
            logger.info(
                "Worker starting loopback upstream connection..."
            )
            upstream_ws = await session.ws_connect(
                self.upstream_url,
                max_msg_size=MAX_STREAM_FRAME_SIZE,
                timeout=IO_TIMEOUT,
                heartbeat=HEARTBEAT_INTERVAL,
            )
            upstream_reader_task = asyncio.create_task(
                self._upstream_reader(gw_ws, conn_id, upstream_ws, generation)
            )

            if (
                conn_id in self.viewer_workers
                and self.viewer_workers[conn_id].generation == generation
            ):
                self.viewer_workers[conn_id].upstream_ws = upstream_ws
                self.viewer_workers[conn_id].reader_task = upstream_reader_task

            while True:
                envelope = await queue.get()
                if isinstance(envelope, GatewayTunnelEnvelope):
                    pkt_type = envelope.type
                    data = envelope.data or ""
                else:
                    pkt_type = envelope.get("type")
                    data = envelope.get("data", "")

                if pkt_type == "msg":
                    if len(data.encode("utf-8")) > MAX_PAYLOAD_SIZE:
                        logger.warning(
                            "Outbound payload exceeded limit"
                        )
                        break

                    # Inspect HELLO metadata and inject controller token if absent
                    if data.startswith("HELLO client "):
                        try:
                            hello = parse_hello_metadata(data)
                            if hello is not None:
                                parts, meta = hello
                                tab_id = meta.get("client_tab_id")
                                resume_key = meta.get("resume_key")
                                if (
                                    conn_id in self.viewer_workers
                                    and self.viewer_workers[conn_id].generation
                                    == generation
                                ):
                                    self.viewer_workers[conn_id].tab_id = tab_id
                                    self.viewer_workers[conn_id].resume_key = resume_key
                                if (
                                    not meta.get("client_token")
                                    and self.config.controller_token is not None
                                ):
                                    data = inject_controller_token(
                                        parts,
                                        meta,
                                        self.config.controller_token.get_secret_value(),
                                    )
                        except Exception as exc:  # noqa: BLE001 - non-critical HELLO message metadata parse failure logged
                            logger.warning(
                                "HELLO metadata parse failed: error_type=%s",
                                type(exc).__name__,
                            )

                    if not upstream_ws.closed:
                        await asyncio.wait_for(
                            upstream_ws.send_str(data), timeout=IO_TIMEOUT
                        )

                    # Correlate exact native client ID unambiguously
                    if conn_id not in self.conn_id_to_sdk_peer_id:
                        self._correlate_sdk_peer(
                            conn_id, tab_id, resume_key, upstream_ws
                        )

                elif pkt_type == "close":
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001 - upstream worker task failure isolated per-viewer
            logger.warning(
                "Upstream worker error (%s)", type(e).__name__
            )
            # Only send close to Gateway if this worker generation is still active
            active = self.viewer_workers.get(conn_id)
            if active and active.generation == generation and not gw_ws.closed:
                try:
                    close_env = tunnel_close_envelope(
                        profile_id=self.config.profile_id,
                        runtime_instance_id=self.config.runtime_instance_id,
                        session_id=self.agent_session_id or "",
                        conn_id=conn_id,
                        code=1011,
                        reason="Upstream worker failure",
                    )
                    await asyncio.wait_for(
                        gw_ws.send_str(close_env.model_dump_json()),
                        timeout=IO_TIMEOUT,
                    )
                except Exception as exc_close:  # noqa: BLE001 - best-effort notify gateway of worker close failure
                    logger.debug(
                        "Failed notifying gateway of worker failure: %s",
                        type(exc_close).__name__,
                    )
        finally:
            detached = (conn_id, generation) in self._detached_generations
            if detached:
                self._detached_generations.discard((conn_id, generation))
            else:
                if upstream_reader_task and not upstream_reader_task.done():
                    upstream_reader_task.cancel()
                if upstream_ws and not upstream_ws.closed:
                    try:
                        await upstream_ws.close()
                    except Exception as exc_ws:  # noqa: BLE001 - best-effort closing of upstream websocket
                        logger.debug(
                            "Failed closing upstream_ws in worker cleanup: %s",
                            type(exc_ws).__name__,
                        )
                # Generation check: superseded worker must not delete replacement
                active = self.viewer_workers.get(conn_id)
                if active and active.generation == generation:
                    self.viewer_workers.pop(conn_id, None)
                    sdk_id = self.conn_id_to_sdk_peer_id.pop(conn_id, None)
                    if sdk_id:
                        self.policy.unregister_peer_mapping(
                            sdk_peer_id=sdk_id, conn_id=conn_id
                        )
                    self.policy.remove_viewer(conn_id)
                    await self.policy.reconcile_capture_state(
                        caller="viewer_worker_exit"
                    )

    def _correlate_sdk_peer(
        self,
        conn_id: str,
        tab_id: str | None,
        resume_key: str | None,
        upstream_ws: aiohttp.ClientWebSocketResponse,
    ) -> None:
        """Correlates native SDK client ID with Gateway conn_id unambiguously."""
        if not self._webrtc_service or not hasattr(
            self._webrtc_service, "peer_manager"
        ):
            return
        pm = getattr(self._webrtc_service, "peer_manager", None)
        if not pm or not hasattr(pm, "peers"):
            return

        matching_pids = []
        for pid, peer in list(pm.peers.items()):
            if getattr(peer, "peer_type", None) != "client":
                continue
            p_tab = getattr(peer, "tab_id", None)
            p_res = getattr(peer, "resume_key", None)
            # Both native identity components must belong to this viewer.
            if tab_id and resume_key and p_tab == tab_id and p_res == resume_key:
                matching_pids.append(pid)

        # Unambiguous matching only: if ambiguity reject
        if len(matching_pids) == 1:
            sdk_id = matching_pids[0]
            self.conn_id_to_sdk_peer_id[conn_id] = sdk_id
            self.policy.register_peer_mapping(sdk_id, conn_id)
        elif len(matching_pids) > 1:
            logger.warning("Ambiguous SDK peer mapping, rejecting")

    async def _upstream_reader(
        self,
        gw_ws: aiohttp.ClientWebSocketResponse,
        conn_id: str,
        upstream_ws: aiohttp.ClientWebSocketResponse,
        generation: int,
    ) -> None:
        try:
            async for msg in upstream_ws:
                if msg.type == WSMsgType.TEXT:
                    if len(msg.data.encode("utf-8")) > MAX_PAYLOAD_SIZE:
                        logger.warning(
                            "Upstream sent oversized payload"
                        )
                        break
                    # Only relay if this reader is from the currently active generation
                    active = self.viewer_workers.get(conn_id)
                    if active and active.generation == generation and not gw_ws.closed:
                        tunnel_msg = tunnel_message_envelope(
                            profile_id=self.config.profile_id,
                            runtime_instance_id=self.config.runtime_instance_id,
                            session_id=self.agent_session_id,
                            conn_id=conn_id,
                            data=msg.data,
                        )
                        await asyncio.wait_for(
                            gw_ws.send_str(tunnel_msg.model_dump_json()),
                            timeout=IO_TIMEOUT,
                        )
                elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001 - upstream reader task failure isolated per-viewer
            logger.warning(
                "Upstream reader error (%s)", type(e).__name__
            )
        finally:
            # Gate ALL outgoing old close by matching active generation.
            # Preserve Selkies/upstream close semantics instead of faking 1000.
            upstream_code = normalize_close_code(upstream_ws.close_code)
            active = self.viewer_workers.get(conn_id)
            if active and active.generation == generation and not gw_ws.closed:
                try:
                    close_env = tunnel_close_envelope(
                        profile_id=self.config.profile_id,
                        runtime_instance_id=self.config.runtime_instance_id,
                        session_id=self.agent_session_id or "",
                        conn_id=conn_id,
                        code=upstream_code,
                        reason=f"Upstream closed ({upstream_code})",
                    )
                    await asyncio.wait_for(
                        gw_ws.send_str(close_env.model_dump_json()),
                        timeout=IO_TIMEOUT,
                    )
                except Exception as exc_notify:  # noqa: BLE001 - best-effort notify gateway of upstream close
                    logger.debug(
                        "Failed notifying gateway of upstream close: %s",
                        type(exc_notify).__name__,
                    )
            self._release_detached_upstream(upstream_ws)

    async def stop(self) -> None:
        """Deterministic drain and shutdown of all workers, readers, WS, and policy."""
        self._running = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._gw_ws and not self._gw_ws.closed:
            try:
                await self._gw_ws.close()
            except Exception as exc:  # noqa: BLE001 - best-effort closing of gateway websocket during stop
                logger.debug(
                    "Failed closing _gw_ws during stop: %s", type(exc).__name__
                )
        await self._cleanup_all_viewers(caller="agent_stop", detach=False)
        await self._close_all_detached_upstreams()
        await self.policy.stop()

    def close(self) -> None:
        self._running = False
        if self._gw_ws and not self._gw_ws.closed:
            asyncio.create_task(self._gw_ws.close())


def run_standalone_service() -> None:
    """Main standalone entrypoint for StreamAgent."""
    setup_service_logging()
    logger.info("Initializing CBrowser StreamAgent Standalone Service...")

    # Load configuration
    try:
        config = StreamAgentConfig.from_env()
    except Exception as e:  # noqa: BLE001 - configuration validation failure on service startup
        logger.error(
            "CONFIG_ERROR: Configuration loading failed (%s)", type(e).__name__
        )
        sys.exit(1)

    # Verify runtime mount security boundaries
    try:
        from .boundary import verify_stream_runtime_boundaries

        verify_stream_runtime_boundaries(
            pulse_dir=config.pulse_dir,
            x11_socket=config.x11_socket,
            xauthority_path=config.xauthority_path,
        )
    except Exception as e:  # noqa: BLE001 - security boundary validation failure on service startup
        logger.error(
            "BOUNDARY_ERROR: Security boundary validation failed (%s)", type(e).__name__
        )
        sys.exit(1)

    # 1. Install the X11 keymap refresh hook required by native input.
    try:
        from .x11_keymap import install_x11_keymap_refresh

        install_x11_keymap_refresh()
    except Exception as e:  # noqa: BLE001 - X11 keymap hook installation failure on service startup
        logger.error(
            "X11_KEYMAP_ERROR: Failed to install X11 keymap refresh (%s).",
            type(e).__name__,
        )
        sys.exit(1)

    # 2. Patch selkies.__main__.WebRTCService
    try:
        import selkies.__main__ as selkies_main
        from selkies.webrtc_mode import WebRTCService as SelkiesWebRTCService

        ServiceCls = create_policy_controlled_service_class(SelkiesWebRTCService)

        policy_agent = LiveCapturePolicyAgent(
            min_fps=config.min_fps,
            max_fps=config.max_fps,
        )
        upstream_port = os.environ.get("SELKIES_PORT", "18081")
        agent = StreamAgent(
            config=config,
            policy_agent=policy_agent,
            upstream_url=f"ws://127.0.0.1:{upstream_port}/api/webrtc/signaling",
        )

        def patched_factory(server: Any) -> Any:
            svc = ServiceCls(server)
            policy_agent.bind_service(svc)
            agent.bind_webrtc_service(svc)

            async def run_agent() -> None:
                try:
                    await agent.connect_and_run()
                finally:
                    await agent.stop()

            # Native shutdown cancels and awaits its owned task registry.
            svc.tasks.append(asyncio.create_task(run_agent()))
            return svc

        selkies_main.WebRTCService = patched_factory
        logger.info("Patched selkies.__main__.WebRTCService.")

        # 3. Launch official selkies.main()
        selkies_main.main()
    except Exception as e:  # noqa: BLE001 - Selkies service launch failure on service startup
        logger.error(
            "SERVICE_STARTUP_ERROR: Failed to start Selkies service (%s)",
            type(e).__name__,
        )
        sys.exit(1)


if __name__ == "__main__":
    run_standalone_service()
