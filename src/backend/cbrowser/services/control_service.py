"""Human-priority control state service (t031, ADR 019).

The API is the sole business-DB writer for control state: this service
owns every read and write of ``profile_controls``. Supervisor, Gateway,
and Agent processes never write the table; they enforce the state the
API persists (tunnel registries, generation fences, close cascades).

Safety direction: transitions *toward* ``user`` are fail-open (any
caller may move a profile back to the safe state); transitions *toward*
``agent`` are fail-closed (identity match, reclaim flag, and explicit
restore are all required).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from cbrowser.adapters.database.models import ProfileControlModel, ProfileModel
from cbrowser.adapters.database.session import write_transaction
from cbrowser.domain.models import (
    ControlHandoffReason,
    ProfileControlStateData,
    utc_now_iso,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("cbrowser.services.control")

# Reasons that return a profile to the safe state *without* requiring an
# explicit human restore before the next agent claim. A clean agent
# finish and a runtime restart/crash are fresh starts, not takeovers:
# the agent that held control is gone, so the next session may claim.
RECLAIM_ALLOWED_REASONS: frozenset[str] = frozenset(
    {
        "agent_finish",
        "supervisor_restart",
        "profile_restart",
        "crash",
    }
)


class ControlNotFoundError(Exception):
    def __init__(self, profile_id: str):
        super().__init__(f"Profile {profile_id} not found")
        self.profile_id = profile_id


class ControlConflictError(Exception):
    """A transition toward agent was refused (second agent / reclaim)."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


def _row_to_data(row: ProfileControlModel) -> ProfileControlStateData:
    return ProfileControlStateData(
        profile_id=row.profile_id,
        owner=row.owner,  # type: ignore[arg-type]
        generation=row.generation,
        agent_instance_id=row.agent_instance_id,
        agent_session_id=row.agent_session_id,
        handoff_reason=row.handoff_reason,
        handoff_detail=row.handoff_detail,
        agent_reclaim_allowed=row.agent_reclaim_allowed,
        pending_supervisor_close=row.pending_supervisor_close,
        updated_at=row.updated_at,
    )


def _default_state(profile_id: str) -> ProfileControlStateData:
    return ProfileControlStateData(
        profile_id=profile_id,
        owner="user",
        generation=0,
        agent_instance_id=None,
        agent_session_id=None,
        handoff_reason=None,
        handoff_detail=None,
        agent_reclaim_allowed=True,
        pending_supervisor_close=False,
        updated_at=utc_now_iso(),
    )


def _identity_matches(
    row: ProfileControlModel,
    agent_instance_id: str | None,
    agent_session_id: str | None,
) -> bool:
    """True when the caller is the currently controlling agent.

    Both dimensions must agree when both sides carry them: a session
    mismatch is a conflict even under the same token (a second CLI
    process claiming explicitly), and an instance mismatch is a conflict
    even with the same session id. A missing dimension on either side
    defers to the other dimension, so a bare tunnel handshake (token
    identity only) renews a session-scoped claim instead of conflicting.
    At least one dimension must positively agree.
    """
    session_ok = (
        agent_session_id is None
        or row.agent_session_id is None
        or row.agent_session_id == agent_session_id
    )
    instance_ok = (
        agent_instance_id is None
        or row.agent_instance_id is None
        or row.agent_instance_id == agent_instance_id
    )
    identified = (
        agent_session_id is not None
        and row.agent_session_id == agent_session_id
    ) or (
        agent_instance_id is not None
        and row.agent_instance_id == agent_instance_id
    )
    return session_ok and instance_ok and identified


