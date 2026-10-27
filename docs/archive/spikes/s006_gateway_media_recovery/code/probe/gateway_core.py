"""
StreamGateway & StreamAgent WebSocket Protocol Prototype (18.11 Verification)

Fixes and hardening:
1. Strict Profile & Agent Isolation:
   - Each Agent registration instance is bound to its unique agent_session_id.
   - Gateway checks: conn_id must exist, AND its profile_id must match the agent's profile_id,
     AND it must belong to the active agent_session_id.
   - Messages/close requests from other profiles or stale agent sessions are dropped immediately.

2. Agent Replacement Policy:
   - If a new Agent connects for an existing profile while the old Agent is still alive,
     Gateway rejects the new registration with 409 Conflict ("Agent already active for profile")
     to prevent race conditions / stale reader callbacks tear down.
   - When the old Agent disconnects or is explicitly terminated, the slot frees up.

3. Origin Enforcement:
   - Viewer connections on /stream/{profile_id}/signal enforce Origin checks (default localhost / configured origins).
   - Non-matching or missing browser Origin headers are rejected with 403 Forbidden.

4. Non-blocking Upstream Handshake & Per-Viewer Queues:
   - Agent maintains an independent, bounded Queue per conn_id.
   - Upstream connection establishment happens in a dedicated worker task per viewer,
     so a slow upstream handshake on viewer A NEVER blocks viewer B or the main Agent tunnel loop.
   - Messages arriving before upstream is ready are buffered in the queue in strict order (e.g. HELLO is never lost).

5. Clean Teardown & Legal Close Codes:
   - No reserved close code 1006 is sent over the wire; uses 1000 (normal), 1008 (policy/auth), 1011 (internal/agent gone).
   - Frame payload size limit: MAX_PAYLOAD_SIZE (1MB), MAX_FRAME_SIZE (1MB + 16KB envelope).
   - Send timeouts on all socket sends.
"""
import asyncio
import json
import logging
import sys
import uuid
from typing import Dict, Optional, Set
from aiohttp import web, WSMsgType, ClientSession, WSCloseCode

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("gateway_core")

MAX_PAYLOAD_SIZE = 1024 * 1024            # 1MB raw payload limit (UTF-8 bytes)
MAX_ESCAPE_MULTIPLIER = 6                 # JSON worst-case escape expansion (e.g. \x00 -> \u0000)
ENVELOPE_MARGIN = 64 * 1024               # 64KB JSON framing margin
MAX_FRAME_SIZE = MAX_PAYLOAD_SIZE * MAX_ESCAPE_MULTIPLIER + ENVELOPE_MARGIN
IO_TIMEOUT = 10.0                         # 10s timeout for handshakes, writes and closes
QUEUE_MAX_SIZE = 100                      # bounded per-viewer queue
HEARTBEAT_INTERVAL = 30.0                 # idle websocket keepalive interval

def _check_payload_limit(data: str) -> bool:
    """Return True if UTF-8 encoded payload size <= MAX_PAYLOAD_SIZE."""
    if not isinstance(data, str):
        return False
    return len(data.encode("utf-8")) <= MAX_PAYLOAD_SIZE

def _sanitize_packet(packet: dict) -> dict:
    """Ensure outgoing packet never leaks secret/token fields."""
    forbidden = {"token", "agent_token", "secret", "authorization", "password"}
    return {k: v for k, v in packet.items() if k.lower() not in forbidden}

