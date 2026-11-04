"""In-memory registry of live automation tunnels, one per layer (t031).

The API and the Supervisor each hold one registry. A tunnel is
registered at proxy-handshake time (after authentication and the
control claim) and unregistered when the proxy task tears down. A
takeover closes every registered tunnel for the profile through the
stored close callback, so enforcement is connection teardown, not
per-message filtering: after the boundary, no stale tunnel can deliver
another command, and a reconnect must pass the control claim again.

The registry never persists: a process restart drops every tunnel with
it, which is itself a safe state (control resets to ``user``).
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import time

from cbrowser.domain.models import utc_now_iso

logger = logging.getLogger("cbrowser.services.tunnel_registry")


class TunnelRecord:
    def __init__(
        self,
        tunnel_id: str,
        profile_id: str,
        layer: str,
        generation: int | None,
        close_callback,
        *,
        agent_instance_id: str | None = None,
        agent_session_id: str | None = None,
    ):
        self.tunnel_id = tunnel_id
        self.profile_id = profile_id
        self.layer = layer
        self.generation = generation
        self.close_callback = close_callback
        self.agent_instance_id = agent_instance_id
        self.agent_session_id = agent_session_id
        self.opened_at = utc_now_iso()
        self._opened_monotonic = time.monotonic()

    def to_data(self) -> dict:
        return {
            "tunnel_id": self.tunnel_id,
            "profile_id": self.profile_id,
            "layer": self.layer,
            "generation": self.generation,
            "agent_instance_id": self.agent_instance_id,
            "agent_session_id": self.agent_session_id,
            "opened_at": self.opened_at,
        }


class AutomationTunnelRegistry:
    """Thread-safe (single-loop) registry of live tunnels."""

    def __init__(self, layer: str):
        self.layer = layer
        self._tunnels: dict[str, TunnelRecord] = {}
        self._counter = itertools.count(1)
        self._fenced_generation: dict[str, int] = {}

    def register(
        self,
        profile_id: str,
        close_callback,
        *,
        generation: int | None = None,
        agent_instance_id: str | None = None,
        agent_session_id: str | None = None,
    ) -> TunnelRecord:
        tunnel_id = f"{self.layer}-{next(self._counter)}"
        record = TunnelRecord(
            tunnel_id,
            profile_id,
            self.layer,
            generation,
            close_callback,
            agent_instance_id=agent_instance_id,
            agent_session_id=agent_session_id,
        )
        self._tunnels[tunnel_id] = record
        return record

    def unregister(self, tunnel_id: str) -> None:
        self._tunnels.pop(tunnel_id, None)

    def list_for_profile(self, profile_id: str) -> list[TunnelRecord]:
        return [
            record
            for record in self._tunnels.values()
            if record.profile_id == profile_id
        ]

    def fence_generation(self, profile_id: str) -> int | None:
        """Generation below which forwarded handshakes are stale."""
        return self._fenced_generation.get(profile_id)

    async def close_all_for_profile(
        self, profile_id: str, *, generation: int | None = None
    ) -> list[str]:
        """Close every live tunnel for the profile; return closed ids.

        When ``generation`` is given, the fence advances to it (monotonic):
        later forwarded handshakes presenting a generation at or below
        the fence are stale and must be rejected by the proxy.
        """
        if generation is not None:
            previous = self._fenced_generation.get(profile_id)
            if previous is None or generation > previous:
                self._fenced_generation[profile_id] = generation
        records = self.list_for_profile(profile_id)
        closed: list[str] = []
        for record in records:
            try:
                result = record.close_callback()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001 - close is best-effort
                logger.debug(
                    "Tunnel close failed: tunnel=%s", record.tunnel_id
                )
            finally:
                self._tunnels.pop(record.tunnel_id, None)
                closed.append(record.tunnel_id)
        return closed

    def is_generation_fenced(
        self, profile_id: str, generation: int | None
    ) -> bool:
        """True when a presented generation is stale for this profile."""
        if generation is None:
            return False
        fence = self._fenced_generation.get(profile_id)
        return fence is not None and generation <= fence
