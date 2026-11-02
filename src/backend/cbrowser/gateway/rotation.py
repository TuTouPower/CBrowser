"""TURN credential rotation coordinator managing ICE restarts and generation cycles."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from cbrowser.rtc_config.models import RtcGeneration
from cbrowser.rtc_config.service import RtcConfigService
from cbrowser.stream_agent.protocol import (
    AgentAction,
    GatewayControlEnvelope,
    ProtocolEnvelope,
)

logger = logging.getLogger("cbrowser.gateway.rotation")

# Backstop above the Agent's own 20 s takeover bound (ICE_RESTART_COMMIT_TIMEOUT).
COMMIT_TIMEOUT_SEC = 30.0


class NoActiveGenerationError(RuntimeError):
    """No unexpired TURN generation exists for new connections."""


@dataclass(frozen=True)
class PendingHandshake:
    future: asyncio.Future
    generation: int
    profile_id: str


@dataclass
class ProfileRotationState:
    profile_id: str
    current_generation: RtcGeneration
    in_progress_generation: RtcGeneration | None = None
    migrated_connections: set[str] = field(default_factory=set)
    retry_count: int = 0
    next_retry_at: float = 0.0
    active_restarts: dict[str, asyncio.Task[None]] = field(default_factory=dict)


class RotationCoordinator:
    """Orchestrates periodic generation cycles and per-connection ICE restarts."""

    def __init__(
        self,
        rtc_service: RtcConfigService,
        send_agent_control: Callable[
            [GatewayControlEnvelope], Coroutine[Any, Any, None]
        ],
        send_viewer_control: Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]],
        get_active_connections: Callable[[str], list[str]],
        get_agent_info: Callable[[str], Any | None],
    ) -> None:
        self.rtc_service = rtc_service
        self._send_agent_control = send_agent_control
        self._send_viewer_control = send_viewer_control
        self._get_active_connections = get_active_connections
        self._get_agent_info = get_agent_info

        self._states: dict[str, ProfileRotationState] = {}
        # Pending futures for offer/answer handshakes, pinned to a generation.
        self._pending_offers: dict[str, PendingHandshake] = {}
        self._pending_answers: dict[str, PendingHandshake] = {}
        self._pending_commits: dict[str, PendingHandshake] = {}

    def get_or_create_state(
        self, profile_id: str, now: float | None = None
    ) -> ProfileRotationState:
        state = self._states.get(profile_id)
        if state is None:
            t = time.time() if now is None else now
            gen1 = self.rtc_service.generate_generation(
                profile_id=profile_id, generation_num=1, now=t
            )
            state = ProfileRotationState(profile_id=profile_id, current_generation=gen1)
            self._states[profile_id] = state
        return state

    def get_effective_generation(
        self, profile_id: str, now: float | None = None
    ) -> RtcGeneration:
        """Returns the latest valid generation for new connections."""
        state = self.get_or_create_state(profile_id, now=now)
        t = time.time() if now is None else now
        if (
            state.in_progress_generation is not None
            and not self.rtc_service.is_expired(state.in_progress_generation, t)
        ):
            return state.in_progress_generation
        if not self.rtc_service.is_expired(state.current_generation, t):
            return state.current_generation
        raise NoActiveGenerationError(
            "TURN credentials expired before rotation completed"
        )

    def register_connection(
        self, profile_id: str, conn_id: str, generation: RtcGeneration
    ) -> None:
        """A new connection already uses the in-progress generation."""
        state = self._states.get(profile_id)
        if (
            state is not None
            and state.in_progress_generation is not None
            and generation.generation == state.in_progress_generation.generation
        ):
            state.migrated_connections.add(conn_id)

    @staticmethod
    def _resolve_pending(
        pending: dict[str, PendingHandshake],
        conn_id: str | None,
        generation: int | None,
        value: Any,
        kind: str,
    ) -> None:
        entry = pending.get(conn_id or "")
        if entry is None:
            return
        if generation is not None and generation != entry.generation:
            logger.warning(
                "Dropped stale %s for conn=%s: expected generation %s, got %s",
                kind,
                conn_id,
                entry.generation,
                generation,
            )
            return
        if not entry.future.done():
            entry.future.set_result(value)

    def handle_agent_restart_offer(self, envelope: ProtocolEnvelope) -> None:
        """Called when an ICE_RESTART_OFFER is received from an Agent."""
        generation = envelope.payload.get("generation")
        self._resolve_pending(
            self._pending_offers,
            envelope.conn_id,
            generation if type(generation) is int else None,
            envelope,
            "ICE restart offer",
        )

    def handle_agent_restart_committed(self, envelope: ProtocolEnvelope) -> None:
        """Called when the Agent confirms the new ICE generation took over."""
        generation = envelope.payload.get("generation")
        self._resolve_pending(
            self._pending_commits,
            envelope.conn_id,
            generation if type(generation) is int else None,
            envelope,
            "ICE restart commit",
        )

    def handle_agent_error(self, envelope: ProtocolEnvelope) -> None:
        """Called when an ERROR action is received from an Agent."""
        conn_id = envelope.conn_id
        generation = envelope.payload.get("generation")
        generation = generation if type(generation) is int else None
        for pending in (self._pending_offers, self._pending_commits):
            entry = pending.get(conn_id or "")
            if entry is None:
                continue
            if generation is not None and generation != entry.generation:
                continue
            if not entry.future.done():
                entry.future.set_exception(
                    RuntimeError(f"Agent reported error for restart on {conn_id}")
                )

    def handle_viewer_restart_answer(self, conn_id: str, frame: dict[str, Any]) -> None:
        """Called when an ice_restart_answer control frame is received from a Viewer."""
        generation = frame.get("generation")
        self._resolve_pending(
            self._pending_answers,
            conn_id,
            generation if type(generation) is int else None,
            frame,
            "viewer ICE restart answer",
        )

    async def cancel_profile(self, profile_id: str) -> None:
        """Abort in-flight rotation work when the Profile's viewers go away."""
        state = self._states.get(profile_id)
        tasks: list[asyncio.Task[None]] = []
        if state is not None:
            tasks = list(state.active_restarts.values())
            state.active_restarts.clear()
            state.migrated_connections.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for pending in (
            self._pending_offers,
            self._pending_answers,
            self._pending_commits,
        ):
            for conn_id, entry in list(pending.items()):
                if entry.profile_id != profile_id:
                    continue
                pending.pop(conn_id, None)
                if not entry.future.done():
                    entry.future.cancel()

    async def tick(self, now: float | None = None) -> None:
        """Periodic check called by background rotation loop."""
        t = time.time() if now is None else now
        for profile_id in list(self._states.keys()):
            state = self._states[profile_id]

            # 1. Check if next generation should be generated
            if (
                state.in_progress_generation is None
                and self.rtc_service.should_generate_next(state.current_generation, t)
            ):
                next_gen_num = state.current_generation.generation + 1
                next_gen = self.rtc_service.generate_generation(
                    profile_id=profile_id, generation_num=next_gen_num, now=t
                )
                state.in_progress_generation = next_gen
                state.migrated_connections.clear()
                state.retry_count = 0
                state.next_retry_at = 0.0
                logger.info(
                    "Generated new RTC generation %d for profile %s",
                    next_gen_num,
                    profile_id,
                )

                # AC-004: Immediately sync new stream-side configuration
                # to registered Agent
                agent = self._get_agent_info(profile_id)
                if agent is not None and not agent.ws.closed:
                    env = GatewayControlEnvelope(
                        version="v2",
                        action=AgentAction.RTC_CONFIG,
                        profile_id=profile_id,
                        runtime_instance_id=agent.instance_id,
                        agent_session_id=agent.agent_session_id,
                        payload=next_gen.build_stream_rtc_config(
                            agent.turn_host, agent.turn_port
                        ),
                    )
                    try:
                        await self._send_agent_control(env)
                    except Exception as exc:  # noqa: BLE001 - control message delivery failure retried on next loop
                        logger.warning(
                            "RTC config delivery failed: profile=%s error_type=%s",
                            profile_id,
                            type(exc).__name__,
                        )

            # 2. Check if ICE restart should be triggered
            if state.in_progress_generation is not None:
                if (
                    self.rtc_service.should_trigger_restart(state.current_generation, t)
                    and t >= state.next_retry_at
                    and not state.active_restarts
                ):
                    await self._start_restart_round(state, t)

                # Check if old generation has expired while restart is still uncommitted
                if self.rtc_service.is_expired(state.current_generation, t):
                    logger.error(
                        "TURN credential gen %d for profile %s expired before rotation",
                        state.current_generation.generation,
                        profile_id,
                    )

    async def _start_restart_round(
        self, state: ProfileRotationState, now: float
    ) -> None:
        active_conns = self._get_active_connections(state.profile_id)
        unmigrated = [
            cid for cid in active_conns if cid not in state.migrated_connections
        ]

        if not unmigrated:
            # All connections already migrated (or 0 active) -> commit generation
            committed_gen = state.in_progress_generation
            state.current_generation = committed_gen  # type: ignore[assignment]
            state.in_progress_generation = None
            state.migrated_connections.clear()
            state.retry_count = 0
            state.next_retry_at = 0.0
            logger.info(
                "Generation %d officially committed for profile %s",
                committed_gen.generation,  # type: ignore[union-attr]
                state.profile_id,
            )
            return

        agent = self._get_agent_info(state.profile_id)
        if agent is None:
            # Agent offline, backoff
            self._schedule_backoff(state, now, reason="Agent not available")
            return

        # Launch restart for unmigrated connections concurrently
        for conn_id in unmigrated:
            if conn_id not in state.active_restarts:
                task = asyncio.create_task(
                    self._restart_connection(state, conn_id, agent)
                )
                state.active_restarts[conn_id] = task

    async def _restart_connection(
        self, state: ProfileRotationState, conn_id: str, agent: Any
    ) -> None:
        target_gen = state.in_progress_generation
        if target_gen is None:
            state.active_restarts.pop(conn_id, None)
            return

        loop = asyncio.get_running_loop()
        offer_fut: asyncio.Future[ProtocolEnvelope] = loop.create_future()
        answer_fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        commit_fut: asyncio.Future[ProtocolEnvelope] = loop.create_future()
        generation = target_gen.generation
        profile_id = state.profile_id
        self._pending_offers[conn_id] = PendingHandshake(
            offer_fut, generation, profile_id
        )
        self._pending_answers[conn_id] = PendingHandshake(
            answer_fut, generation, profile_id
        )
        self._pending_commits[conn_id] = PendingHandshake(
            commit_fut, generation, profile_id
        )

        try:
            # 1. Send ICE_RESTART to Agent
            force_relay = self.rtc_service.webrtc_mode == "relay-only"
            env = GatewayControlEnvelope(
                version="v2",
                action=AgentAction.ICE_RESTART,
                profile_id=state.profile_id,
                runtime_instance_id=agent.instance_id,
                agent_session_id=agent.agent_session_id,
                conn_id=conn_id,
                payload={
                    "generation": target_gen.generation,
                    "ice_servers": target_gen.build_stream_ice_servers(
                        agent.turn_host, agent.turn_port
                    ),
                    "force_relay": force_relay,
                },
            )
            await self._send_agent_control(env)

            # 2. Wait for Agent ICE_RESTART_OFFER (10s timeout)
            offer_env = await asyncio.wait_for(offer_fut, timeout=10.0)
            offer_payload = offer_env.payload
            offer_sdp = offer_payload.get("sdp")
            offer_type = offer_payload.get("type", "offer")

            # 3. Send ice_restart control frame to Viewer
            viewer_frame = {
                "cbrowser": "ice_restart",
                "generation": target_gen.generation,
                "rtc_config": target_gen.client_rtc_config,
                "offer": {"type": offer_type, "sdp": offer_sdp},
            }
            await self._send_viewer_control(conn_id, viewer_frame)

            # 4. Wait for Viewer ice_restart_answer (10s timeout)
            answer_frame = await asyncio.wait_for(answer_fut, timeout=10.0)
            ans_sdp_obj = answer_frame.get("sdp", {})
            if isinstance(ans_sdp_obj, dict):
                ans_sdp = ans_sdp_obj.get("sdp", "")
            else:
                ans_sdp = str(ans_sdp_obj)

            # 5. Send ICE_RESTART_ANSWER to Agent
            answer_env = GatewayControlEnvelope(
                version="v2",
                action=AgentAction.ICE_RESTART_ANSWER,
                profile_id=state.profile_id,
                runtime_instance_id=agent.instance_id,
                agent_session_id=agent.agent_session_id,
                conn_id=conn_id,
                payload={
                    "generation": target_gen.generation,
                    "type": "answer",
                    "sdp": ans_sdp,
                },
            )
            await self._send_agent_control(answer_env)

            # 6. A relayed answer is not a verified restart: wait until the Agent
            # reports that the new ICE generation took over and the old one retired.
            commit_env = await asyncio.wait_for(commit_fut, timeout=COMMIT_TIMEOUT_SEC)
            if commit_env.payload.get("generation") != target_gen.generation:
                raise RuntimeError("Agent committed a different generation")

            state.migrated_connections.add(conn_id)
            logger.info(
                "Connection %s migrated to generation %d",
                conn_id,
                target_gen.generation,
            )

        except Exception as e:  # noqa: BLE001 - single connection failure backs off without crashing rotation
            logger.warning(
                "ICE restart failed on connection %s: %s", conn_id, type(e).__name__
            )
            now = time.time()
            self._schedule_backoff(
                state, now, reason=f"Connection {conn_id} failed: {type(e).__name__}"
            )
        finally:
            self._pending_offers.pop(conn_id, None)
            self._pending_answers.pop(conn_id, None)
            self._pending_commits.pop(conn_id, None)
            state.active_restarts.pop(conn_id, None)

            # Check if all migrated now
            active = self._get_active_connections(state.profile_id)
            if (
                all(c in state.migrated_connections for c in active)
                and state.in_progress_generation is not None
            ):
                    committed_gen = state.in_progress_generation
                    state.current_generation = committed_gen
                    state.in_progress_generation = None
                    state.migrated_connections.clear()
                    state.retry_count = 0
                    state.next_retry_at = 0.0
                    logger.info(
                        "Generation %d officially committed for profile %s",
                        committed_gen.generation,
                        state.profile_id,
                    )

    def _schedule_backoff(
        self, state: ProfileRotationState, now: float, reason: str
    ) -> None:
        delay = min(60.0, 2.0 ** (state.retry_count + 1))
        state.next_retry_at = now + delay
        state.retry_count += 1
        logger.warning(
            "Scheduled ICE restart backoff for profile %s in %.1fs (retry %d): %s",
            state.profile_id,
            delay,
            state.retry_count,
            reason,
        )