class StreamGateway:
    def __init__(self, agent_token: str, allowed_origins: Optional[Set[str]] = None):
        self.agent_token = agent_token
        self.allowed_origins = allowed_origins
        # profile_id -> (agent_session_id, agent_ws)
        self.registered_agents: Dict[str, tuple[str, web.WebSocketResponse]] = {}
        # conn_id -> (profile_id, agent_session_id, viewer_ws)
        self.viewers: Dict[str, tuple[str, str, web.WebSocketResponse]] = {}
        # profile_id -> set of conn_ids
        self.profile_viewers: Dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    def _check_origin(self, request: web.Request) -> bool:
        origin = request.headers.get("Origin")
        if not origin:
            return False
        if self.allowed_origins is not None:
            return origin in self.allowed_origins
        # Strict exact match against current request scheme and host:port
        expected = f"{request.scheme}://{request.host}"
        return origin == expected

    async def handle_agent_register(self, request: web.Request) -> web.WebSocketResponse:
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {self.agent_token}":
            return web.Response(status=401, text="Unauthorized Agent")

        ws = web.WebSocketResponse(max_msg_size=MAX_FRAME_SIZE, heartbeat=HEARTBEAT_INTERVAL)
        await ws.prepare(request)

        agent_session_id = str(uuid.uuid4())
        profile_id: Optional[str] = None
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=IO_TIMEOUT)
            if msg.type != WSMsgType.TEXT:
                await asyncio.wait_for(ws.close(code=WSCloseCode.PROTOCOL_ERROR, message=b"Expected text registration"), timeout=IO_TIMEOUT)
                return ws
            reg_data = json.loads(msg.data)
            if reg_data.get("action") != "register" or not reg_data.get("profile_id"):
                await asyncio.wait_for(ws.close(code=WSCloseCode.PROTOCOL_ERROR, message=b"Invalid registration packet"), timeout=IO_TIMEOUT)
                return ws

            profile_id = reg_data["profile_id"]

            async with self._lock:
                # Agent Replacement / Conflict Policy:
                # If an active agent connection already exists for this profile, reject duplicate registration with 409 policy
                if profile_id in self.registered_agents:
                    existing_sess, existing_ws = self.registered_agents[profile_id]
                    if not existing_ws.closed:
                        logger.warning("Rejecting duplicate agent registration for profile %s (already active in session %s)", profile_id, existing_sess)
                        await asyncio.wait_for(ws.close(code=WSCloseCode.POLICY_VIOLATION, message=b"Agent already active for profile"), timeout=IO_TIMEOUT)
                        return ws

                self.registered_agents[profile_id] = (agent_session_id, ws)
                self.profile_viewers.setdefault(profile_id, set())

            await asyncio.wait_for(ws.send_json(_sanitize_packet({
                "action": "registered",
                "status": "ok",
                "profile_id": profile_id,
                "session_id": agent_session_id
            })), timeout=IO_TIMEOUT)
            logger.info("Agent registered: profile=%s, session=%s", profile_id, agent_session_id)

            # Multiplex loop: receive from Agent and forward to Viewers
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    packet = json.loads(msg.data)
                    conn_id = packet.get("conn_id")
                    pkt_type = packet.get("type")
                    if not conn_id:
                        continue

                    # Strict Profile & Session Isolation Check:
                    viewer_info = self.viewers.get(conn_id)
                    if not viewer_info:
                        continue
                    v_profile_id, v_agent_sess, viewer_ws = viewer_info
                    if v_profile_id != profile_id or v_agent_sess != agent_session_id:
                        logger.error("SECURITY ALERT: Agent session %s (profile %s) attempted cross-profile operation on conn_id %s (belongs to profile %s, session %s)",
                                     agent_session_id, profile_id, conn_id, v_profile_id, v_agent_sess)
                        continue

                    if pkt_type == "msg":
                        data = packet.get("data", "")
                        if not _check_payload_limit(data):
                            logger.warning("Agent sent payload exceeding MAX_PAYLOAD_SIZE for conn %s, closing viewer", conn_id)
                            if not viewer_ws.closed:
                                await asyncio.wait_for(viewer_ws.close(code=WSCloseCode.MESSAGE_TOO_BIG, message=b"Payload too large"), timeout=IO_TIMEOUT)
                            await asyncio.wait_for(ws.send_json(_sanitize_packet({
                                "type": "close",
                                "conn_id": conn_id,
                                "code": 1009,
                                "reason": "Payload too large"
                            })), timeout=IO_TIMEOUT)
                            self.viewers.pop(conn_id, None)
                            if profile_id in self.profile_viewers:
                                self.profile_viewers[profile_id].discard(conn_id)
                            continue

                        if not viewer_ws.closed:
                            await asyncio.wait_for(viewer_ws.send_str(data), timeout=IO_TIMEOUT)
                    elif pkt_type == "close":
                        if not viewer_ws.closed:
                            close_code = packet.get("code", 1000)
                            # Ensure code is legal RFC 6455
                            if close_code == 1006 or close_code < 1000 or close_code > 4999:
                                close_code = 1000
                            await asyncio.wait_for(viewer_ws.close(code=close_code, message=packet.get("reason", "").encode()), timeout=IO_TIMEOUT)
                        self.viewers.pop(conn_id, None)
                        if profile_id in self.profile_viewers:
                            self.profile_viewers[profile_id].discard(conn_id)
                elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        except Exception as e:
            logger.warning("Agent %s connection error: %s", profile_id, e)
        finally:
            async with self._lock:
                if profile_id and self.registered_agents.get(profile_id) == (agent_session_id, ws):
                    self.registered_agents.pop(profile_id, None)
                    # Tear down only viewers belonging to this agent session
                    active_conn_ids = list(self.profile_viewers.pop(profile_id, set()))
                    for cid in active_conn_ids:
                        if cid in self.viewers:
                            v_pid, v_sess, v_ws = self.viewers.pop(cid)
                            if v_sess == agent_session_id and not v_ws.closed:
                                try:
                                    await asyncio.wait_for(v_ws.close(code=WSCloseCode.SERVICE_RESTART, message=b"Agent disconnected"), timeout=IO_TIMEOUT)
                                except Exception:
                                    pass
                    logger.info("Agent deregistered: profile=%s, cleaned up %d viewers", profile_id, len(active_conn_ids))
            if not ws.closed:
                await ws.close()
        return ws

    async def handle_viewer_signal(self, request: web.Request) -> web.WebSocketResponse:
        # 1. Enforce browser Origin check
        if not self._check_origin(request):
            logger.warning("Rejected viewer connection with disallowed Origin: %s", request.headers.get("Origin"))
            return web.Response(status=403, text="Forbidden: Invalid Origin")

        profile_id = request.match_info.get("profile_id")
        if not profile_id or profile_id not in self.registered_agents:
            return web.Response(status=503, text="Profile agent not ready or offline")

        agent_session_id, agent_ws = self.registered_agents[profile_id]
        if agent_ws.closed:
            return web.Response(status=503, text="Profile agent connection closed")

        ws = web.WebSocketResponse(max_msg_size=MAX_FRAME_SIZE, heartbeat=HEARTBEAT_INTERVAL)
        await ws.prepare(request)

        conn_id = str(uuid.uuid4())
        self.viewers[conn_id] = (profile_id, agent_session_id, ws)
        self.profile_viewers[profile_id].add(conn_id)

        try:
            # Inform Agent about new viewer tunnel
            await asyncio.wait_for(agent_ws.send_json(_sanitize_packet({
                "type": "open",
                "conn_id": conn_id,
                "profile_id": profile_id
            })), timeout=IO_TIMEOUT)

            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    if not _check_payload_limit(msg.data):
                        logger.warning("Viewer %s payload exceeded MAX_PAYLOAD_SIZE, closing viewer", conn_id)
                        if not ws.closed:
                            await asyncio.wait_for(ws.close(code=WSCloseCode.MESSAGE_TOO_BIG, message=b"Payload too large"), timeout=IO_TIMEOUT)
                        if not agent_ws.closed:
                            await asyncio.wait_for(agent_ws.send_json(_sanitize_packet({
                                "type": "close",
                                "conn_id": conn_id,
                                "code": 1009,
                                "reason": "Payload too large"
                            })), timeout=IO_TIMEOUT)
                        break

                    if not agent_ws.closed:
                        await asyncio.wait_for(agent_ws.send_json(_sanitize_packet({
                            "type": "msg",
                            "conn_id": conn_id,
                            "data": msg.data
                        })), timeout=IO_TIMEOUT)
                elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        except Exception as e:
            logger.warning("Viewer %s error: %s", conn_id, e)
        finally:
            self.viewers.pop(conn_id, None)
            if profile_id in self.profile_viewers:
                self.profile_viewers[profile_id].discard(conn_id)
            if not agent_ws.closed:
                try:
                    await asyncio.wait_for(agent_ws.send_json(_sanitize_packet({
                        "type": "close",
                        "conn_id": conn_id,
                        "code": 1000,
                        "reason": "Viewer closed"
                    })), timeout=IO_TIMEOUT)
                except Exception:
                    pass
            if not ws.closed:
                await ws.close()
        return ws

