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
