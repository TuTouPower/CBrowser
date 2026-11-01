"""In-memory active Stream Agent registry and liveness monitor."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class RegisteredAgent:
    profile_id: str
    instance_id: str
    agent_session_id: str
    selkies_version: str
    runtime_state: str
    udp_port: int
    config_version: int
    turn_host: str
    turn_port: int
    ws: Any
    last_heartbeat: float
    # Last Selkies video state reported in an Agent HEARTBEAT; None until then.
    unpaused_video_consumers: int | None = None
    capture_running: bool | None = None


class AgentRegistry:
    """Manages active StreamAgent connections and detects lost heartbeats (>30s)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._agents: dict[str, RegisteredAgent] = {}
        self._clock = clock

    def now(self) -> float:
        return self._clock()

    def register(self, agent: RegisteredAgent) -> RegisteredAgent | None:
        """Registers agent for profile, returning previous agent if replaced."""
        old = self._agents.get(agent.profile_id)
        self._agents[agent.profile_id] = agent
        return old

    def get(self, profile_id: str) -> RegisteredAgent | None:
        return self._agents.get(profile_id)

    def remove(self, profile_id: str, ws: Any | None = None) -> RegisteredAgent | None:
        """Removes the agent if currently registered (and matches ws if provided)."""
        current = self._agents.get(profile_id)
        if current is not None:
            if ws is None or current.ws is ws:
                return self._agents.pop(profile_id)
        return None

    def update_heartbeat(
        self,
        profile_id: str,
        instance_id: str,
        agent_session_id: str | None = None,
        now: float | None = None,
    ) -> bool:
        """Only the registered session may extend liveness."""
        agent = self._agents.get(profile_id)
        if agent is None or agent.instance_id != instance_id:
            return False
        if agent_session_id is not None and (
            agent.agent_session_id != agent_session_id
        ):
            return False
        agent.last_heartbeat = self.now() if now is None else now
        return True

    def check_heartbeat_timeouts(
        self, now: float | None = None, timeout_sec: float = 30.0
    ) -> list[RegisteredAgent]:
        """Identifies and evicts agents that exceeded heartbeat timeout_sec."""
        t = self.now() if now is None else now
        timed_out: list[RegisteredAgent] = []
        for pid, agent in list(self._agents.items()):
            if (t - agent.last_heartbeat) > timeout_sec:
                timed_out.append(agent)
                self._agents.pop(pid, None)
        return timed_out

    def all_agents(self) -> list[RegisteredAgent]:
        return list(self._agents.values())


class RegistrationThrottle:
    """Bounded per-source registration attempts for the Agent handshake."""

    def __init__(self, max_attempts: int = 20, window_seconds: float = 60.0) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}

    def allow(self, peer: str | None, now: float | None = None) -> bool:
        clock = time.monotonic() if now is None else now
        key = peer or "unknown"
        attempts = self._attempts.setdefault(key, [])
        cutoff = clock - self.window_seconds
        while attempts and attempts[0] < cutoff:
            attempts.pop(0)
        if len(attempts) >= self.max_attempts:
            return False
        attempts.append(clock)
        if len(self._attempts) > 1024:
            for stale in [
                source
                for source, values in self._attempts.items()
                if not values or values[-1] < cutoff
            ]:
                self._attempts.pop(stale, None)
        return True
