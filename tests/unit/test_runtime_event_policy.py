"""Runtime event semantics and observation authority.

Disk events are diagnostics only: lifecycle state must converge from the
Supervisor's Docker/Agent observations. Terminal error observations preserve
running intent and count failures; a clean close clears running intent.
"""

import pytest
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import ProfileConfig, RuntimeEvent


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
async def test_abnormal_exit_event_does_not_change_lifecycle_state(db_context):
    repo, profile = await live_profile(db_context)
    outcome = await repo.consume_runtime_event(
        RuntimeEvent(
            event_id="forged_exit",
            profile_id=profile.id,
            runtime_instance_id="initial",
            event_type="exit",
            exit_code=137,
            exit_reason="crash",
            config_version=1,
        )
    )
    assert outcome == "applied"
    state = await repo.get_runtime(profile.id)
    assert state.desired_state == "running"
    assert state.observed_state == "running"
    assert state.runtime_instance_id == "initial"
    assert state.failure_count == 0


@pytest.mark.asyncio
async def test_error_observations_count_failures_and_block_after_four(db_context):
    repo, profile = await live_profile(db_context)
    for index in range(4):
        instance = "initial" if index == 0 else f"retry_{index}"
        if index:
            await repo.bind_runtime_instance(profile.id, instance, config_version=1)
            await repo.report_observed_state(profile.id, instance, "running")
        await repo.report_observed_state(
            profile.id, instance, "error", reason="process_lost"
        )
        state = await repo.get_runtime(profile.id)
        assert state.desired_state == "running"
        assert state.observed_state == "error"
        assert state.runtime_instance_id is None
        assert state.failure_count == index + 1
        assert state.restart_blocked is (index == 3)


@pytest.mark.asyncio
async def test_normal_exit_observation_clears_running_intent(db_context):
    repo, profile = await live_profile(db_context)
    await repo.report_observed_state(
        profile.id, "initial", "stopped", reason="normal_exit"
    )
    state = await repo.get_runtime(profile.id)
    assert state.desired_state == "stopped"
    assert state.observed_state == "stopped"
    assert state.runtime_instance_id is None
    assert state.failure_count == 0


@pytest.mark.asyncio
async def test_repeated_error_observation_for_same_instance_counts_once(db_context):
    repo, profile = await live_profile(db_context)
    await repo.report_observed_state(
        profile.id, "initial", "error", reason="process_lost"
    )
    second = await repo.report_observed_state(
        profile.id, "initial", "error", reason="process_lost"
    )
    assert second is None
    state = await repo.get_runtime(profile.id)
    assert state.failure_count == 1
