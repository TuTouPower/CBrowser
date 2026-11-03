"""Reusable integration test harness for Stream Gateway with a minimal API."""

from __future__ import annotations

import secrets
import socket
from pathlib import Path
from typing import Any

from aiohttp import web
from cbrowser.gateway.config import GatewayConfig
from cbrowser.gateway.server import create_gateway_app
from cbrowser.supervisor.agent_credentials import AgentCredentials


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeApiService:
    """Minimal fake API implementing /api/v1/internal/gateway/* for gateway tests."""

    # The origin every viewer grant in this harness defaults to; it matches
    # the GatewayHarness allowed_origins entry the suites connect with.
    DEFAULT_VIEWER_ORIGIN = "https://localhost:8443"

    def __init__(self, port: int, token: str) -> None:
        self.port = port
        self.token = token
        self.app = web.Application()
        self.profile_runtimes: dict[str, dict[str, Any]] = {}
        # Authorization is keyed by (cookie, origin, profile_id) and denied
        # by default, mirroring the production internal API and the recovery
        # lane's FakeGatewayApiClient (t024 AC-004/A25): a grant for one
        # origin never authorizes another.
        self.viewer_auths: dict[tuple[str, str, str], tuple[bool, str | None]] = {}

        self.app.router.add_get(
            "/api/v1/internal/gateway/profiles/{profile_id}/runtime",
            self.handle_profile_runtime,
        )
        self.app.router.add_post(
            "/api/v1/internal/gateway/viewer-authorize",
            self.handle_viewer_authorize,
        )
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

    def set_profile_runtime(
        self,
        profile_id: str,
        runtime_instance_id: str,
        observed_state: str = "running",
        config_version: int = 1,
        desired_state: str = "running",
    ) -> None:
        self.profile_runtimes[profile_id] = {
            "runtime_instance_id": runtime_instance_id,
            "config_version": config_version,
            "desired_state": desired_state,
            "observed_state": observed_state,
        }

    def set_viewer_auth(
        self,
        cookie: str,
        profile_id: str,
        allowed: bool = True,
        reason: str | None = None,
        *,
        origin: str = DEFAULT_VIEWER_ORIGIN,
    ) -> None:
        self.viewer_auths[(cookie, origin, profile_id)] = (allowed, reason)

    async def handle_profile_runtime(self, request: web.Request) -> web.Response:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {self.token}":
            return web.json_response({"detail": "Unauthorized API token"}, status=401)
        profile_id = request.match_info["profile_id"]
        info = self.profile_runtimes.get(profile_id)
        if not info:
            return web.json_response({"detail": "Profile not found"}, status=404)
        return web.json_response(info)

    async def handle_viewer_authorize(self, request: web.Request) -> web.Response:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {self.token}":
            return web.json_response({"detail": "Unauthorized API token"}, status=401)
        body = await request.json()
        cookie = body.get("session_cookie", "")
        origin = body.get("origin", "")
        profile_id = body.get("profile_id", "")
        allowed, reason = self.viewer_auths.get(
            (cookie, origin, profile_id), (False, "Unauthorized session")
        )
        return web.json_response({"allowed": allowed, "reason": reason})

    async def start(self) -> None:
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", self.port)
        await self.site.start()

    async def stop(self) -> None:
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()


class GatewayHarness:
    """Spins up a real Gateway application and FakeApiService on localhost."""

    def __init__(
        self,
        tmp_path: Path,
        agent_heartbeat_timeout_sec: float = 30.0,
    ) -> None:
        self.tmp_path = tmp_path
        self.tmp_path.mkdir(parents=True, exist_ok=True)
        self.agent_key_bytes = secrets.token_urlsafe(32)
        self.gw_token_str = secrets.token_urlsafe(32)
        self.api_token_str = secrets.token_urlsafe(32)

        self.agent_key_file = tmp_path / "agent_key.txt"
        self.agent_key_file.write_text(self.agent_key_bytes, encoding="utf-8")
        self.agent_key_file.chmod(0o600)

        self.gw_token_file = tmp_path / "gw_token.txt"
        self.gw_token_file.write_text(self.gw_token_str, encoding="utf-8")
        self.gw_token_file.chmod(0o600)

        self.api_token_file = tmp_path / "api_token.txt"
        self.api_token_file.write_text(self.api_token_str, encoding="utf-8")
        self.api_token_file.chmod(0o600)

        self.agent_credentials = AgentCredentials(self.agent_key_file)

        self.api_port = find_free_port()
        self.gw_port = find_free_port()

        self.api_service = FakeApiService(port=self.api_port, token=self.api_token_str)

        self.config = GatewayConfig(
            host="127.0.0.1",
            port=self.gw_port,
            agent_key_file=self.agent_key_file,
            gateway_token_file=self.gw_token_file,
            api_url=f"http://127.0.0.1:{self.api_port}",
            api_token_file=self.api_token_file,
            allowed_origins=["https://localhost:8443", "http://127.0.0.1:3000"],
            agent_heartbeat_timeout_sec=agent_heartbeat_timeout_sec,
        )

        self.app = create_gateway_app(self.config)
        self.gw_runner: web.AppRunner | None = None
        self.gw_site: web.TCPSite | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.gw_port}"

    @property
    def ws_url(self) -> str:
        return f"ws://127.0.0.1:{self.gw_port}"

    async def start(self) -> None:
        await self.api_service.start()
        # A fresh app per start: aiohttp applications are single-use and the
        # previous instance's cleanup closed its API client (gateway restart
        # scenarios, t022/A39, rely on this).
        self.app = create_gateway_app(self.config)
        self.gw_runner = web.AppRunner(self.app)
        await self.gw_runner.setup()
        self.gw_site = web.TCPSite(self.gw_runner, "127.0.0.1", self.gw_port)
        await self.gw_site.start()

    async def stop(self) -> None:
        if self.gw_site:
            await self.gw_site.stop()
        if self.gw_runner:
            await self.gw_runner.cleanup()
        await self.api_service.stop()
