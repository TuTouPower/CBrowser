"""In-memory active Stream Agent registry and liveness monitor."""

from __future__ import annotations

import time
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

    def __init__(self) -> None:
        self._agents: dict[str, RegisteredAgent] = {}

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
        self, profile_id: str, instance_id: str, now: float | None = None
    ) -> bool:
        agent = self._agents.get(profile_id)
        if agent and agent.instance_id == instance_id:
            agent.last_heartbeat = time.time() if now is None else now
            return True
        return False

    def check_heartbeat_timeouts(
        self, now: float | None = None, timeout_sec: float = 30.0
    ) -> list[RegisteredAgent]:
        """Identifies and evicts agents that exceeded heartbeat timeout_sec."""
        t = time.time() if now is None else now
        timed_out: list[RegisteredAgent] = []
        for pid, agent in list(self._agents.items()):
            if (t - agent.last_heartbeat) > timeout_sec:
                timed_out.append(agent)
                self._agents.pop(pid, None)
        return timed_out

    def all_agents(self) -> list[RegisteredAgent]:
        return list(self._agents.values())