class ProfileControlService:
    def __init__(
        self,
        session_maker,
        *,
        publish_profile_change: (
            Callable[[str], Awaitable[None]] | None
        ) = None,
        close_supervisor_tunnels: (
            Callable[[str, int], Awaitable[bool]] | None
        ) = None,
        close_api_tunnels: (
            Callable[[str, int], Awaitable[bool]] | None
        ) = None,
    ):
        self._session_maker = session_maker
        self._publish_profile_change = publish_profile_change
        self._close_supervisor_tunnels = close_supervisor_tunnels
        self._close_api_tunnels = close_api_tunnels
        # Per-profile serialization (t031_code_f008): concurrent claims
        # for one profile must serialize into a 409 conflict, not a raw
        # DB write error. Locks are created on first use; dict
        # get-or-create runs synchronously between awaits, so no two
        # tasks create different locks for the same profile.
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, profile_id: str) -> asyncio.Lock:
        lock = self._locks.get(profile_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[profile_id] = lock
        return lock

    async def _publish(self, profile_id: str) -> None:
        if self._publish_profile_change is None:
            return
        try:
            await self._publish_profile_change(profile_id)
        except Exception:  # noqa: BLE001 - SSE publish must never fail control
            logger.warning(
                "Control SSE publish failed: profile=%s", profile_id
            )

    async def _close_supervisor(
        self, profile_id: str, generation: int
    ) -> bool:
        if self._close_supervisor_tunnels is None:
            return False
        try:
            return await self._close_supervisor_tunnels(profile_id, generation)
        except Exception:  # noqa: BLE001 - close failure degrades to pending
            logger.warning(
                "Supervisor tunnel close failed: profile=%s", profile_id
            )
            return False

    async def get_state(self, profile_id: str) -> ProfileControlStateData:
        """Current state; a never-persisted profile reports the default.

        Raises ControlNotFoundError for an unknown profile id.
        """
        async with self._session_maker() as session:
            profile = await session.get(ProfileModel, profile_id)
            if profile is None:
                raise ControlNotFoundError(profile_id)
            row = await session.get(ProfileControlModel, profile_id)
            if row is None:
                return _default_state(profile_id)
            return _row_to_data(row)

    async def _get_or_create_row(
        self, session: AsyncSession, profile_id: str
    ) -> ProfileControlModel:
        profile = await session.get(ProfileModel, profile_id)
        if profile is None:
            raise ControlNotFoundError(profile_id)
        row = await session.get(ProfileControlModel, profile_id)
        if row is None:
            row = ProfileControlModel(
                profile_id=profile_id,
                owner="user",
                generation=0,
                agent_reclaim_allowed=True,
                pending_supervisor_close=False,
                updated_at=utc_now_iso(),
            )
            session.add(row)
            await session.flush()
        return row

    async def claim(
        self,
        profile_id: str,
        agent_instance_id: str | None,
        agent_session_id: str | None,
    ) -> tuple[ProfileControlStateData, bool]:
        """Move control to the calling agent (serialized per profile)."""
        async with self._lock_for(profile_id):
            return await self._claim(
                profile_id, agent_instance_id, agent_session_id
            )

    async def _claim(
        self,
        profile_id: str,
        agent_instance_id: str | None,
        agent_session_id: str | None,
    ) -> tuple[ProfileControlStateData, bool]:
        """Move control to the calling agent.

        Returns ``(state, close_requested)``; claims never close tunnels.
        A renewing claim by the controlling agent is a no-op (no
        generation bump). A claim while another agent holds control, or
        while reclaim is blocked after a takeover, is a conflict.
        """
        async with self._session_maker() as session, write_transaction(session):
            row = await self._get_or_create_row(session, profile_id)
            if row.owner == "agent":
                if not _identity_matches(
                    row, agent_instance_id, agent_session_id
                ):
                    raise ControlConflictError(
                        "Another agent holds control for this profile",
                        code="control_second_agent",
                    )
                # Renew: upgrade a missing dimension (a bare handshake
                # renews a session-scoped claim without downgrading it;
                # an explicit claim upgrades an instance-only claim to
                # session scope).
                upgraded = (
                    agent_session_id is not None
                    and row.agent_session_id is None
                )
                if upgraded:
                    row.agent_session_id = agent_session_id
                    row.updated_at = utc_now_iso()
                data = _row_to_data(row)
                if upgraded:
                    await self._publish(profile_id)
                return data, False
            if agent_instance_id is None and agent_session_id is None:
                raise ControlConflictError(
                    "A claim requires an agent identity",
                    code="control_no_identity",
                )
            if not row.agent_reclaim_allowed:
                raise ControlConflictError(
                    "Control was taken over; an explicit human restore "
                    "is required before an agent may claim again",
                    code="control_reclaim_blocked",
                )
            row.owner = "agent"
            row.generation += 1
            row.agent_instance_id = agent_instance_id
            row.agent_session_id = agent_session_id
            row.handoff_reason = None
            row.handoff_detail = None
            row.updated_at = utc_now_iso()
            data = _row_to_data(row)
        await self._publish(profile_id)
        return data, False

    async def handoff(
        self,
        profile_id: str,
        reason: ControlHandoffReason,
        detail: str | None = None,
        agent_instance_id: str | None = None,
        agent_session_id: str | None = None,
    ) -> tuple[ProfileControlStateData, bool]:
        """Move control back to the user (serialized per profile)."""
        async with self._lock_for(profile_id):
            return await self._handoff(
                profile_id,
                reason,
                detail=detail,
                agent_instance_id=agent_instance_id,
                agent_session_id=agent_session_id,
            )

    async def _handoff(
        self,
        profile_id: str,
        reason: ControlHandoffReason,
        detail: str | None = None,
        agent_instance_id: str | None = None,
        agent_session_id: str | None = None,
    ) -> tuple[ProfileControlStateData, bool]:
        """Move control back to the user (fail-open toward safety).

        Already-user is an idempotent no-op (no generation bump, no
        tunnel close). Otherwise the generation advances, tunnels must
        close, and ``agent_reclaim_allowed`` follows the reason table:
        only a clean finish or a runtime restart/crash leaves reclaim
        open; every human-driven handoff requires explicit restore.
        """
        async with self._session_maker() as session, write_transaction(session):
            row = await self._get_or_create_row(session, profile_id)
            if row.owner == "user":
                return _row_to_data(row), False
            row.owner = "user"
            row.generation += 1
            row.handoff_reason = reason
            row.handoff_detail = detail
            row.agent_reclaim_allowed = reason in RECLAIM_ALLOWED_REASONS
            row.pending_supervisor_close = True
            row.updated_at = utc_now_iso()
            data = _row_to_data(row)
        close_ok = await self._close_supervisor(profile_id, data.generation)
        if not close_ok:
            # Supervisor unreachable: the API-side state already commits
            # (the API is authoritative); the pending flag lets the
            # coordinator retry the close on its next Supervisor contact.
            await self._set_pending(profile_id, True)
        else:
            await self._set_pending(profile_id, False)
        # API-layer tunnels close before the SSE publish, so observers
        # never see owner=user while a stale tunnel is still open.
        if self._close_api_tunnels is not None:
            try:
                await self._close_api_tunnels(profile_id, data.generation)
            except Exception:  # noqa: BLE001 - close is best-effort
                logger.warning(
                    "API tunnel close failed: profile=%s", profile_id
                )
        await self._publish(profile_id)
        # t031_code_f004: the response must reflect the settled state,
        # not the pre-close snapshot (pending flag + updated_at changed
        # in the second commit). Best-effort: a profile deleted mid
        # handoff keeps the pre-close snapshot rather than failing.
        try:
            data = await self.get_state(profile_id)
        except ControlNotFoundError:
            pass
        return data, True

    async def takeover(
        self,
        profile_id: str,
        *,
        conn_id: str | None = None,
        input_kind: str | None = None,
    ) -> tuple[ProfileControlStateData, bool]:
        """Human-input takeover: same as handoff(reason=human_input)."""
        detail = None
        if conn_id or input_kind:
            detail = ",".join(
                part for part in (conn_id, input_kind) if part
            )[:256]
        return await self.handoff(
            profile_id, "human_input", detail=detail
        )

    async def restore(
        self, profile_id: str
    ) -> tuple[ProfileControlStateData, bool]:
        """Explicit human restore (serialized per profile)."""
        async with self._lock_for(profile_id):
            return await self._restore(profile_id)

    async def _restore(
        self, profile_id: str
    ) -> tuple[ProfileControlStateData, bool]:
        """Explicit human restore: return control to the recorded agent.

        Already-agent is an idempotent no-op. A profile that never had
        an agent identity recorded cannot be restored (conflict).
        """
        async with self._session_maker() as session, write_transaction(session):
            row = await self._get_or_create_row(session, profile_id)
            if row.owner == "agent":
                return _row_to_data(row), False
            if not row.agent_instance_id and not row.agent_session_id:
                raise ControlConflictError(
                    "No recorded agent identity to restore",
                    code="control_nothing_to_restore",
                )
            row.owner = "agent"
            row.generation += 1
            row.handoff_reason = None
            row.handoff_detail = None
            row.agent_reclaim_allowed = True
            row.pending_supervisor_close = False
            row.updated_at = utc_now_iso()
            data = _row_to_data(row)
        await self._publish(profile_id)
        return data, False

    async def note_runtime_started(
        self, profile_id: str, reason: ControlHandoffReason
    ) -> tuple[ProfileControlStateData, bool]:
        """Reset agent control on runtime restart/crash (AC-001).

        Already-user is a no-op: the old runtime's tunnels died with it.
        """
        return await self.handoff(profile_id, reason)

    async def handoff_for_identity(
        self, agent_instance_id: str, reason: ControlHandoffReason
    ) -> list[str]:
        """Hand off every profile controlled by this agent identity.

        t031_code_f002: revoking an automation token must move live
        control back to the user through the normal tunnel-close
        cascade, not just refuse future connections. Profiles already
        back on the user (raced handoff) are no-ops. A profile deleted
        between the scan and the handoff is skipped.
        """
        async with self._session_maker() as session:
            rows = (
                await session.execute(
                    select(ProfileControlModel).where(
                        ProfileControlModel.owner == "agent",
                        ProfileControlModel.agent_instance_id
                        == agent_instance_id,
                    )
                )
            ).scalars().all()
            profile_ids = [row.profile_id for row in rows]
        handed: list[str] = []
        for profile_id in profile_ids:
            try:
                await self.handoff(profile_id, reason)
            except ControlNotFoundError:
                continue
            except Exception:  # noqa: BLE001 - one profile's failure
                # must not abort the batch (t031_code_f009): the token
                # is revoked regardless, so every other profile it held
                # still moves to the user; the failure is logged.
                logger.warning(
                    "Handoff after token revoke failed: profile=%s",
                    profile_id,
                )
                continue
            handed.append(profile_id)
        return handed

    async def _set_pending(self, profile_id: str, value: bool) -> None:
        async with self._session_maker() as session, write_transaction(session):
            row = await session.get(ProfileControlModel, profile_id)
            if row is None:
                return
            if row.pending_supervisor_close == value:
                return
            row.pending_supervisor_close = value
            row.updated_at = utc_now_iso()

    async def retry_pending_supervisor_close(
        self, profile_id: str
    ) -> bool | None:
        """Re-issue a pending Supervisor tunnel close (serialized)."""
        async with self._lock_for(profile_id):
            return await self._retry_pending_supervisor_close(profile_id)

    async def _retry_pending_supervisor_close(
        self, profile_id: str
    ) -> bool | None:
        """Re-issue a pending Supervisor tunnel close, if one is pending.

        Returns True when a pending close was confirmed, False when it
        is still pending, and None when nothing was pending.
        """
        async with self._session_maker() as session:
            row = await session.get(ProfileControlModel, profile_id)
            if row is None or not row.pending_supervisor_close:
                return None
            generation = row.generation
        close_ok = await self._close_supervisor(profile_id, generation)
        await self._set_pending(profile_id, not close_ok)
        if close_ok:
            await self._publish(profile_id)
        return close_ok
