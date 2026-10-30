"""Multiple live inputs must compose without cancelling another pressure source."""

from cbrowser.supervisor.resource_policy import (
    HostCpuSample,
    ResourcePolicyConfig,
    ResourcePolicyService,
    container_cpu_limit,
)


def test_cpu_limit_uses_tightest_actual_docker_constraint():
    assert (
        container_cpu_limit({"CpuQuota": 50_000, "CpuPeriod": 100_000}) == 500_000_000
    )
    assert (
        container_cpu_limit(
            {"NanoCpus": 2_000_000_000, "CpuQuota": 100_000, "CpuPeriod": 100_000}
        )
        == 1_000_000_000
    )
    assert container_cpu_limit({"CpusetCpus": "0-1,4"}) == 3_000_000_000
    assert container_cpu_limit({"CpuQuota": -1}) == 0


def host(tick, busy):
    return HostCpuSample(tick, busy, tick - busy, tick / 1000)


def service():
    result = ResourcePolicyService(
        config=ResourcePolicyConfig(
            overload_window_samples=2,
            recovery_window_samples=2,
            min_measurement_interval_sec=0,
        )
    )
    result.get_profile_state("profile")
    return result


def hot_host(policy):
    for sample in (host(1000, 100), host(2000, 1000), host(3000, 1900)):
        policy.record_host_sample(sample)


def test_registered_profile_requires_two_host_pressure_windows():
    policy = service()
    policy.record_host_sample(host(1000, 100))
    first = policy.record_host_sample(host(2000, 1000))["profile"]
    assert not first.is_throttled
    second = policy.record_host_sample(host(3000, 1900))["profile"]
    assert second.max_fps_cap == 8
    assert second.observed_scope == "docker_host_linux"


def test_host_recovery_releases_its_own_quota():
    policy = service()
    hot_host(policy)
    assert policy.get_decision("profile").is_throttled
    policy.record_host_sample(host(4000, 2000))
    assert policy.get_decision("profile").is_throttled
    policy.record_host_sample(host(5000, 2100))
    assert policy.get_decision("profile").max_fps_cap is None


def test_host_updates_preserve_background_visibility():
    policy = service()
    policy.evaluate_profile("profile", has_foreground_viewers=False)
    hot_host(policy)
    assert policy.get_decision("profile").max_fps_cap is None


def stats(step, used):
    return {
        "cpu_stats": {
            "cpu_usage": {"total_usage": step * used},
            "system_cpu_usage": step * 10_000_000_000,
            "online_cpus": 10,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": (step - 1) * used},
            "system_cpu_usage": (step - 1) * 10_000_000_000,
        },
    }


def test_idle_stream_cannot_clear_overloaded_browser():
    policy = service()
    for step in (2, 3):
        policy.record_stats(
            "profile",
            "browser",
            stats(step, 900_000_000),
            nano_cpus_limit=1_000_000_000,
        )
        decision = policy.record_stats(
            "profile", "stream", stats(step, 10_000_000), nano_cpus_limit=1_000_000_000
        )
    assert decision.is_throttled
    assert decision.max_fps_cap == 8


def test_identical_counter_window_is_not_counted_twice():
    policy = service()
    sample = stats(2, 900_000_000)
    policy.record_stats(
        "profile", "browser", sample, nano_cpus_limit=1_000_000_000, current_monotonic=1
    )
    duplicate = policy.record_stats(
        "profile", "browser", sample, nano_cpus_limit=1_000_000_000, current_monotonic=2
    )
    assert not duplicate.is_throttled
    assert duplicate.sample_count == 1


def test_partial_stats_cannot_count_as_recovery():
    policy = service()
    for step in (2, 3):
        policy.record_stats(
            "profile",
            "browser",
            stats(step, 900_000_000),
            nano_cpus_limit=1_000_000_000,
        )
    for step in (4, 5):
        partial = {"cpu_stats": {"cpu_usage": {"total_usage": step * 900_000_000}}}
        decision = policy.record_stats(
            "profile", "browser", partial, nano_cpus_limit=1_000_000_000
        )
    assert decision.is_throttled


def test_host_overload_windows_must_be_consecutive():
    policy = service()
    for sample in (
        host(1000, 100),
        host(2000, 1000),
        host(3000, 1600),
        host(4000, 2500),
    ):
        policy.record_host_sample(sample)
    assert policy.get_decision("profile").max_fps_cap is None


def test_reset_counters_are_not_idle_recovery_windows():
    policy = service()
    for step in (2, 3):
        policy.record_stats(
            "profile",
            "browser",
            stats(step, 900_000_000),
            nano_cpus_limit=1_000_000_000,
        )
    assert policy.get_decision("profile").is_throttled
    for step, usage in ((4, 10), (5, 5)):
        reset = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": usage},
                "system_cpu_usage": step * 10_000_000_000,
                "online_cpus": 10,
            }
        }
        decision = policy.record_stats(
            "profile", "browser", reset, nano_cpus_limit=1_000_000_000
        )
    assert decision.is_throttled
