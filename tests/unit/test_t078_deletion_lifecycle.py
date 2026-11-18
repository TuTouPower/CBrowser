"""t078: profile deletion lifecycle (stop-then-delete state machine).

AC-003 stopping stage converges before any data is touched and a stop
failure keeps the profile fully intact; AC-004 repeat requests join the
same durable intent and a new instance bound after the stop stage
fences the cleaning stage; AC-005 batch targets succeed/fail
independently; AC-006 artifact cleanup outcomes are recorded on the
intent, never silently swallowed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio

from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.profile_service import (
    ProfileDeletionFailedError,
    ProfileService,
)


@pytest_asyncio.fixture
async def repo(db_context):
    _engine, session_maker = db_context
    return ProfileRepository(session_maker)


@pytest_asyncio.fixture
async def service(repo, tmp_path: Path):
    svc = ProfileService(repo, data_root=tmp_path / "data")
    svc.deletion_poll_interval_seconds = 0.01
    svc.deletion_stop_timeout_seconds = 5.0
    return svc


async def _make_profile(repo, name: str):
    return await repo.create_profile(ProfileConfig(name=name))


async def _make_running(repo, name: str, instance: str = "inst-1"):
    profile = await _make_profile(repo, name)
    await repo.set_desired_state(profile.id, "running")
    await repo.bind_runtime_instance(profile.id, instance)
    await repo.report_observed_state(profile.id, instance, "running")
    return profile


def _profile_dirs(service: ProfileService, profile_id: str) -> list[Path]:
    root = service._data_root
    assert root is not None
    dirs = []
    for sub in ("profiles", "runtime", "runtime-events"):
        target = root / sub / profile_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "marker.txt").write_text("x")
        dirs.append(target)
    return dirs


async def _supervisor_simulator(repo, profile_id: str, stop_event: asyncio.Event):
    """Converge desired=stopped into observed stopped + unbound, the
    way the real Supervisor/coordinator pair does."""
    while not stop_event.is_set():
        runtime = await repo.get_runtime(profile_id)
        if (
            runtime is not None
            and runtime.desired_state == "stopped"
            and runtime.runtime_instance_id is not None
        ):
            await repo.report_observed_state(
                profile_id, runtime.runtime_instance_id, "stopped"
            )
            return
        await asyncio.sleep(0.01)


async def test_stopped_profile_deletion_completes(service, repo):
    profile = await _make_profile(repo, "stopped-one")
    dirs = _profile_dirs(service, profile.id)

    _batch, operations = await service.request_deletions([profile.id])
    await service.await_pending_deletions()

    final = await service.get_deletion(operations[0].id)
    assert final is not None
    assert final.stage == "done"
    assert final.detail["steps"]["database"] == "ok"
    assert await repo.get_profile(profile.id) is None
    assert all(not d.exists() for d in dirs)


async def test_running_profile_is_stopped_then_deleted(service, repo):
    profile = await _make_running(repo, "running-one")
    stop_event = asyncio.Event()
    simulator = asyncio.create_task(
        _supervisor_simulator(repo, profile.id, stop_event)
    )
    try:
        _batch, operations = await service.request_deletions([profile.id])
        await service.await_pending_deletions()
    finally:
        stop_event.set()
        await simulator

    final = await service.get_deletion(operations[0].id)
    assert final is not None and final.stage == "done"
    assert final.detail["bound_instance_id"] == "inst-1"
    assert await repo.get_profile(profile.id) is None


async def test_stop_timeout_fails_and_keeps_everything(service, repo):
    service.deletion_stop_timeout_seconds = 0.2
    profile = await _make_running(repo, "never-stops")
    dirs = _profile_dirs(service, profile.id)

    _batch, operations = await service.request_deletions([profile.id])
    await service.await_pending_deletions()

    final = await service.get_deletion(operations[0].id)
    assert final is not None
    assert final.stage == "failed"
    assert final.failed_stage == "stopping"
    assert "stop_timeout" in (final.error or "")
    # Data untouched: profile, runtime binding and directories intact.
    assert await repo.get_profile(profile.id) is not None
    runtime = await repo.get_runtime(profile.id)
    assert runtime is not None and runtime.runtime_instance_id == "inst-1"
    assert all(d.exists() for d in dirs)

    # Retry after the supervisor catches up completes the same intent.
    stop_event = asyncio.Event()
    simulator = asyncio.create_task(
        _supervisor_simulator(repo, profile.id, stop_event)
    )
    try:
        retried = await service.retry_deletion(operations[0].id)
        assert retried.id == operations[0].id
        await service.await_pending_deletions()
    finally:
        stop_event.set()
        await simulator
    final = await service.get_deletion(operations[0].id)
    assert final is not None and final.stage == "done"
    assert await repo.get_profile(profile.id) is None


async def test_repeat_request_joins_same_intent(service, repo):
    profile = await _make_profile(repo, "dup-target")
    _b1, first = await service.request_deletions([profile.id])
    _b2, second = await service.request_deletions([profile.id])
    assert second[0].id == first[0].id
    await service.await_pending_deletions()
    final = await service.get_deletion(first[0].id)
    assert final is not None and final.stage == "done"
    assert await repo.get_profile(profile.id) is None


async def test_missing_profile_fails_at_accepted(service, repo):
    _batch, operations = await service.request_deletions(["no-such-id"])
    assert operations[0].stage == "failed"
    assert operations[0].failed_stage == "accepted"
    assert operations[0].error == "profile_not_found"


async def test_new_instance_bound_after_stop_fences_cleaning(service, repo):
    profile = await _make_profile(repo, "restarted")
    operation = await repo.create_deletion(
        batch_id="batch-x", profile_id=profile.id, profile_name=profile.config.name
    )
    # The stop stage stopped inst-old; a new instance was bound since.
    await repo.update_deletion(
        operation.id,
        stage="cleaning",
        failed_stage=None,
        error=None,
        detail={"bound_instance_id": "inst-old"},
    )
    await repo.bind_runtime_instance(profile.id, "inst-new")

    await service._drive_deletion(operation.id)

    final = await service.get_deletion(operation.id)
    assert final is not None
    assert final.stage == "failed"
    assert final.failed_stage == "cleaning"
    assert "instance_changed" in (final.error or "")
    assert await repo.get_profile(profile.id) is not None


async def test_artifact_failure_is_recorded_and_retryable(service, repo):
    profile = await _make_profile(repo, "artifact-victim")

    async def broken_cleaner(_profile_id: str) -> None:
        raise RuntimeError("store offline")

    service.set_artifact_cleaner(broken_cleaner)
    _batch, operations = await service.request_deletions([profile.id])
    await service.await_pending_deletions()

    final = await service.get_deletion(operations[0].id)
    assert final is not None
    assert final.stage == "failed"
    assert final.failed_stage == "cleaning"
    assert "artifact_cleanup_failed" in (final.error or "")
    assert final.detail["steps"]["artifacts"].startswith("error:")
    # Nothing else was cleaned: the profile row survives for the retry.
    assert await repo.get_profile(profile.id) is not None

    async def working_cleaner(_profile_id: str) -> None:
        return None

    service.set_artifact_cleaner(working_cleaner)
    await service.retry_deletion(operations[0].id)
    await service.await_pending_deletions()
    final = await service.get_deletion(operations[0].id)
    assert final is not None and final.stage == "done"
    assert final.detail["steps"]["artifacts"] == "ok"
    assert await repo.get_profile(profile.id) is None


async def test_resume_pending_deletions_after_restart(service, repo):
    profile = await _make_profile(repo, "crash-survivor")
    operation = await repo.create_deletion(
        batch_id="batch-crash",
        profile_id=profile.id,
        profile_name=profile.config.name,
    )
    await repo.update_deletion(
        operation.id,
        stage="stopping",
        failed_stage=None,
        error=None,
        detail={},
    )

    resumed = await service.resume_pending_deletions()
    assert resumed == 1
    await service.await_pending_deletions()
    final = await service.get_deletion(operation.id)
    assert final is not None and final.stage == "done"
    assert await repo.get_profile(profile.id) is None


async def test_batch_targets_are_independent(service, repo):
    service.deletion_stop_timeout_seconds = 0.2
    ok_profile = await _make_profile(repo, "batch-ok")
    stuck = await _make_running(repo, "batch-stuck", instance="inst-9")

    batch_id, operations = await service.request_deletions(
        [ok_profile.id, stuck.id]
    )
    await service.await_pending_deletions()

    by_profile = {
        op.profile_id: op for op in await service.list_deletion_batch(batch_id)
    }
    assert by_profile[ok_profile.id].stage == "done"
    assert by_profile[stuck.id].stage == "failed"
    assert by_profile[stuck.id].failed_stage == "stopping"
    assert await repo.get_profile(ok_profile.id) is None
    assert await repo.get_profile(stuck.id) is not None
    assert len(operations) == 2


async def test_sync_delete_profile_uses_same_lifecycle(service, repo):
    profile = await _make_running(repo, "sync-delete")
    stop_event = asyncio.Event()
    simulator = asyncio.create_task(
        _supervisor_simulator(repo, profile.id, stop_event)
    )
    try:
        assert await service.delete_profile(profile.id) is True
    finally:
        stop_event.set()
        await simulator
    assert await repo.get_profile(profile.id) is None


async def test_sync_delete_profile_reports_failed_stage(service, repo):
    service.deletion_stop_timeout_seconds = 0.2
    profile = await _make_running(repo, "sync-stuck", instance="inst-7")
    with pytest.raises(ProfileDeletionFailedError) as excinfo:
        await service.delete_profile(profile.id)
    assert excinfo.value.operation.failed_stage == "stopping"
    assert await repo.get_profile(profile.id) is not None


async def test_reconfirm_failed_intent_retries_under_new_batch(service, repo):
    """Review f001 regression: a failed intent that is confirmed again
    must appear in the NEW batch's query and be re-driven to done, not
    stranded under its original batch."""
    service.deletion_stop_timeout_seconds = 0.2
    profile = await _make_running(repo, "reconfirm-me")
    _b1, operations = await service.request_deletions([profile.id])
    await service.await_pending_deletions()
    failed = await service.get_deletion(operations[0].id)
    assert failed is not None and failed.stage == "failed"
    assert failed.failed_stage == "stopping"

    stop_event = asyncio.Event()
    simulator = asyncio.create_task(
        _supervisor_simulator(repo, profile.id, stop_event)
    )
    try:
        batch2, second = await service.request_deletions([profile.id])
        assert second[0].id == operations[0].id
        in_batch = await service.list_deletion_batch(batch2)
        assert [op.id for op in in_batch] == [operations[0].id]
        await service.await_pending_deletions()
    finally:
        stop_event.set()
        await simulator
    final = await service.get_deletion(operations[0].id)
    assert final is not None and final.stage == "done"
    assert await repo.get_profile(profile.id) is None


async def test_second_open_intent_violates_unique_index(repo):
    """Review f003: the database itself enforces one open intent per
    profile; a second create while one is open is rejected."""
    from sqlalchemy.exc import IntegrityError

    profile = await _make_profile(repo, "unique-target")
    await repo.create_deletion(
        batch_id="b1", profile_id=profile.id, profile_name="x"
    )
    with pytest.raises(IntegrityError):
        await repo.create_deletion(
            batch_id="b2", profile_id=profile.id, profile_name="x"
        )


async def test_concurrent_requests_create_single_open_intent(service, repo):
    """Review f003: concurrent duplicate submissions converge on one
    intent instead of creating two."""
    profile = await _make_profile(repo, "race-target")
    results = await asyncio.gather(
        service.request_deletions([profile.id]),
        service.request_deletions([profile.id]),
    )
    ids = {ops[0].id for _batch, ops in results}
    assert len(ids) == 1
    await service.await_pending_deletions()
    final = await service.get_deletion(ids.pop())
    assert final is not None and final.stage == "done"
    assert await repo.get_profile(profile.id) is None


async def test_concurrent_requests_converge_under_repeated_pressure(
    service, repo
):
    """t085 (p139): repeated concurrent duplicate submissions converge
    on one intent and finish it; no duplicate intent and no spurious
    ``profile_not_found`` failure.

    The single-shot test above only exercises one interleaving. The
    gate failures (final3, t084 merge gate) showed two intermittent
    modes under parallel load: two intents created for one profile,
    and the single converged intent ending ``failed`` with
    ``profile_not_found``. Ten rounds of 8-way concurrency with fresh
    profiles per round make the race window wide enough to catch
    both modes on unfixed code.
    """
    for round_no in range(10):
        profile = await _make_profile(repo, f"race-pressure-{round_no}")
        results = await asyncio.gather(
            *(
                service.request_deletions([profile.id])
                for _ in range(8)
            )
        )
        ids = {ops[0].id for _batch, ops in results}
        assert len(ids) == 1, f"round {round_no}: {len(ids)} intents"
        await service.await_pending_deletions()
        final = await service.get_deletion(ids.pop())
        assert final is not None, f"round {round_no}: intent vanished"
        assert final.stage == "done", (
            f"round {round_no}: stage={final.stage} "
            f"error={final.error}"
        )
        assert await repo.get_profile(profile.id) is None


async def test_late_duplicate_intent_completes_when_sibling_deleted_row(
    service, repo
):
    """t085 (p139 :350): a duplicate intent created after the first
    intent completed must not fail with ``profile_not_found`` — its
    machine finds the row gone because the sibling already deleted
    it, and the deletion it represents is complete, so it is done.

    Built directly (the per-profile lock now prevents the race from
    producing the duplicate in-process): first intent driven to done,
    then a second intent for the same profile, then drive the second.
    """
    profile = await _make_profile(repo, "sibling-victim")
    first = await repo.create_deletion(
        batch_id="batch-first",
        profile_id=profile.id,
        profile_name=profile.config.name,
    )
    await service._drive_deletion(first.id)
    done_first = await service.get_deletion(first.id)
    assert done_first is not None and done_first.stage == "done"
    assert await repo.get_profile(profile.id) is None

    late = await repo.create_deletion(
        batch_id="batch-late",
        profile_id=profile.id,
        profile_name=profile.config.name,
    )
    await service._drive_deletion(late.id)

    final = await service.get_deletion(late.id)
    assert final is not None and final.stage == "done"
    assert final.error is None
    assert final.detail["steps"]["database"] == "ok"


async def test_guard_still_fails_without_sibling_intent(service, repo):
    """t085: the accepted-stage guard keeps failing with
    ``profile_not_found`` when no sibling intent exists — the
    genuinely-missing receipt semantics (a profile that never
    existed, or whose row vanished with no other intent) is
    preserved; only the sibling-proven case completes as done.
    """
    profile = await _make_profile(repo, "vanished-alone")
    operation = await repo.create_deletion(
        batch_id="batch-alone",
        profile_id=profile.id,
        profile_name=profile.config.name,
    )
    assert await repo.delete_profile(profile.id)

    await service._drive_deletion(operation.id)

    final = await service.get_deletion(operation.id)
    assert final is not None and final.stage == "failed"
    assert final.failed_stage == "accepted"
    assert final.error == "profile_not_found"


async def test_integrity_retry_joins_winner_that_completed(
    service, repo, monkeypatch
):
    """t085: if the winning intent completes while the
    ``IntegrityError`` retry is polling for an open intent, the retry
    falls back to the finished intent instead of raising after 50
    empty polls.

    Simulated with a mocked ``create_deletion`` that — standing in
    for a concurrent submission — really creates the winner and marks
    it done before raising ``IntegrityError`` (the in-process
    per-profile lock makes the real interleaving unreachable; the
    fallback is the cross-process backstop).
    """
    from sqlalchemy.exc import IntegrityError

    profile = await _make_profile(repo, "retry-winner")
    orig_create = repo.create_deletion

    async def _create_then_conflict(*args, **kwargs):
        winner = await orig_create(*args, **kwargs)
        await repo.update_deletion(
            winner.id,
            stage="done",
            failed_stage=None,
            error=None,
            detail={},
        )
        raise IntegrityError("INSERT", None, Exception("unique"))

    monkeypatch.setattr(repo, "create_deletion", _create_then_conflict)

    _batch, operations = await service.request_deletions([profile.id])
    assert len(operations) == 1
    assert operations[0].stage == "done"
    winner = await repo.find_deletion_for_profile(profile.id)
    assert winner is not None
    assert operations[0].id == winner.id


async def test_resume_pending_deletions_from_cleaning(service, repo):
    """AC-004: an intent interrupted during cleaning is resumed by a
    fresh service instance and completes without redoing harm."""
    profile = await _make_profile(repo, "cleaning-survivor")
    dirs = _profile_dirs(service, profile.id)
    operation = await repo.create_deletion(
        batch_id="batch-crash2",
        profile_id=profile.id,
        profile_name=profile.config.name,
    )
    await repo.update_deletion(
        operation.id,
        stage="cleaning",
        failed_stage=None,
        error=None,
        detail={},
    )

    resumed = await service.resume_pending_deletions()
    assert resumed == 1
    await service.await_pending_deletions()
    final = await service.get_deletion(operation.id)
    assert final is not None and final.stage == "done"
    assert await repo.get_profile(profile.id) is None
    assert all(not d.exists() for d in dirs)


async def test_late_instance_event_does_not_resurrect_deleted(service, repo):
    """AC-004: after an intent completes, a late observed-state report
    from the deleted instance changes nothing."""
    profile = await _make_running(repo, "ghost")
    stop_event = asyncio.Event()
    simulator = asyncio.create_task(
        _supervisor_simulator(repo, profile.id, stop_event)
    )
    try:
        _batch, operations = await service.request_deletions([profile.id])
        await service.await_pending_deletions()
    finally:
        stop_event.set()
        await simulator
    final = await service.get_deletion(operations[0].id)
    assert final is not None and final.stage == "done"
    assert await repo.get_profile(profile.id) is None

    late = await repo.report_observed_state(profile.id, "inst-1", "running")
    assert late is None
    assert await repo.get_profile(profile.id) is None
    assert await repo.find_open_deletion(profile.id) is None
    final = await service.get_deletion(operations[0].id)
    assert final is not None and final.stage == "done"


async def test_late_request_joins_finished_intent_not_a_failed_one(
    service, repo
):
    """p136: a request arriving after a concurrent deletion finished must
    re-join that done intent, never create a second ``failed`` intent."""
    profile = await _make_profile(repo, "late-race-target")
    first_batch, first_ops = await service.request_deletions([profile.id])
    await service.await_pending_deletions()
    assert (await service.get_deletion(first_ops[0].id)).stage == "done"
    assert await repo.get_profile(profile.id) is None

    second_batch, second_ops = await service.request_deletions([profile.id])

    assert second_batch != first_batch
    assert len(second_ops) == 1
    assert second_ops[0].id == first_ops[0].id
    assert second_ops[0].stage == "done"
    assert second_ops[0].error is None
    assert [
        op.id for op in await service.list_deletion_batch(second_batch)
    ] == [first_ops[0].id]


async def test_two_confirming_batches_both_observe_the_intent(service, repo):
    """p130: two clients confirming the same intent must both be able to
    poll their own batch. Membership is a set of rows, not a single
    mutable ``batch_id`` on the intent."""
    profile = await _make_profile(repo, "two-batch-target")
    first_batch, first_ops = await service.request_deletions([profile.id])
    second_batch, second_ops = await service.request_deletions([profile.id])

    assert first_batch != second_batch
    assert first_ops[0].id == second_ops[0].id
    assert [
        op.id for op in await service.list_deletion_batch(first_batch)
    ] == [first_ops[0].id]
    assert [
        op.id for op in await service.list_deletion_batch(second_batch)
    ] == [second_ops[0].id]

    await service.await_pending_deletions()
    final = await service.get_deletion(first_ops[0].id)
    assert final is not None and final.stage == "done"
