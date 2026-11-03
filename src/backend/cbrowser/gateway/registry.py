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
    ws: Any
    last_heartbeat: float
    # Last Selkies video state reported in an Agent HEARTBEAT; None until then.
    unpaused_video_consumers: int | None = None
    capture_running: bool | None = None


class AgentRegistry:
    """Manages active StreamAgent connections and detects lost heartbeats."""

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
        if current is not None and (ws is None or current.ws is ws):
            return self._agents.pop(profile_id)
        return None

    def update_heartbeat(
        self,
        profile_id: str,
        instance_id: str,
        agent_session_id: str | None = None,
        now: float | None = None,
        runtime_state: str | None = None,
    ) -> bool:
        """Only the registered session may extend liveness.

        A heartbeat also carries the Agent's current runtime_state; the
        registry record is kept in sync so control-plane reads never serve
        a stale registration-time state.
        """
        agent = self._agents.get(profile_id)
        if agent is None or agent.instance_id != instance_id:
            return False
        if agent_session_id is not None and (
            agent.agent_session_id != agent_session_id
        ):
            return False
        agent.last_heartbeat = self.now() if now is None else now
        if runtime_state is not None:
            agent.runtime_state = runtime_state
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
    """Registration abuse control with two separately-modelled budgets.

    - In-flight handshakes per source are bounded by a reservation that is
      released on *every* exit path (success, rejection, timeout, cancel).
    - Failed handshakes are recorded per source inside a sliding window;
      only failures consume that budget. A success releases its reservation
      and never erases other failures, so legitimate Agent recovery is not
      starved by the failure budget it did not spend, and an attacker
      cannot reset the window by succeeding once.

    Keys are transport source addresses only — never an unauthenticated
    claimed identity — and the number of tracked sources is bounded.
    """

    def __init__(
        self,
        max_inflight: int = 4,
        max_failures: int = 20,
        window_seconds: float = 60.0,
        max_sources: int = 1024,
    ) -> None:
        self.max_inflight = max_inflight
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.max_sources = max_sources
        self._inflight: dict[str, int] = {}
        self._failures: dict[str, list[float]] = {}

    def _prune_failures(self, key: str, clock: float) -> list[float]:
        failures = self._failures.setdefault(key, [])
        cutoff = clock - self.window_seconds
        while failures and failures[0] < cutoff:
            failures.pop(0)
        return failures

    def _evict_sources(self, clock: float, *, protect: str) -> None:
        """Bound the tracked-source maps without breaking live state.

        A source is evictable only when it holds no in-flight reservation
        and is not the source of the operation in progress: evicting a
        source with reservations would silently drop its in-flight count
        (defeating max_inflight) and erasing its failure history would let
        flooding reset the failure budget (review t022_code_f002). When
        every tracked source is live, the cap is exceeded temporarily —
        bounded by actual concurrency — rather than corrupting state.
        """
        if len(self._failures) <= self.max_sources:
            return
        cutoff = clock - self.window_seconds
        for stale in [
            source
            for source, values in self._failures.items()
            if source != protect
            and self._inflight.get(source, 0) == 0
            and (not values or values[-1] < cutoff)
        ]:
            self._failures.pop(stale, None)
            self._inflight.pop(stale, None)
        while len(self._failures) > self.max_sources:
            # Prefer sources carrying no failure history at all; among the
            # rest evict the least recently active, so a flood of fresh
            # sources cannot flush the history of sources that are still
            # actively failing.
            candidates = [
                source
                for source in self._failures
                if source != protect and self._inflight.get(source, 0) == 0
            ]
            if not candidates:
                break
            victim = min(
                candidates,
                key=lambda source: (
                    bool(self._failures[source]),
                    self._failures[source][-1] if self._failures[source] else 0.0,
                ),
            )
            self._failures.pop(victim, None)
            self._inflight.pop(victim, None)

    def reserve(self, peer: str | None, now: float | None = None) -> bool:
        """Reserve an in-flight handshake slot; False means refuse (429)."""
        clock = time.monotonic() if now is None else now
        key = peer or "unknown"
        failures = self._prune_failures(key, clock)
        if len(failures) >= self.max_failures:
            return False
        if self._inflight.get(key, 0) >= self.max_inflight:
            return False
        self._inflight[key] = self._inflight.get(key, 0) + 1
        self._evict_sources(clock, protect=key)
        return True

    def release(
        self, peer: str | None, *, success: bool, now: float | None = None
    ) -> None:
        """Release a reservation; failures are recorded, successes are not."""
        clock = time.monotonic() if now is None else now
        key = peer or "unknown"
        remaining = self._inflight.get(key, 0) - 1
        if remaining > 0:
            self._inflight[key] = remaining
        else:
            self._inflight.pop(key, None)
        if not success:
            failures = self._prune_failures(key, clock)
            failures.append(clock)
            self._evict_sources(clock, protect=key)


class AuthorizationThrottle:
    """Bounded failed Viewer authorization attempts per source and Profile."""

    def __init__(self, max_failures: int = 10, window_seconds: float = 60.0) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[tuple[str, str], list[float]] = {}

    def allow(
        self, source: str | None, profile_id: str, now: float | None = None
    ) -> bool:
        clock = time.monotonic() if now is None else now
        key = (source or "unknown", profile_id)
        failures = self._failures.get(key, [])
        cutoff = clock - self.window_seconds
        while failures and failures[0] < cutoff:
            failures.pop(0)
        return len(failures) < self.max_failures

    def record_failure(
        self, source: str | None, profile_id: str, now: float | None = None
    ) -> None:
        clock = time.monotonic() if now is None else now
        key = (source or "unknown", profile_id)
        failures = self._failures.setdefault(key, [])
        failures.append(clock)
        cutoff = clock - self.window_seconds
        while failures and failures[0] < cutoff:
            failures.pop(0)
        if len(self._failures) > 1024:
            for stale in [
                entry
                for entry, values in self._failures.items()
                if not values or values[-1] < cutoff
            ]:
                self._failures.pop(stale, None)
        while len(self._failures) > 1024:
            self._failures.pop(next(iter(self._failures)))