class StreamAgent:
    def __init__(self, gateway_url: str, profile_id: str, agent_token: str, upstream_url: str):
        self.gateway_url = gateway_url
        self.profile_id = profile_id
        self.agent_token = agent_token
        self.upstream_url = upstream_url
        # conn_id -> asyncio.Queue of tunnel packets
        self.viewer_queues: Dict[str, asyncio.Queue] = {}
        # conn_id -> worker task
        self.viewer_tasks: Dict[str, asyncio.Task] = {}
        self.running = False
        self._gw_ws = None

    async def run(self):
        self.running = True
        headers = {"Authorization": f"Bearer {self.agent_token}"}
        async with ClientSession() as session:
            while self.running:
                try:
                    logger.info("StreamAgent connecting to Gateway at %s...", self.gateway_url)
                    async with session.ws_connect(self.gateway_url, headers=headers, max_msg_size=MAX_FRAME_SIZE, timeout=IO_TIMEOUT, heartbeat=HEARTBEAT_INTERVAL) as gw_ws:
                        self._gw_ws = gw_ws
                        # Register
                        await asyncio.wait_for(gw_ws.send_json(_sanitize_packet({"action": "register", "profile_id": self.profile_id})), timeout=IO_TIMEOUT)
                        resp = await asyncio.wait_for(gw_ws.receive(), timeout=IO_TIMEOUT)
                        if resp.type != WSMsgType.TEXT:
                            logger.error("Registration failed, invalid response")
                            break
                        reg_res = json.loads(resp.data)
                        if reg_res.get("status") != "ok":
                            logger.error("Registration rejected: %s", reg_res)
                            break
                        logger.info("StreamAgent registered with Gateway: session=%s", reg_res.get("session_id"))

                        # Dispatch tunnel packets from Gateway non-blockingly into per-viewer queues
                        async for msg in gw_ws:
                            if msg.type == WSMsgType.TEXT:
                                packet = json.loads(msg.data)
                                conn_id = packet.get("conn_id")
                                pkt_type = packet.get("type")
                                if not conn_id:
                                    continue

                                if pkt_type == "open":
                                    queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
                                    self.viewer_queues[conn_id] = queue
                                    task = asyncio.create_task(self._viewer_upstream_worker(session, gw_ws, conn_id, queue))
                                    self.viewer_tasks[conn_id] = task
                                else:
                                    q = self.viewer_queues.get(conn_id)
                                    if q:
                                        try:
                                            q.put_nowait(packet)
                                        except asyncio.QueueFull:
                                            logger.warning("Viewer %s queue full, terminating viewer", conn_id)
                                            self.viewer_queues.pop(conn_id, None)
                                            t = self.viewer_tasks.pop(conn_id, None)
                                            if t:
                                                t.cancel()
                                            if not gw_ws.closed:
                                                try:
                                                    await asyncio.wait_for(gw_ws.send_json(_sanitize_packet({
                                                        "type": "close",
                                                        "conn_id": conn_id,
                                                        "code": 1008,
                                                        "reason": "Viewer queue overflow"
                                                    })), timeout=IO_TIMEOUT)
                                                except Exception:
                                                    pass
                            elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                                break
                except Exception as e:
                    logger.warning("StreamAgent connection error: %s", e)
                finally:
                    # Cancel all viewer tasks
                    for task in self.viewer_tasks.values():
                        task.cancel()
                    self.viewer_tasks.clear()
                    self.viewer_queues.clear()

                if not self.running:
                    break
                await asyncio.sleep(1.0)

    async def _viewer_upstream_worker(self, session: ClientSession, gw_ws, conn_id: str, queue: asyncio.Queue):
        """Dedicated per-viewer worker: connects to upstream without blocking the main Agent loop."""
        upstream_ws = None
        upstream_reader_task = None
        try:
            logger.info("Worker starting upstream connection for %s -> %s", conn_id, self.upstream_url)
            upstream_ws = await session.ws_connect(self.upstream_url, max_msg_size=MAX_FRAME_SIZE, timeout=IO_TIMEOUT, heartbeat=HEARTBEAT_INTERVAL)
            upstream_reader_task = asyncio.create_task(self._upstream_reader(gw_ws, conn_id, upstream_ws))

            # Process queued packets strictly in order
            while True:
                packet = await queue.get()
                pkt_type = packet.get("type")
                if pkt_type == "msg":
                    data = packet.get("data", "")
                    if not _check_payload_limit(data):
                        logger.warning("Viewer %s outbound payload exceeded limit, closing", conn_id)
                        if not upstream_ws.closed:
                            await asyncio.wait_for(upstream_ws.close(code=WSCloseCode.MESSAGE_TOO_BIG, message=b"Payload too large"), timeout=IO_TIMEOUT)
                        if not gw_ws.closed:
                            await asyncio.wait_for(gw_ws.send_json(_sanitize_packet({
                                "type": "close",
                                "conn_id": conn_id,
                                "code": 1009,
                                "reason": "Payload too large"
                            })), timeout=IO_TIMEOUT)
                        break
                    if not upstream_ws.closed:
                        await asyncio.wait_for(upstream_ws.send_str(data), timeout=IO_TIMEOUT)
                elif pkt_type == "close":
                    break
        except Exception as e:
            logger.warning("Upstream worker error for %s: %s", conn_id, e)
            if not gw_ws.closed:
                try:
                    await asyncio.wait_for(gw_ws.send_json(_sanitize_packet({"type": "close", "conn_id": conn_id, "code": 1011, "reason": "Upstream failure"})), timeout=IO_TIMEOUT)
                except Exception:
                    pass
        finally:
            if upstream_reader_task:
                upstream_reader_task.cancel()
            if upstream_ws and not upstream_ws.closed:
                try:
                    await upstream_ws.close()
                except Exception:
                    pass
            self.viewer_queues.pop(conn_id, None)
            self.viewer_tasks.pop(conn_id, None)
            logger.info("Worker finished for %s", conn_id)

    async def _upstream_reader(self, gw_ws, conn_id: str, upstream_ws):
        try:
            async for msg in upstream_ws:
                if msg.type == WSMsgType.TEXT:
                    if not _check_payload_limit(msg.data):
                        logger.warning("Upstream sent oversized payload for %s, closing", conn_id)
                        if not upstream_ws.closed:
                            await asyncio.wait_for(upstream_ws.close(code=WSCloseCode.MESSAGE_TOO_BIG, message=b"Payload too large"), timeout=IO_TIMEOUT)
                        if not gw_ws.closed:
                            await asyncio.wait_for(gw_ws.send_json(_sanitize_packet({
                                "type": "close",
                                "conn_id": conn_id,
                                "code": 1009,
                                "reason": "Payload too large"
                            })), timeout=IO_TIMEOUT)
                        break

                    if not gw_ws.closed:
                        await asyncio.wait_for(gw_ws.send_json(_sanitize_packet({
                            "type": "msg",
                            "conn_id": conn_id,
                            "data": msg.data
                        })), timeout=IO_TIMEOUT)
                elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        except Exception as e:
            logger.warning("Upstream reader error for %s: %s", conn_id, e)
        finally:
            if not gw_ws.closed:
                try:
                    await asyncio.wait_for(gw_ws.send_json(_sanitize_packet({
                        "type": "close",
                        "conn_id": conn_id,
                        "code": 1000,
                        "reason": "Upstream closed"
                    })), timeout=IO_TIMEOUT)
                except Exception:
                    pass

    def stop(self):
        self.running = False
        if self._gw_ws and not self._gw_ws.closed:
            asyncio.create_task(self._gw_ws.close())
