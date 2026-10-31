"""
StreamAgent core coordinator and service runtime.
Connects outbound to Stream Gateway, manages WebRTC signaling bridge,
and delegates ICE restarts to GenerationIceTransport helper.
"""

import asyncio
import importlib.metadata
import json
import logging
import os
import socket
import sys
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import WSMsgType

from .config import StreamAgentConfig
from .policy import (
    LiveCapturePolicyAgent,
    create_policy_controlled_service_class,
)
from .protocol import (
    AgentAction,
    AgentHeartbeatPayload,
    AgentRegisterPayload,
    GatewayControlEnvelope,
    GatewayRegisterResponse,
    GatewayTunnelEnvelope,
    ProtocolEnvelope,
    RtcConfigPayload,
    SupervisorQuotaPayload,
)

logger = logging.getLogger("stream_agent.core")

MAX_PAYLOAD_SIZE = 1024 * 1024
MAX_FRAME_SIZE = 1024 * 1024 * 6 + 64 * 1024
IO_TIMEOUT = 10.0
QUEUE_MAX_SIZE = 100
HEARTBEAT_INTERVAL = 30.0
# Bound for a new ICE generation to take over before Gateway is told it failed.
ICE_RESTART_COMMIT_TIMEOUT = 20.0


class ISO8601Formatter(logging.Formatter):
    """Formats log record timestamps as strict ISO 8601 with UTC timezone."""

    def formatTime(
        self, record: logging.LogRecord, datefmt: Optional[str] = None
    ) -> str:
        dt = datetime.fromtimestamp(record.created, timezone.utc)
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


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc += f":{parsed.port}"
            return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except Exception:
        pass
    return url


def _sanitize_packet(packet: dict) -> dict:
    forbidden = {
        "token",
        "agent_token",
        "secret",
        "authorization",
        "password",
        "credential",
        "master_token",
        "controller_token",
        "client_token",
    }
    sanitized = {}
    for k, v in packet.items():
        if k.lower() in forbidden:
            continue
        if isinstance(v, dict):
            sanitized[k] = _sanitize_packet(v)
        else:
            sanitized[k] = v
    return sanitized


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


def resolve_selkies_version(configured_version: Optional[str] = None) -> str:
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
        reader_task: Optional[asyncio.Task] = None,
        upstream_ws: Optional[aiohttp.ClientWebSocketResponse] = None,
        tab_id: Optional[str] = None,
        resume_key: Optional[str] = None,
    ):
        self.generation = generation
        self.task = task
        self.queue = queue
        self.reader_task = reader_task
        self.upstream_ws = upstream_ws
        self.tab_id = tab_id
        self.resume_key = resume_key


