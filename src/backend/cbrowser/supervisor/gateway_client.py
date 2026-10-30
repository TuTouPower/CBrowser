"""Authenticated, instance-fenced control RPC from Supervisor to Gateway."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx
from pydantic import SecretStr


class GatewayControlClient:
    def __init__(self, base_url: str, token_file: Path) -> None:
        token = token_file.read_text(encoding="utf-8").strip()
        if len(token.encode("utf-8")) < 32:
            raise ValueError(
                "Gateway control authentication requires an external key "
                "of at least 32 bytes"
            )
        self._token = SecretStr(token)
        self._client = httpx.AsyncClient(base_url=base_url, timeout=5, trust_env=False)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token.get_secret_value()}"}

    def _path(self, profile_id: str, operation: str) -> str:
        return f"/gateway/v1/internal/profiles/{quote(profile_id, safe='')}/{operation}"

    async def disconnect_viewers(
        self, profile_id: str, runtime_instance_id: str
    ) -> None:
        response = await self._client.post(
            self._path(profile_id, "disconnect"),
            headers=self._headers(),
            json={"runtime_instance_id": runtime_instance_id},
        )
        response.raise_for_status()

    async def set_quota(
        self,
        profile_id: str,
        runtime_instance_id: str,
        max_fps_cap: float | None,
    ) -> None:
        response = await self._client.post(
            self._path(profile_id, "quota"),
            headers=self._headers(),
            json={
                "runtime_instance_id": runtime_instance_id,
                "max_fps_cap": max_fps_cap,
            },
        )
        response.raise_for_status()

    async def has_foreground_viewers(
        self, profile_id: str, runtime_instance_id: str
    ) -> bool:
        response = await self._client.get(
            self._path(profile_id, "visibility"),
            headers=self._headers(),
            params={"runtime_instance_id": runtime_instance_id},
        )
        response.raise_for_status()
        value = response.json().get("has_foreground_viewers")
        if type(value) is not bool:
            raise ValueError("Gateway visibility response requires a boolean")
        return value

    async def close(self) -> None:
        await self._client.aclose()
