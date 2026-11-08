"""Production Gateway harness for Supervisor integration and recovery tests.

The harness runs the real ``cbrowser.gateway.server.create_gateway_app`` and only
supplies a minimal fake API client for the two Gateway -> API calls.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from aiohttp import web
from cbrowser.gateway.config import GatewayConfig
from cbrowser.gateway.server import create_gateway_app

logger = logging.getLogger("cbrowser.fixtures.production_gateway")


class ApiRuntimeLookup:
    """Reads the authoritative runtime binding from the real API subprocess."""

    def __init__(self, api_url: str, token_file: Path) -> None:
        token = Path(token_file).read_text(encoding="utf-8").strip()
        self._client = httpx.AsyncClient(
            base_url=api_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
            trust_env=False,
        )

    async def __call__(self, profile_id: str) -> dict[str, Any] | None:
        path = (
            "/api/v1/internal/supervisor/profiles/"
            f"{quote(profile_id, safe='')}/runtime"
        )
        try:
            response = await self._client.get(path)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - transport/decode failure means unavailable
            logger.warning(
                "Runtime lookup failed for profile %s: %s",
                profile_id,
                type(exc).__name__,
            )
            return None

    async def close(self) -> None:
        await self._client.aclose()


class FakeGatewayApiClient:
    """Minimal fake for the Gateway -> API authorization surface."""

    def __init__(self, runtime_lookup: ApiRuntimeLookup | None = None) -> None:
        self.runtime_lookup = runtime_lookup
        self.profile_runtimes: dict[str, dict[str, Any]] = {}
        self.allow_all_viewers = False
        self.viewer_authorizations: dict[
            tuple[str, str, str], tuple[bool, str | None]
        ] = {}
        self.viewer_authorize_calls: list[tuple[str, str, str]] = []

    def set_profile_runtime(
        self,
        profile_id: str,
        runtime_instance_id: str,
        observed_state: str = "running",
        config_version: int = 1,
        desired_state: str = "running",
    ) -> None:
        self.profile_runtimes[profile_id] = {
            "profile_id": profile_id,
            "runtime_instance_id": runtime_instance_id,
            "config_version": config_version,
            "desired_state": desired_state,
            "observed_state": observed_state,
        }

    def set_viewer_authorization(
        self,
        session_cookie: str,
        origin: str,
        profile_id: str,
        allowed: bool = True,
        reason: str | None = None,
    ) -> None:
        self.viewer_authorizations[(session_cookie, origin, profile_id)] = (
            allowed,
            reason,
        )

    async def get_profile_runtime(self, profile_id: str) -> dict[str, Any] | None:
        if self.runtime_lookup is not None:
            return await self.runtime_lookup(profile_id)
        info = self.profile_runtimes.get(profile_id)
        return dict(info) if info is not None else None

    async def authorize_viewer(
        self, session_cookie: str, origin: str, profile_id: str
    ) -> tuple[bool, str | None]:
        self.viewer_authorize_calls.append((session_cookie, origin, profile_id))
        if self.allow_all_viewers and session_cookie:
            return True, None
        return self.viewer_authorizations.get(
            (session_cookie, origin, profile_id),
            (False, "Viewer unauthorized"),
        )

    async def close(self) -> None:
        if self.runtime_lookup is not None:
            await self.runtime_lookup.close()


class ProductionGatewayService:
    """Runs the production Gateway application on localhost."""

    def __init__(
        self,
        port: int,
        agent_key_file: Path,
        gateway_token_file: Path,
        runtime_lookup: ApiRuntimeLookup | None = None,
        api_client: FakeGatewayApiClient | None = None,
        network_state_dir: Path | None = None,
        agent_heartbeat_timeout_sec: float = 30.0,
    ) -> None:
        self.port = port
        self.agent_key_file = Path(agent_key_file)
        self.gateway_token_file = Path(gateway_token_file)
        self.api = api_client or FakeGatewayApiClient(runtime_lookup=runtime_lookup)

        if network_state_dir is None:
            from cbrowser.network_config import create_default_applied_version, write_applied_network_state
            net_dir = self.agent_key_file.parent / "network"
            net_dir.mkdir(parents=True, exist_ok=True)
            v = create_default_applied_version()
            write_applied_network_state(net_dir, v, "caddyfile dummy")
            network_state_dir = net_dir

        self.config = GatewayConfig(
            host="127.0.0.1",
            port=port,
            agent_key_file=self.agent_key_file,
            gateway_token_file=self.gateway_token_file,
            api_url="http://api.invalid",
            api_token_file=self.gateway_token_file,
            network_state_dir=network_state_dir,
            agent_heartbeat_timeout_sec=agent_heartbeat_timeout_sec,
        )
        self.app = create_gateway_app(self.config, api_client=self.api)
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

    @property
    def control_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def gateway_url(self) -> str:
        return f"ws://host.docker.internal:{self.port}"

    async def start(self) -> None:
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", self.port)
        await self.site.start()

    async def stop(self) -> None:
        await self.api.close()
        if self.site is not None:
            await self.site.stop()
            self.site = None
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def __aenter__(self) -> ProductionGatewayService:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