class StreamAgent:
    def __init__(
        self,
        config: StreamAgentConfig,
        policy_agent: Optional[LiveCapturePolicyAgent] = None,
        upstream_url: str = "ws://127.0.0.1:18081",
    ):
        self.config = config
        self.policy = policy_agent or LiveCapturePolicyAgent(
            min_fps=config.min_fps,
            max_fps=config.max_fps,
        )
        self.upstream_url = upstream_url
        self.agent_session_id: Optional[str] = None
        self._running = False
        self._gw_ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._webrtc_service: Any = None

        # Monotonic generation counter preventing stale worker identity collision
        self._generation_counter = 0
        self.viewer_workers: Dict[str, ViewerWorkerEntry] = {}
        self.conn_id_to_sdk_peer_id: Dict[str, str] = {}
        self._backoff = ReconnectBackoff()
        self.heartbeat_interval: float = 10.0
        self._heartbeat_task: Optional[asyncio.Task] = None
        # ICE takeover waits run beside the Gateway pump so other viewers' signaling
        # is not stalled while one restart completes.
        self._restart_tasks: set[asyncio.Task] = set()
        self._sleep_fn = asyncio.sleep
        self.active_rtc_config: Optional[RtcConfigPayload] = None

    @property
    def viewer_queues(self) -> Dict[str, asyncio.Queue]:
        return {k: v.queue for k, v in self.viewer_workers.items()}

    @property
    def viewer_tasks(self) -> Dict[str, asyncio.Task]:
        return {k: v.task for k, v in self.viewer_workers.items()}

    def bind_webrtc_service(self, service: Any) -> None:
        """Binds WebRTCService and explicitly registers with policy_agent."""
        self._webrtc_service = service
        self.policy.bind_service(service)
        # Selkies creates its RTCApp only in initialize_components(); config that
        # arrived from Gateway earlier is pushed once it exists.
        service.rtc_ready_hook = self._push_rtc_config

    @property
    def peer_connections(self) -> Dict[str, Any]:
        """Lookup peer_connections directly from Selkies service if available."""
        if (
            self._webrtc_service
            and hasattr(self._webrtc_service, "rtc_app")
            and self._webrtc_service.rtc_app
        ):
            return getattr(self._webrtc_service.rtc_app, "peer_connections", {})
        return {}

    def get_peer_connection(self, conn_id: str) -> Optional[Any]:
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
        url = f"{self.config.gateway_url}/stream/agent/register"
        headers = {
            "Authorization": f"Bearer {self.config.agent_token.get_secret_value()}"
        }

        # Start policy background loops
        await self.policy.start()

        while self._running:
            try:
                logger.info(
                    "[%s] Connecting to Gateway at %s...",
                    _iso_now(),
                    _sanitize_url(url),
                )
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(
                        url,
                        headers=headers,
                        max_msg_size=MAX_FRAME_SIZE,
                        timeout=IO_TIMEOUT,
                        heartbeat=HEARTBEAT_INTERVAL,
                    ) as ws:
                        self._gw_ws = ws
                        logger.info(
                            "[%s] Connected to Gateway. Registering profile...",
                            _iso_now(),
                        )

                        selkies_ver = resolve_selkies_version(
                            self.config.selkies_version
                        )
                        reg_payload = AgentRegisterPayload(
                            hostname=socket.gethostname(),
                            profile_id=self.config.profile_id,
                            runtime_instance_id=self.config.runtime_instance_id,
                            udp_port=self.config.udp_mux_port,
                            selkies_version=selkies_ver,
                            runtime_state="ready",
                            config_version=self.config.config_version,
                            turn_host=self.config.turn_host,
                            turn_port=self.config.turn_port,
                            video_streaming_mode=self.config.video_streaming_mode,
                            max_fps=int(self.config.max_fps),
                            min_fps=int(self.config.min_fps),
                            width=self.config.width,
                            height=self.config.height,
                        )
                        reg_envelope = ProtocolEnvelope(
                            action=AgentAction.REGISTER,
                            profile_id=self.config.profile_id,
                            runtime_instance_id=self.config.runtime_instance_id,
                            payload=reg_payload.model_dump(),
                            timestamp=_iso_now(),
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
                            "[%s] StreamAgent registered with Gateway",
                            _iso_now(),
                        )

                        # Start application heartbeat task
                        self._heartbeat_task = asyncio.create_task(
                            self._heartbeat_loop(ws)
                        )

                        # Message pump
                        async for msg in ws:
                            if msg.type == WSMsgType.TEXT:
                                await self._handle_gateway_envelope(
                                    session, ws, msg.data
                                )
                            elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                                logger.warning(
                                    "[%s] Gateway connection closed or errored",
                                    _iso_now(),
                                )
                                break
            except asyncio.CancelledError:
                break
            except GatewayRegistrationError as e:
                logger.error("[%s] %s", _iso_now(), e)
            except Exception as e:
                logger.warning(
                    "[%s] Gateway connection error (%s)",
                    _iso_now(),
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
            logger.info("[%s] Reconnecting in %.1fs (backoff)...", _iso_now(), delay)
            await self._sleep_fn(delay)

    async def _heartbeat_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Send HEARTBEAT right after registration, then every 10 seconds.

        Supervisor readiness reads the reported Selkies video state through
        Gateway, so the first report must not wait a full interval.
        """
        try:
            while self._running and self.agent_session_id and not ws.closed:
                unpaused, capturing = self.policy.selkies_video_state()
                hb_payload = AgentHeartbeatPayload(
                    runtime_state="ready",
                    viewer_count=len(self.viewer_workers),
                    unpaused_video_consumers=unpaused,
                    capture_running=capturing,
                )
                hb_envelope = ProtocolEnvelope(
                    action=AgentAction.HEARTBEAT,
                    profile_id=self.config.profile_id,
                    runtime_instance_id=self.config.runtime_instance_id,
                    agent_session_id=self.agent_session_id,
                    payload=hb_payload.model_dump(),
                    timestamp=_iso_now(),
                )
                await ws.send_str(hb_envelope.model_dump_json())
                await self._sleep_fn(self.heartbeat_interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(
                "[%s] Heartbeat send failed (%s)",
                _iso_now(),
                type(e).__name__,
            )

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

    async def _cleanup_all_viewers(self, caller: str = "disconnect") -> None:
        """Invalidate generations before draining workers and their readers."""
        workers = list(self.viewer_workers.values())
        conn_ids = list(self.viewer_workers)
        self.viewer_workers.clear()
        for conn_id in conn_ids:
            sdk_id = self.conn_id_to_sdk_peer_id.pop(conn_id, None)
            self.policy.unregister_peer_mapping(sdk_peer_id=sdk_id, conn_id=conn_id)
            self.policy.remove_viewer(conn_id)
        await self._drain_workers(workers)
        await self.policy.reconcile_capture_state(caller=caller)

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
                logger.warning("[%s] Incoming envelope exceeded size limit", _iso_now())
                return

            raw_dict = json.loads(raw_data)
            if not isinstance(raw_dict, dict):
                logger.warning("[%s] Invalid envelope format", _iso_now())
                return

            # 2. Strict model validation
            if "type" in raw_dict:
                envelope = GatewayTunnelEnvelope.model_validate(raw_dict)
                await self._handle_tunnel_packet(session, gw_ws, envelope)
            elif "action" in raw_dict:
                envelope = GatewayControlEnvelope.model_validate(raw_dict)
                await self._handle_control_packet(envelope)
            else:
                logger.warning("[%s] Unknown envelope structure", _iso_now())

        except Exception as e:
            logger.error(
                "[%s] Error processing gateway message: %s",
                _iso_now(),
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
            logger.warning("[%s] Profile mismatch in tunnel envelope", _iso_now())
            return
        if envelope.runtime_instance_id != self.config.runtime_instance_id:
            logger.warning("[%s] Instance mismatch in tunnel envelope", _iso_now())
            return
        if (
            not self.agent_session_id
            or envelope.agent_session_id != self.agent_session_id
        ):
            logger.warning("[%s] Stale agent_session_id in tunnel envelope", _iso_now())
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
                    logger.warning("[%s] Viewer queue full, terminating", _iso_now())
                    await self._terminate_viewer(conn_id, caller="queue_full")
                    close = GatewayTunnelEnvelope(
                        version="v2",
                        type="close",
                        profile_id=self.config.profile_id,
                        runtime_instance_id=self.config.runtime_instance_id,
                        agent_session_id=self.agent_session_id,
                        conn_id=conn_id,
                        code=1013,
                        reason="Viewer queue full",
                    )
                    await asyncio.wait_for(
                        gw_ws.send_str(close.model_dump_json()), timeout=IO_TIMEOUT
                    )

        elif pkt_type == "close":
            await self._terminate_viewer(conn_id, caller="viewer_tunnel_close")

    async def _handle_control_packet(
        self,
        envelope: GatewayControlEnvelope,
    ) -> None:
        if envelope.profile_id != self.config.profile_id:
            logger.warning("[%s] Profile mismatch in control envelope", _iso_now())
            return
        if envelope.runtime_instance_id != self.config.runtime_instance_id:
            logger.warning("[%s] Instance mismatch in control envelope", _iso_now())
            return
        if (
            not self.agent_session_id
            or envelope.agent_session_id != self.agent_session_id
        ):
            logger.warning(
                "[%s] Stale agent_session_id in control envelope", _iso_now()
            )
            return

        action = envelope.action
        conn_id = envelope.conn_id

        if action == AgentAction.REGISTERED:
            self.agent_session_id = envelope.agent_session_id

        elif action == AgentAction.SUPERVISOR_QUOTA:
            quota = SupervisorQuotaPayload.model_validate(envelope.payload)
            self.policy.set_supervisor_quota(quota.max_fps_cap)
            await self.policy.reconcile_capture_state(caller="supervisor_quota")

        elif action == AgentAction.ICE_RESTART:
            if not conn_id or conn_id not in self.viewer_workers:
                logger.warning("[%s] ICE restart rejected: unknown conn_id", _iso_now())
                return
            if "ice_servers" in envelope.payload and envelope.payload["ice_servers"]:
                try:
                    gen_num = envelope.payload.get("generation")
                    if gen_num is None:
                        gen_num = (
                            self.active_rtc_config.generation
                            if self.active_rtc_config
                            else 1
                        )
                    rtc_payload = RtcConfigPayload(
                        generation=gen_num,
                        ice_servers=envelope.payload["ice_servers"],
                        relay_only=bool(
                            envelope.payload.get("relay_only")
                            or envelope.payload.get("force_relay")
                            or (
                                self.active_rtc_config
                                and self.active_rtc_config.relay_only
                            )
                        ),
                    )
                    self.apply_rtc_config(rtc_payload)
                except Exception as e:
                    logger.warning(
                        "[%s] Failed to update active_rtc_config from ice_restart (%s)",
                        _iso_now(),
                        type(e).__name__,
                    )
            await self._trigger_ice_restart(conn_id, envelope.payload)

        elif action == AgentAction.ICE_RESTART_ANSWER:
            if not conn_id or conn_id not in self.viewer_workers:
                return
            task = asyncio.create_task(
                self._handle_ice_restart_answer(conn_id, envelope.payload)
            )
            self._restart_tasks.add(task)
            task.add_done_callback(self._restart_tasks.discard)

        elif action == AgentAction.RTC_CONFIG:
            try:
                rtc_payload = RtcConfigPayload.model_validate(envelope.payload)
            except Exception as e:
                logger.warning(
                    "[%s] Invalid rtc_config payload rejected (%s)",
                    _iso_now(),
                    type(e).__name__,
                )
                return
            try:
                self.apply_rtc_config(rtc_payload)
            except Exception as e:
                logger.error(
                    "[%s] Applying rtc_config generation %d failed (%s)",
                    _iso_now(),
                    rtc_payload.generation,
                    type(e).__name__,
                )
                return
            logger.info(
                "[%s] Applied rtc_config generation %d with %d ICE servers",
                _iso_now(),
                rtc_payload.generation,
                len(rtc_payload.ice_servers),
            )

    def apply_rtc_config(self, payload: RtcConfigPayload) -> None:
        """Apply new stream-side RTC configuration from Gateway."""
        self.active_rtc_config = payload
        self.config.turn_servers = payload.wire_ice_servers()
        from .ice_transport import set_relay_only

        set_relay_only(payload.relay_only)
        self._push_rtc_config()

    def _push_rtc_config(self) -> None:
        """Give Selkies the current stream-side servers for new PeerConnections."""
        rtc_app = getattr(self._webrtc_service, "rtc_app", None)
        if rtc_app is None or self.active_rtc_config is None:
            return
        stun, turn = self.active_rtc_config.selkies_server_urls()
        rtc_app.update_rtc_config(stun, turn)

    def _resolve_ice_servers_for_restart(self, payload: Dict[str, Any]) -> List[Any]:
        """Resolve ICE servers for restart: payload overrides active rtc_config."""
        server_turn = payload.get("ice_servers")
        if not server_turn:
            if self.active_rtc_config is not None:
                server_turn = self.active_rtc_config.wire_ice_servers()
            else:
                server_turn = self.config.turn_servers
        return server_turn

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
        tab_id: Optional[str] = None
        resume_key: Optional[str] = None

        try:
            logger.info(
                "[%s] Worker starting loopback upstream connection...", _iso_now()
            )
            upstream_ws = await session.ws_connect(
                self.upstream_url,
                max_msg_size=MAX_FRAME_SIZE,
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
                            "[%s] Outbound payload exceeded limit", _iso_now()
                        )
                        break

                    # Inspect HELLO metadata and inject controller token if absent
                    if data.startswith("HELLO client "):
                        try:
                            parts = data.split(" ", 2)
                            if len(parts) > 2:
                                meta = json.loads(parts[2])
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
                                    meta["client_token"] = (
                                        self.config.controller_token.get_secret_value()
                                    )
                                    data = f"{parts[0]} {parts[1]} {json.dumps(meta)}"
                        except Exception:
                            pass

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
        except Exception as e:
            logger.warning(
                "[%s] Upstream worker error (%s)", _iso_now(), type(e).__name__
            )
            # Only send close to Gateway if this worker generation is still active
            active = self.viewer_workers.get(conn_id)
            if active and active.generation == generation and not gw_ws.closed:
                try:
                    close_env = GatewayTunnelEnvelope(
                        version="v2",
                        type="close",
                        profile_id=self.config.profile_id,
                        runtime_instance_id=self.config.runtime_instance_id,
                        agent_session_id=self.agent_session_id or "",
                        conn_id=conn_id,
                        code=1011,
                        reason="Upstream worker failure",
                    )
                    await asyncio.wait_for(
                        gw_ws.send_str(close_env.model_dump_json()),
                        timeout=IO_TIMEOUT,
                    )
                except Exception:
                    pass
        finally:
            if upstream_reader_task and not upstream_reader_task.done():
                upstream_reader_task.cancel()
            if upstream_ws and not upstream_ws.closed:
                try:
                    await upstream_ws.close()
                except Exception:
                    pass
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
                await self.policy.reconcile_capture_state(caller="viewer_worker_exit")

    def _correlate_sdk_peer(
        self,
        conn_id: str,
        tab_id: Optional[str],
        resume_key: Optional[str],
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
            logger.warning("[%s] Ambiguous SDK peer mapping, rejecting", _iso_now())

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
                            "[%s] Upstream sent oversized payload", _iso_now()
                        )
                        break
                    # Only relay if this reader is from the currently active generation
                    active = self.viewer_workers.get(conn_id)
                    if active and active.generation == generation and not gw_ws.closed:
                        tunnel_msg = GatewayTunnelEnvelope(
                            version="v2",
                            type="msg",
                            profile_id=self.config.profile_id,
                            runtime_instance_id=self.config.runtime_instance_id,
                            agent_session_id=self.agent_session_id or "",
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
        except Exception as e:
            logger.warning(
                "[%s] Upstream reader error (%s)", _iso_now(), type(e).__name__
            )
        finally:
            # Gate ALL outgoing old close by matching active generation
            active = self.viewer_workers.get(conn_id)
            if active and active.generation == generation and not gw_ws.closed:
                try:
                    close_env = GatewayTunnelEnvelope(
                        version="v2",
                        type="close",
                        profile_id=self.config.profile_id,
                        runtime_instance_id=self.config.runtime_instance_id,
                        agent_session_id=self.agent_session_id or "",
                        conn_id=conn_id,
                        code=1000,
                        reason="Upstream closed",
                    )
                    await asyncio.wait_for(
                        gw_ws.send_str(close_env.model_dump_json()),
                        timeout=IO_TIMEOUT,
                    )
                except Exception:
                    pass

    async def _trigger_ice_restart(
        self, conn_id: Optional[str], payload: Dict[str, Any]
    ) -> None:
        """Invoke ice_transport helper to create restart offer on existing PC."""
        if not conn_id:
            return
        pc = self.get_peer_connection(conn_id)
        if not pc:
            logger.warning("[%s] PeerConnection not found for conn_id", _iso_now())
            await self._report_restart(
                AgentAction.ERROR, conn_id, {"error": "peer_connection_not_found"}
            )
            return
        # A restart offer while the initial offer/answer or ICE run is still in
        # flight would replace it; Gateway retries after backoff instead.
        if pc.signalingState != "stable" or pc.iceConnectionState not in (
            "connected",
            "completed",
        ):
            logger.warning("[%s] ICE restart deferred: peer not connected", _iso_now())
            await self._report_restart(
                AgentAction.ERROR, conn_id, {"error": "peer_not_ready"}
            )
            return

        try:
            from .ice_transport import create_restart_offer

            server_turn = self._resolve_ice_servers_for_restart(payload)
            force_relay = payload.get("force_relay", False)
            local_desc = await create_restart_offer(
                pc, server_turn, force_relay=force_relay
            )

            if self._gw_ws and not self._gw_ws.closed:
                envelope = ProtocolEnvelope(
                    action=AgentAction.ICE_RESTART_OFFER,
                    profile_id=self.config.profile_id,
                    runtime_instance_id=self.config.runtime_instance_id,
                    agent_session_id=self.agent_session_id,
                    conn_id=conn_id,
                    payload={"sdp": local_desc.sdp, "type": local_desc.type},
                    timestamp=_iso_now(),
                )
                await self._gw_ws.send_str(envelope.model_dump_json())
        except Exception as e:
            logger.error(
                "[%s] Failed to create ICE restart offer: %s",
                _iso_now(),
                type(e).__name__,
            )
            await self._report_restart(
                AgentAction.ERROR, conn_id, {"error": "ice_restart_offer_failed"}
            )

    async def _handle_ice_restart_answer(
        self, conn_id: Optional[str], payload: Dict[str, Any]
    ) -> None:
        """Apply the Viewer answer and confirm to Gateway only after real takeover."""
        if not conn_id:
            return
        pc = self.get_peer_connection(conn_id)
        if not pc:
            logger.warning("[%s] PeerConnection not found on answer", _iso_now())
            await self._report_restart(
                AgentAction.ERROR, conn_id, {"error": "peer_connection_not_found"}
            )
            return
        try:
            from selkies.webrtc.rtcsessiondescription import RTCSessionDescription

            from .ice_transport import wait_restart_commit

            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=payload.get("sdp"), type="answer")
            )
            ice_generation = await wait_restart_commit(pc, ICE_RESTART_COMMIT_TIMEOUT)
        except Exception as e:
            logger.error(
                "[%s] ICE restart not committed: %s", _iso_now(), type(e).__name__
            )
            await self._report_restart(
                AgentAction.ERROR, conn_id, {"error": "ice_restart_not_committed"}
            )
            return
        logger.info(
            "[%s] ICE restart committed (ice generation %d)",
            _iso_now(),
            ice_generation,
        )
        await self._report_restart(
            AgentAction.ICE_RESTART_COMMITTED,
            conn_id,
            {"generation": payload.get("generation"), "ice_generation": ice_generation},
        )

    async def _report_restart(
        self, action: AgentAction, conn_id: str, payload: Dict[str, Any]
    ) -> None:
        if self._gw_ws and not self._gw_ws.closed:
            envelope = ProtocolEnvelope(
                action=action,
                profile_id=self.config.profile_id,
                runtime_instance_id=self.config.runtime_instance_id,
                agent_session_id=self.agent_session_id,
                conn_id=conn_id,
                payload=payload,
                timestamp=_iso_now(),
            )
            await self._gw_ws.send_str(envelope.model_dump_json())

    async def stop(self) -> None:
        """Deterministic drain and shutdown of all workers, readers, WS, and policy."""
        self._running = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        restarts = list(self._restart_tasks)
        for task in restarts:
            task.cancel()
        await asyncio.gather(*restarts, return_exceptions=True)
        if self._gw_ws and not self._gw_ws.closed:
            try:
                await self._gw_ws.close()
            except Exception:
                pass
        await self._cleanup_all_viewers(caller="agent_stop")
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
    except Exception as e:
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
    except Exception as e:
        logger.error(
            "BOUNDARY_ERROR: Security boundary validation failed (%s)", type(e).__name__
        )
        sys.exit(1)

    # 1. Install ICE transport generation adapter (fail-closed, must abort on failure!)
    try:
        from .ice_transport import install_ice_transport

        install_ice_transport()
        from .x11_keymap import install_x11_keymap_refresh

        install_x11_keymap_refresh()
        logger.info("GenerationIceTransport installed into Selkies.")
    except Exception as e:
        logger.error(
            "ICE_ABI_ERROR: Failed to install GenerationIceTransport (%s).",
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
    except Exception as e:
        logger.error(
            "SERVICE_STARTUP_ERROR: Failed to start Selkies service (%s)",
            type(e).__name__,
        )
        sys.exit(1)


if __name__ == "__main__":
    run_standalone_service()
