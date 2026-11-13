"""t031 control service: transitions, generation, reclaim, identity."""

from __future__ import annotations

import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.control_service import (
    ControlConflictError,
    ControlNotFoundError,
    ProfileControlService,
)


async def _context(tmp_path):
    db = tmp_path / "control.db"
    run_database_migrations(db)
    engine, maker = create_engine_and_maker(db)
    repo = ProfileRepository(maker)
    profile = await repo.create_profile(
        ProfileConfig(name="Control", fingerprint_seed=1)
    )
    return engine, maker, profile.id


@pytest.mark.asyncio
async def test_default_state_is_user_generation_zero(tmp_path):
    engine, maker, pid = await _context(tmp_path)
    try:
        svc = ProfileControlService(maker)
        state = await svc.get_state(pid)
        assert state.owner == "user"
        assert state.generation == 0
        assert state.agent_reclaim_allowed is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unknown_profile_raises_not_found(tmp_path):
    engine, maker, _pid = await _context(tmp_path)
    try:
        svc = ProfileControlService(maker)
        with pytest.raises(ControlNotFoundError):
            await svc.get_state("no-such-profile")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_claim_handoff_restore_cycle(tmp_path):
    engine, maker, pid = await _context(tmp_path)
    try:
        svc = ProfileControlService(maker)
        state, _ = await svc.claim(pid, "tok-1", "exec-1")
        assert state.owner == "agent" and state.generation == 1
        # Renewing claim by the same identity is a no-op (no bump).
        state, _ = await svc.claim(pid, "tok-1", "exec-1")
        assert state.generation == 1
        # Human-input takeover: generation advances, reclaim blocked.
        state, close = await svc.takeover(pid, conn_id="c1", input_kind="key")
        assert state.owner == "user" and state.generation == 2
        assert state.handoff_reason == "human_input"
        assert state.agent_reclaim_allowed is False
        assert close is True
        # Re-claim while blocked is a conflict (both paths).
        with pytest.raises(ControlConflictError) as exc:
            await svc.claim(pid, "tok-1", "exec-1")
        assert exc.value.code == "control_reclaim_blocked"
        # Explicit restore returns control to the recorded agent.
        state, _ = await svc.restore(pid)
        assert state.owner == "agent" and state.generation == 3
        assert state.agent_reclaim_allowed is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_second_agent_cannot_claim(tmp_path):
    engine, maker, pid = await _context(tmp_path)
    try:
        svc = ProfileControlService(maker)
        await svc.claim(pid, "tok-1", "exec-1")
        # Different token AND session: second agent.
        with pytest.raises(ControlConflictError) as exc:
            await svc.claim(pid, "tok-2", "exec-2")
        assert exc.value.code == "control_second_agent"
        # Same token but a different explicit session: still second agent.
        with pytest.raises(ControlConflictError):
            await svc.claim(pid, "tok-1", "exec-2")
        # Bare handshake (token only) renews instead of conflicting.
        state, _ = await svc.claim(pid, "tok-1", None)
        assert state.owner == "agent" and state.generation == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_handoff_is_idempotent_and_fail_open(tmp_path):
    engine, maker, pid = await _context(tmp_path)
    try:
        svc = ProfileControlService(maker)
        # Already user: no generation bump, no close request.
        state, close = await svc.handoff(pid, "cli_handoff")
        assert state.generation == 0 and close is False
        await svc.claim(pid, "tok-1", "exec-1")
        # Handoff from a non-controlling identity still moves to user
        # (transitions toward safety never conflict).
        state, close = await svc.handoff(pid, "permission")
        assert state.owner == "user" and close is True
        assert state.agent_reclaim_allowed is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_agent_finish_leaves_reclaim_open(tmp_path):
    engine, maker, pid = await _context(tmp_path)
    try:
        svc = ProfileControlService(maker)
        await svc.claim(pid, "tok-1", "exec-1")
        state, _ = await svc.handoff(pid, "agent_finish")
        assert state.owner == "user"
        assert state.agent_reclaim_allowed is True
        # A fresh session may claim again without a restore.
        state, _ = await svc.claim(pid, "tok-1", "exec-9")
        assert state.owner == "agent"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_restore_without_identity_conflicts(tmp_path):
    engine, maker, pid = await _context(tmp_path)
    try:
        svc = ProfileControlService(maker)
        with pytest.raises(ControlConflictError) as exc:
            await svc.restore(pid)
        assert exc.value.code == "control_nothing_to_restore"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_runtime_restart_resets_agent_control(tmp_path):
    engine, maker, pid = await _context(tmp_path)
    try:
        svc = ProfileControlService(maker)
        await svc.claim(pid, "tok-1", "exec-1")
        state, close = await svc.note_runtime_started(pid, "profile_restart")
        assert state.owner == "user" and close is True
        assert state.handoff_reason == "profile_restart"
        # Fresh start: reclaim stays open for the next session.
        assert state.agent_reclaim_allowed is True
        # Already user: restart is a no-op (no generation bump).
        state, close = await svc.note_runtime_started(pid, "crash")
        assert state.generation == 2 and close is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_claim_requires_identity(tmp_path):
    engine, maker, pid = await _context(tmp_path)
    try:
        svc = ProfileControlService(maker)
        with pytest.raises(ControlConflictError) as exc:
            await svc.claim(pid, None, None)
        assert exc.value.code == "control_no_identity"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pending_supervisor_close_retry(tmp_path):
    engine, maker, pid = await _context(tmp_path)
    try:
        calls: list[tuple[str, int]] = []

        async def failing_close(profile_id: str, generation: int) -> bool:
            calls.append((profile_id, generation))
            return False

        svc = ProfileControlService(
            maker, close_supervisor_tunnels=failing_close
        )
        await svc.claim(pid, "tok-1", "exec-1")
        state, _ = await svc.handoff(pid, "human_input")
        assert state.pending_supervisor_close is True
        assert calls == [(pid, 2)]
        # Retry still failing keeps the flag.
        assert await svc.retry_pending_supervisor_close(pid) is False
        state = await svc.get_state(pid)
        assert state.pending_supervisor_close is True

        async def ok_close(profile_id: str, generation: int) -> bool:
            return True

        svc._close_supervisor_tunnels = ok_close
        assert await svc.retry_pending_supervisor_close(pid) is True
        state = await svc.get_state(pid)
        assert state.pending_supervisor_close is False
        # Nothing pending anymore.
        assert await svc.retry_pending_supervisor_close(pid) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_handoff_returns_settled_pending_flag(tmp_path):
    """t031_code_f004: a handoff whose Supervisor close succeeds
    returns pending_supervisor_close False, not the pre-close True."""
    import asyncio

    engine, maker, pid = await _context(tmp_path)
    try:
        async def ok_close(profile_id: str, generation: int) -> bool:
            return True

        svc = ProfileControlService(
            maker, close_supervisor_tunnels=ok_close
        )
        await svc.claim(pid, "tok-1", "exec-1")
        state, closed = await svc.handoff(pid, "human_input")
        assert closed is True
        assert state.pending_supervisor_close is False
        assert (await svc.get_state(pid)).pending_supervisor_close is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_claims_serialize_to_conflict(tmp_path):
    """t031_code_f008: concurrent claims for one profile serialize:
    exactly one wins and every loser is a 409-style conflict, never a
    raw DB error."""
    import asyncio

    engine, maker, pid = await _context(tmp_path)
    try:
        svc = ProfileControlService(maker)

        async def attempt(i: int):
            return await svc.claim(pid, f"tok-{i}", f"exec-{i}")

        results = await asyncio.gather(
            *(attempt(i) for i in range(8)), return_exceptions=True
        )
        winners = [r for r in results if not isinstance(r, Exception)]
        losers = [r for r in results if isinstance(r, Exception)]
        assert len(winners) == 1
        assert winners[0][0].owner == "agent"
        assert len(losers) == 7
        assert all(isinstance(e, ControlConflictError) for e in losers)
        assert all(e.code == "control_second_agent" for e in losers)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_handoff_for_identity_moves_only_that_token(tmp_path):
    """t031_code_f002: revoke-driven handoff by token identity."""
    engine, maker, pid = await _context(tmp_path)
    try:
        repo = ProfileRepository(maker)
        pid2 = (
            await repo.create_profile(
                ProfileConfig(name="Second", fingerprint_seed=2)
            )
        ).id
        pid3 = (
            await repo.create_profile(
                ProfileConfig(name="Third", fingerprint_seed=3)
            )
        ).id
        svc = ProfileControlService(maker)
        await svc.claim(pid, "tok-1", "exec-1")
        await svc.claim(pid2, "tok-1", "exec-2")
        await svc.claim(pid3, "tok-2", "exec-3")
        handed = await svc.handoff_for_identity("tok-1", "identity_invalid")
        assert sorted(handed) == sorted([pid, pid2])
        for handed_pid in (pid, pid2):
            state = await svc.get_state(handed_pid)
            assert state.owner == "user"
            assert state.handoff_reason == "identity_invalid"
            assert state.agent_reclaim_allowed is False
        # The other token's profile is untouched.
        assert (await svc.get_state(pid3)).owner == "agent"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_handoff_for_identity_isolates_per_profile_failures(
    tmp_path, monkeypatch
):
    """t031_code_f009: one profile's handoff failure must not abort the
    batch for the other profiles held by the same token."""
    engine, maker, pid = await _context(tmp_path)
    try:
        repo = ProfileRepository(maker)
        pid2 = (
            await repo.create_profile(
                ProfileConfig(name="Second", fingerprint_seed=2)
            )
        ).id
        svc = ProfileControlService(maker)
        await svc.claim(pid, "tok-1", "exec-1")
        await svc.claim(pid2, "tok-1", "exec-2")
        real_handoff = svc.handoff

        async def failing_once(profile_id, *args, **kwargs):
            if profile_id == pid:
                raise RuntimeError("simulated DB failure")
            return await real_handoff(profile_id, *args, **kwargs)

        monkeypatch.setattr(svc, "handoff", failing_once)
        handed = await svc.handoff_for_identity("tok-1", "identity_invalid")
        assert handed == [pid2]
        assert (await svc.get_state(pid2)).owner == "user"
        # The failed profile keeps its control (revoke retry/reconcile
        # surface reports it; the batch still moved the other profile).
        assert (await svc.get_state(pid)).owner == "agent"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_renew_upgrade_publishes_only_after_commit(tmp_path, monkeypatch):
    """t056 A2 / AC-002: a renew-upgrade publishes after the transaction
    commits.  When the commit fails, no SSE event is emitted and the
    session upgrade is not persisted."""
    from contextlib import asynccontextmanager

    from cbrowser.services import control_service as control_service_module

    engine, maker, pid = await _context(tmp_path)
    published: list[str] = []

    async def record_publish(profile_id: str) -> None:
        published.append(profile_id)

    try:
        svc = ProfileControlService(
            maker, publish_profile_change=record_publish
        )
        # Instance-only claim: publish once.
        state, _ = await svc.claim(pid, "tok-1", None)
        assert state.agent_session_id is None
        assert published == [pid]
        # Renew-upgrade to session scope: publish again, after commit.
        state, _ = await svc.claim(pid, "tok-1", "exec-1")
        assert state.agent_session_id == "exec-1"
        assert published == [pid, pid]

        # A second profile whose commit fails: the upgrade must not publish.
        profile2 = await ProfileRepository(maker).create_profile(
            ProfileConfig(name="Control2", fingerprint_seed=2)
        )
        svc2 = ProfileControlService(
            maker, publish_profile_change=record_publish
        )
        await svc2.claim(profile2.id, "tok-2", None)
        assert published == [pid, pid, profile2.id]

        real_write_transaction = control_service_module.write_transaction

        @asynccontextmanager
        async def failing_write_transaction(session):
            async with real_write_transaction(session):
                yield session
                raise RuntimeError("simulated commit failure")

        # The wrapper above yields inside the real transaction, then
        # raises before the real commit runs: the outer context manager
        # rolls back, so the upgrade never persists.
        monkeypatch.setattr(
            control_service_module,
            "write_transaction",
            failing_write_transaction,
        )
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            await svc2.claim(profile2.id, "tok-2", "exec-2")
        assert published == [pid, pid, profile2.id]
        after = await svc2.get_state(profile2.id)
        assert after.agent_session_id is None
    finally:
        await engine.dispose()
