"""Internal HTTP client for Gateway -> CBrowser API authorization."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import SecretStr

logger = logging.getLogger("cbrowser.gateway.api_client")


class GatewayApiClient:
    """Invokes CBrowser internal API endpoints for authorization and runtime state."""

    def __init__(self, base_url: str, token_file: Path | str) -> None:
        token = Path(token_file).read_text(encoding="utf-8").strip()
        if len(token.encode("utf-8")) < 32:
            raise ValueError("API token must contain at least 32 bytes")
        self._token = SecretStr(token)
        self._base_url = base_url.rstrip("/")
        # trust_env=False to avoid SOCKS proxy issues in test environments
        self._client = httpx.AsyncClient(
            base_url=self._base_url, timeout=5.0, trust_env=False
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token.get_secret_value()}"}

    async def get_profile_runtime(self, profile_id: str) -> dict[str, Any] | None:
        """Queries the currently bound runtime instance and state for a profile."""
        path = f"/api/v1/internal/gateway/profiles/{quote(profile_id, safe='')}/runtime"
        try:
            resp = await self._client.get(path, headers=self._headers())
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as e:  # noqa: BLE001 - transport or decode failure returns None safely
            logger.warning(
                "Failed to query runtime state for profile %s: %s",
                profile_id,
                type(e).__name__,
            )
            return None

    async def authorize_viewer(
        self, session_cookie: str, origin: str, profile_id: str
    ) -> tuple[bool, str | None]:
        """Validates session cookie, origin, and profile access with API."""
        path = "/api/v1/internal/gateway/viewer-authorize"
        try:
            resp = await self._client.post(
                path,
                headers=self._headers(),
                json={
                    "session_cookie": session_cookie,
                    "origin": origin,
                    "profile_id": profile_id,
                },
            )
            if resp.status_code in (200, 401, 403):
                data = resp.json()
                return bool(data.get("allowed", False)), data.get("reason")
            return False, f"API authorization error ({resp.status_code})"
        except Exception as e:  # noqa: BLE001 - transport failure fail-closes authorization
            logger.warning(
                "Viewer authorization call failed for profile %s: %s",
                profile_id,
                type(e).__name__,
            )
            return False, "API authorization unavailable"

    async def close(self) -> None:
        await self._client.aclose()
