"""Runtime event semantics, including three retries after the first failure."""

import pytest
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import ProfileConfig, RuntimeEvent
from test_domain_and_repository import db_context as db_context
from test_domain_and_repository import temp_db_path as temp_db_path


async def live_profile(context):
    repo = ProfileRepository(context[1])
    profile = await repo.create_profile(ProfileConfig(name="runtime_policy"))
    await repo.set_desired_state(profile.id, "running")
    await repo.bind_runtime_instance(profile.id, "initial", config_version=1)
    await repo.report_observed_state(profile.id, "initial", "running")
    return repo, profile


@pytest.mark.asyncio
async def test_non_exit_and_invalid_version_do_not_mutate_live_runtime(db_context):
    repo, profile = await live_profile(db_context)
    for kind, version, expected in (
        ("heartbeat", 1, "applied"),
        ("exit", 999, "invalid_config_version"),
    ):
        outcome = await repo.consume_runtime_event(
            RuntimeEvent(
                event_id=kind,
                profile_id=profile.id,
                runtime_instance_id="initial",
                event_type=kind,
                config_version=version,
                exit_code=137 if kind == "exit" else None,
            )
        )
        assert outcome == expected
        state = await repo.get_runtime(profile.id)
        assert (state.desired_state, state.observed_state, state.failure_count) == (
            "running",
            "running",
            0,
        )


@pytest.mark.asyncio
async def test_normal_exit_replay_does_not_clear_new_running_intent(db_context):
    repo, profile = await live_profile(db_context)
    event = RuntimeEvent(
        event_id="normal",
        profile_id=profile.id,
        runtime_instance_id="initial",
        event_type="exit",
        exit_code=0,
        exit_reason="normal",
        config_version=1,
    )
    assert await repo.consume_runtime_event(event) == "applied"
    stopped = await repo.get_runtime(profile.id)
    assert stopped.desired_state == "stopped" and stopped.observed_state == "stopped"
    assert (
        stopped.runtime_instance_id is None and stopped.last_exit_event_id == "normal"
    )
    await repo.set_desired_state(profile.id, "running")
    assert await repo.consume_runtime_event(event) == "duplicate"
    assert (await repo.get_runtime(profile.id)).desired_state == "running"


@pytest.mark.asyncio
async def test_three_failed_retries_block_after_four_abnormal_runtime_exits(db_context):
    repo, profile = await live_profile(db_context)
    for index in range(4):
        instance = "initial" if index == 0 else f"retry_{index}"
        if index:
            await repo.bind_runtime_instance(profile.id, instance, config_version=1)
        assert (
            await repo.consume_runtime_event(
                RuntimeEvent(
                    event_id=f"failure_{index}",
                    profile_id=profile.id,
                    runtime_instance_id=instance,
                    event_type="exit",
                    exit_code=137,
                    exit_reason="crash",
                    config_version=1,
                )
            )
            == "applied"
        )
        state = await repo.get_runtime(profile.id)
        assert state.desired_state == "running"
        assert state.failure_count == index + 1
        assert state.restart_blocked is (index == 3)


@pytest.mark.asyncio
async def test_late_abnormal_exit_cannot_restore_a_user_stopped_intent(db_context):
    repo, profile = await live_profile(db_context)
    await repo.set_desired_state(profile.id, "stopped")
    await repo.consume_runtime_event(
        RuntimeEvent(
            event_id="late_failure",
            profile_id=profile.id,
            runtime_instance_id="initial",
            event_type="exit",
            exit_code=137,
            exit_reason="crash",
            config_version=1,
        )
    )
    state = await repo.get_runtime(profile.id)
    assert state.desired_state == "stopped" and state.observed_state == "stopped"
