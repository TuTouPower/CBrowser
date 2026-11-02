"""Public Supervisor Gateway Test Fixture.

Provides a real aiohttp localhost service implementing the Gateway contract:
- Stream Agent WebSocket registration (/stream/agent/register)
  with HMAC token verification.
- Internal control plane RPC:
  - GET  /gateway/v1/internal/profiles/{profile_id}/visibility
  - POST /gateway/v1/internal/profiles/{profile_id}/quota
  - POST /gateway/v1/internal/profiles/{profile_id}/disconnect
- Test viewer WebSocket endpoint (/viewer/{profile_id}).
- Strict instance fencing and constant-time Bearer token authentication.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any, Self

from aiohttp import WSMsgType, web
from cbrowser.supervisor.agent_credentials import AgentCredentials

logger = logging.getLogger("cbrowser.fixtures.supervisor_gateway")


class RegisteredAgentInfo:
    def __init__(
        self,
        profile_id: str,
        instance_id: str,
        agent_session_id: str,
        ws: web.WebSocketResponse,
    ) -> None:
        self.profile_id = profile_id
        self.instance_id = instance_id
        self.agent_session_id = agent_session_id
        self.ws = ws


class SupervisorGatewayFixture:
    """Real aiohttp localhost Gateway server for Supervisor E2E tests."""

    def __init__(
        self,
        port: int,
        credentials: AgentCredentials,
        token_file: Path,
    ) -> None:
        self.port = port
        self.credentials = credentials
        token_path = Path(token_file)
        token_val = token_path.read_text(encoding="utf-8").strip()
        if len(token_val.encode("utf-8")) < 32:
            raise ValueError("Gateway control token must contain at least 32 bytes")
        self._token = token_val.encode("utf-8")

        self.registered_agents: set[str] = set()
        self._agents: dict[str, RegisteredAgentInfo] = {}
        self._viewers: dict[str, set[web.WebSocketResponse]] = {}
        self._foreground_viewers: dict[str, set[web.WebSocketResponse]] = {}
        self._quota_messages: list[dict[str, Any]] = []
        self._all_sockets: list[web.WebSocketResponse] = []

        self._app = web.Application()
        self._setup_routes()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def _setup_routes(self) -> None:
        self._app.router.add_get("/stream/agent/register", self._handle_agent_register)
        self._app.router.add_get(
            "/gateway/v1/internal/profiles/{profile_id}/visibility",
            self._handle_visibility,
        )
        self._app.router.add_post(
            "/gateway/v1/internal/profiles/{profile_id}/quota",
            self._handle_quota,
        )
        self._app.router.add_post(
            "/gateway/v1/internal/profiles/{profile_id}/disconnect",
            self._handle_disconnect,
        )
        self._app.router.add_get("/viewer/{profile_id}", self._handle_viewer_ws)

    @property
    def control_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def gateway_url(self) -> str:
        return f"ws://host.docker.internal:{self.port}"

    def get_agent(self, profile_id: str) -> RegisteredAgentInfo | None:
        return self._agents.get(profile_id)

    async def wait_for_agent(
        self, profile_id: str, timeout_sec: float = 10.0
    ) -> RegisteredAgentInfo:
        deadline = asyncio.get_running_loop().time() + timeout_sec
        while asyncio.get_running_loop().time() < deadline:
            agent = self._agents.get(profile_id)
            if agent is not None and not agent.ws.closed:
                return agent
            await asyncio.sleep(0.1)
        raise TimeoutError(
            f"Agent for profile {profile_id} did not register within {timeout_sec}s"
        )

    def _check_control_auth(self, request: web.Request) -> web.Response | None:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return web.json_response(
                {"detail": "Missing or invalid Bearer authorization header"},
                status=401,
            )
        provided = auth[len("Bearer ") :].strip().encode("utf-8")
        if not hmac.compare_digest(provided, self._token):
            return web.json_response(
                {"detail": "Unauthorized control token"}, status=401
            )
        return None

    async def _handle_visibility(self, request: web.Request) -> web.Response:
        auth_err = self._check_control_auth(request)
        if auth_err:
            return auth_err

        profile_id = request.match_info["profile_id"]
        runtime_instance_id = request.query.get("runtime_instance_id")
        if not runtime_instance_id:
            return web.json_response(
                {"detail": "runtime_instance_id query parameter is required"},
                status=400,
            )

        agent = self._agents.get(profile_id)
        if agent is None or agent.ws.closed:
            return web.json_response(
                {"detail": f"Agent for profile {profile_id} is unavailable"},
                status=503,
            )
        if agent.instance_id != runtime_instance_id:
            return web.json_response(
                {
                    "detail": (
                        "Instance fence conflict: "
                        f"active instance is {agent.instance_id}, "
                        f"requested {runtime_instance_id}"
                    )
                },
                status=409,
            )

        fg_viewers = self._foreground_viewers.get(profile_id, set())
        has_fg = any(not v.closed for v in fg_viewers)
        return web.json_response({"has_foreground_viewers": has_fg})

    async def _handle_quota(self, request: web.Request) -> web.Response:
        auth_err = self._check_control_auth(request)
        if auth_err:
            return auth_err

        profile_id = request.match_info["profile_id"]
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return web.json_response({"detail": "Invalid JSON body"}, status=400)

        runtime_instance_id = body.get("runtime_instance_id")
        if not runtime_instance_id:
            return web.json_response(
                {"detail": "runtime_instance_id is required in body"},
                status=400,
            )

        agent = self._agents.get(profile_id)
        if agent is None or agent.ws.closed:
            return web.json_response(
                {"detail": f"Agent for profile {profile_id} is unavailable"},
                status=503,
            )
        if agent.instance_id != runtime_instance_id:
            return web.json_response(
                {
                    "detail": (
                        "Instance fence conflict: "
                        f"active instance is {agent.instance_id}, "
                        f"requested {runtime_instance_id}"
                    )
                },
                status=409,
            )

        max_fps_cap = body.get("max_fps_cap")
        envelope = {
            "version": "v2",
            "action": "supervisor_quota",
            "profile_id": profile_id,
            "runtime_instance_id": agent.instance_id,
            "agent_session_id": agent.agent_session_id,
            "payload": {
                "max_fps_cap": max_fps_cap,
            },
        }
        self._quota_messages.append(envelope)
        if not agent.ws.closed:
            await agent.ws.send_json(envelope)

        return web.json_response({"status": "ok"})

    async def _handle_disconnect(self, request: web.Request) -> web.Response:
        auth_err = self._check_control_auth(request)
        if auth_err:
            return auth_err

        profile_id = request.match_info["profile_id"]
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return web.json_response({"detail": "Invalid JSON body"}, status=400)

        runtime_instance_id = body.get("runtime_instance_id")
        if not runtime_instance_id:
            return web.json_response(
                {"detail": "runtime_instance_id is required in body"},
                status=400,
            )

        agent = self._agents.get(profile_id)
        if agent is None or agent.ws.closed:
            return web.json_response(
                {"detail": f"Agent for profile {profile_id} is unavailable"},
                status=503,
            )
        if agent.instance_id != runtime_instance_id:
            return web.json_response(
                {
                    "detail": (
                        "Instance fence conflict: "
                        f"active instance is {agent.instance_id}, "
                        f"requested {runtime_instance_id}"
                    )
                },
                status=409,
            )

        # Disconnect viewer WebSockets only; do NOT disconnect Agent WS
        viewers = list(self._viewers.get(profile_id, set()))
        for v_ws in viewers:
            if not v_ws.closed:
                await v_ws.close(code=1000, message=b"Supervisor disconnected viewers")
        self._viewers.get(profile_id, set()).clear()
        self._foreground_viewers.get(profile_id, set()).clear()

        return web.json_response({"status": "ok"})

    async def _handle_viewer_ws(self, request: web.Request) -> web.WebSocketResponse:
        profile_id = request.match_info["profile_id"]
        is_foreground = request.query.get("foreground", "false").lower() in (
            "1",
            "true",
            "yes",
        )

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._all_sockets.append(ws)
        self._viewers.setdefault(profile_id, set()).add(ws)
        if is_foreground:
            self._foreground_viewers.setdefault(profile_id, set()).add(ws)

        try:
            async for msg in ws:
                if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
                elif msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if data.get("action") == "visibility":
                            fg = bool(data.get("foreground", False))
                            if fg:
                                self._foreground_viewers.setdefault(
                                    profile_id, set()
                                ).add(ws)
                            else:
                                self._foreground_viewers.get(profile_id, set()).discard(
                                    ws
                                )
                    except Exception as exc:  # noqa: BLE001 - isolate viewer frame errors to keep connection alive
                        logger.debug(
                            "Failed to process viewer message: %s", type(exc).__name__
                        )
        finally:
            self._viewers.get(profile_id, set()).discard(ws)
            self._foreground_viewers.get(profile_id, set()).discard(ws)
            if ws in self._all_sockets:
                self._all_sockets.remove(ws)

        return ws

    async def _handle_agent_register(
        self, request: web.Request
    ) -> web.WebSocketResponse:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return web.Response(status=401, text="Unauthorized Agent")
        raw_token = auth.removeprefix("Bearer ").strip()

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._all_sockets.append(ws)

        msg = await ws.receive()
        if msg.type != WSMsgType.TEXT:
            await ws.close(code=1003, message=b"Expected text registration packet")
            return ws

        try:
            reg_data = json.loads(msg.data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            await ws.close(code=1003, message=b"Malformed JSON registration packet")
            return ws

        pid = reg_data.get("profile_id")
        iid = reg_data.get("runtime_instance_id")
        if not pid or not iid:
            await ws.close(
                code=1008, message=b"Missing profile_id or runtime_instance_id"
            )
            return ws

        if not self.credentials.verify(raw_token, pid, iid):
            await ws.close(code=1008, message=b"Invalid Agent credentials")
            return ws

        session_id = str(uuid.uuid4())
        agent_info = RegisteredAgentInfo(
            profile_id=pid,
            instance_id=iid,
            agent_session_id=session_id,
            ws=ws,
        )

        old_agent = self._agents.get(pid)
        if old_agent and not old_agent.ws.closed:
            try:
                await old_agent.ws.close(
                    code=1000, message=b"Superceded by new registration"
                )
            except Exception as exc:  # noqa: BLE001 - best effort close superseded socket
                logger.debug(
                    "Closing superseded agent socket failed: %s", type(exc).__name__
                )

        self._agents[pid] = agent_info
        self.registered_agents.add(pid)

        await ws.send_json(
            {
                "version": "v2",
                "status": "ok",
                "profile_id": pid,
                "runtime_instance_id": iid,
                "agent_session_id": session_id,
            }
        )

        try:
            async for m in ws:
                if m.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        finally:
            if self._agents.get(pid) and self._agents[pid].ws is ws:
                for viewer in list(self._viewers.get(pid, set())):
                    if not viewer.closed:
                        await viewer.close(
                            code=1001, message=b"Stream Agent disconnected"
                        )
                self._viewers.pop(pid, None)
                self._foreground_viewers.pop(pid, None)
                del self._agents[pid]
                self.registered_agents.discard(pid)
            if ws in self._all_sockets:
                self._all_sockets.remove(ws)

        return ws

    async def start(self) -> None:
        ready_event = threading.Event()
        self._loop = asyncio.new_event_loop()

        def _run() -> None:
            assert self._loop is not None
            asyncio.set_event_loop(self._loop)

            async def _init() -> None:
                self._runner = web.AppRunner(self._app)
                await self._runner.setup()
                self._site = web.TCPSite(self._runner, "127.0.0.1", self.port)
                await self._site.start()
                ready_event.set()

            self._loop.create_task(_init())
            self._loop.run_forever()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        await asyncio.to_thread(ready_event.wait, 10.0)
        logger.info(f"SupervisorGatewayFixture running on 127.0.0.1:{self.port}")

    async def stop(self) -> None:
        if self._loop and self._loop.is_running():

            async def _cleanup() -> None:
                try:
                    # 1. Close all viewers
                    for ws_set in list(self._viewers.values()):
                        for ws in list(ws_set):
                            if not ws.closed:
                                await ws.close(
                                    code=1000, message=b"Gateway fixture stopping"
                                )
                    self._viewers.clear()
                    self._foreground_viewers.clear()

                    # 2. Close all agent sockets
                    for agent in list(self._agents.values()):
                        if not agent.ws.closed:
                            await agent.ws.close(
                                code=1000, message=b"Gateway fixture stopping"
                            )
                    self._agents.clear()
                    self.registered_agents.clear()

                    # 3. Close any lingering sockets
                    for ws in list(self._all_sockets):
                        if not ws.closed:
                            await ws.close(
                                code=1000, message=b"Gateway fixture stopping"
                            )
                    self._all_sockets.clear()
                finally:
                    if self._site:
                        await self._site.stop()
                        self._site = None
                    if self._runner:
                        await self._runner.cleanup()
                        self._runner = None

            fut = asyncio.run_coroutine_threadsafe(_cleanup(), self._loop)
            await asyncio.to_thread(fut.result, 5.0)
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                await asyncio.to_thread(self._thread.join, 5.0)
                self._thread = None
            self._loop = None
        logger.info(f"SupervisorGatewayFixture stopped on port {self.port}")

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
