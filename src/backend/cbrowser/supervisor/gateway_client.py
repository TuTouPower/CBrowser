"""Authenticated, instance-fenced control RPC from Supervisor to Gateway."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx
from cbrowser.secret_files import read_secret_file
from pydantic import SecretStr


class GatewayControlClient:
    def __init__(self, base_url: str, token_file: Path) -> None:
        try:
            token = read_secret_file(
                token_file,
                label="Gateway control token",
                minimum_bytes=32,
            )
        except RuntimeError as exc:
            raise ValueError(str(exc)) from None
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

    async def agent_registered(
        self, profile_id: str, runtime_instance_id: str
    ) -> bool | None:
        """Whether this exact instance is registered with the Gateway.

        Returns None when the Gateway itself cannot be reached, so the
        caller can distinguish "Gateway down" (never a reason to rebuild
        a Stream) from "Agent absent" (a replacement candidate). The
        visibility route's fence distinguishes the states: 409 is a
        different live instance, a 503 "unavailable" message is no agent,
        and a 503 "has not reported yet" still means registered.
        """
        try:
            response = await self._client.get(
                self._path(profile_id, "visibility"),
                headers=self._headers(),
                params={"runtime_instance_id": runtime_instance_id},
            )
        except (httpx.HTTPError, OSError):
            return None
        if response.status_code == 200:
            return True
        if response.status_code == 409:
            return False
        if response.status_code == 503:
            try:
                body = response.json()
            except ValueError:
                body = {}
            # Unified ErrorResponse carries the reason in `message`; keep
            # the legacy `detail` read so a mixed-version Gateway still
            # parses (t056 A15).
            if isinstance(body, dict):
                text = body.get("message") or body.get("detail") or ""
            else:
                text = ""
            return "unavailable" not in str(text)
        return None

    async def registration_status(self, profile_id: str) -> dict | None:
        """Full registration diagnostics (state + structured refusal).

        Returns None when the Gateway cannot be reached.
        """
        try:
            response = await self._client.get(
                self._path(profile_id, "registration"),
                headers=self._headers(),
            )
        except (httpx.HTTPError, OSError):
            return None
        if response.status_code != 200:
            return None
        try:
            value = response.json()
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    async def close(self) -> None:
        await self._client.aclose()
