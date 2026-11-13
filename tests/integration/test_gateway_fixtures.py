"""Reusable integration test harness for Stream Gateway with a minimal API."""

from __future__ import annotations

import secrets
import socket
from pathlib import Path
from typing import Any

from aiohttp import web
from cbrowser.gateway.config import GatewayConfig
from cbrowser.gateway.server import create_gateway_app
from cbrowser.shared.agent_credentials import AgentCredentials
from cbrowser.shared.viewer_grants import (
    AUTHORIZED_PROFILE_HEADER,
    VIEWER_GRANT_HEADER,
    ViewerGrantAuthority,
)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeApiService:
    """Minimal fake API implementing /api/v1/internal/gateway/* for gateway tests.

    Viewer authorization is not part of this surface anymore (t064): the
    Gateway verifies API-minted grants locally, so the fake API only
    serves the runtime-state endpoint the Gateway still calls.
    """

    def __init__(self, port: int, token: str) -> None:
        self.port = port
        self.token = token
        self.app = web.Application()
        self.profile_runtimes: dict[str, dict[str, Any]] = {}

        self.app.router.add_get(
            "/api/v1/internal/gateway/profiles/{profile_id}/runtime",
            self.handle_profile_runtime,
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

    async def handle_profile_runtime(self, request: web.Request) -> web.Response:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {self.token}":
            return web.json_response({"detail": "Unauthorized API token"}, status=401)
        profile_id = request.match_info["profile_id"]
        info = self.profile_runtimes.get(profile_id)
        if not info:
            return web.json_response({"detail": "Profile not found"}, status=404)
        return web.json_response(info)

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

        self.grant_key_file = tmp_path / "viewer_grant_key.txt"
        self.grant_key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        self.grant_key_file.chmod(0o600)

        self.agent_credentials = AgentCredentials(self.agent_key_file)
        self.grant_authority = ViewerGrantAuthority(self.grant_key_file)

        self.api_port = find_free_port()
        self.gw_port = find_free_port()

        self.api_service = FakeApiService(port=self.api_port, token=self.api_token_str)

        # t054: the Gateway derives its Origin whitelist from the deploy
        # port; the harness viewer origin is https://localhost:8443, so the
        # deploy port here is 8443 (was: seeded applied-state whitelist).
        self.config = GatewayConfig(
            host="127.0.0.1",
            port=self.gw_port,
            agent_key_file=self.agent_key_file,
            gateway_token_file=self.gw_token_file,
            api_url=f"http://127.0.0.1:{self.api_port}",
            api_token_file=self.api_token_file,
            viewer_grant_key_file=self.grant_key_file,
            https_port=8443,
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

    def viewer_headers(
        self, profile_id: str, origin: str = "https://localhost:8443"
    ) -> dict[str, str]:
        """Handshake headers as the edge delivers them (t064): the API
        has authorized this profile and the grant proves it; no cookie
        is ever sent to the Gateway."""
        return {
            "Origin": origin,
            AUTHORIZED_PROFILE_HEADER: profile_id,
            VIEWER_GRANT_HEADER: self.grant_authority.mint(profile_id),
        }

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
