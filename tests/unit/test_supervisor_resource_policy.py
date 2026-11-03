import pytest
from cbrowser.supervisor.resource_policy import (
    HostCpuSample,
    ResourcePolicyConfig,
    ResourcePolicyService,
    calculate_host_cpu_percent,
    parse_linux_proc_stat_cpu,
)

# --- 1. 保留旧测试原样语义 ---


def test_resource_policy_overload_and_hysteresis():
    config = ResourcePolicyConfig(
        overload_cpu_threshold_pct=80.0,
        recovery_cpu_threshold_pct=50.0,
        overload_window_samples=2,
        recovery_window_samples=2,
        throttled_fps_cap=8.0,
        min_measurement_interval_sec=0.0,
    )
    service = ResourcePolicyService(docker_client=None, config=config)
    profile_id = "test_profile_01"
    container_id = "c_001"
    limit = 1_000_000_000  # 1 core limit

    stats_0 = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 1_000_000_000},
            "system_cpu_usage": 10_000_000_000,
            "online_cpus": 10,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 1_000_000_000},
            "system_cpu_usage": 10_000_000_000,
        },
    }
    decision = service.record_stats(
        profile_id, container_id, stats_0, nano_cpus_limit=limit
    )
    assert decision.max_fps_cap is None
    assert not decision.is_throttled

    stats_1 = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 1_900_000_000},
            "system_cpu_usage": 20_000_000_000,
            "online_cpus": 10,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 1_000_000_000},
            "system_cpu_usage": 10_000_000_000,
        },
    }
    decision = service.record_stats(
        profile_id, container_id, stats_1, nano_cpus_limit=limit
    )
    assert decision.max_fps_cap is None
    assert not decision.is_throttled
    assert "pending_overload" in decision.reason

    stats_2 = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 2_800_000_000},
            "system_cpu_usage": 30_000_000_000,
            "online_cpus": 10,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 1_900_000_000},
            "system_cpu_usage": 20_000_000_000,
        },
    }
    decision = service.record_stats(
        profile_id, container_id, stats_2, nano_cpus_limit=limit
    )
    assert decision.max_fps_cap == 8.0
    assert decision.is_throttled
    assert "overload" in decision.reason

    stats_3 = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 3_400_000_000},
            "system_cpu_usage": 40_000_000_000,
            "online_cpus": 10,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 2_800_000_000},
            "system_cpu_usage": 30_000_000_000,
        },
    }
    decision = service.record_stats(
        profile_id, container_id, stats_3, nano_cpus_limit=limit
    )
    assert decision.max_fps_cap == 8.0
    assert decision.is_throttled
    assert "hysteresis" in decision.reason

    stats_4 = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 3_600_000_000},
            "system_cpu_usage": 50_000_000_000,
            "online_cpus": 10,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 3_400_000_000},
            "system_cpu_usage": 40_000_000_000,
        },
    }
    decision = service.record_stats(
        profile_id, container_id, stats_4, nano_cpus_limit=limit
    )
    assert decision.max_fps_cap == 8.0
    assert decision.is_throttled
    assert "pending_recovery" in decision.reason

    stats_5 = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 3_800_000_000},
            "system_cpu_usage": 60_000_000_000,
            "online_cpus": 10,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 3_600_000_000},
            "system_cpu_usage": 50_000_000_000,
        },
    }
    decision = service.record_stats(
        profile_id, container_id, stats_5, nano_cpus_limit=limit
    )
    assert decision.max_fps_cap is None
    assert not decision.is_throttled
    assert "recovered" in decision.reason


def test_resource_policy_background_or_low_load():
    config = ResourcePolicyConfig(min_measurement_interval_sec=0.0)
    service = ResourcePolicyService(docker_client=None, config=config)
    profile_id = "test_profile_bg"
    container_id = "c_bg"
    limit = 1_000_000_000

    for i in range(5):
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 1_000_000_000 + i * 50_000_000},
                "system_cpu_usage": 10_000_000_000 + i * 10_000_000_000,
                "online_cpus": 10,
            },
            "precpu_stats": {
                "cpu_usage": {
                    "total_usage": 1_000_000_000 + (i - 1) * 50_000_000
                    if i > 0
                    else 1_000_000_000
                },
                "system_cpu_usage": 10_000_000_000 + (i - 1) * 10_000_000_000
                if i > 0
                else 10_000_000_000,
            },
        }
        decision = service.record_stats(
            profile_id,
            container_id,
            stats,
            nano_cpus_limit=limit,
            has_foreground_viewers=False,
        )
        assert decision.max_fps_cap is None
        assert not decision.is_throttled
        assert "nominal" in decision.reason


# --- 2. 新增定向缺口验证用例 ---


def test_config_validation():
    with pytest.raises(ValueError, match="NaN"):
        ResourcePolicyConfig(overload_cpu_threshold_pct=float("nan"))

    with pytest.raises(
        ValueError, match="recovery.*must be strictly less than overload"
    ):
        ResourcePolicyConfig(
            overload_cpu_threshold_pct=50.0, recovery_cpu_threshold_pct=60.0
        )

    with pytest.raises(ValueError, match="window.*must be >= 1"):
        ResourcePolicyConfig(overload_window_samples=0)

    with pytest.raises(ValueError, match="throttled_fps_cap.*between 8.0 and 30.0"):
        ResourcePolicyConfig(throttled_fps_cap=5.0)
    with pytest.raises(ValueError, match="throttled_fps_cap.*between 8.0 and 30.0"):
        ResourcePolicyConfig(throttled_fps_cap=35.0)


def test_parse_linux_proc_stat_cpu():
    line = "cpu  9873557 90303 4083584 953548416 1555937 0 1972478 0 0 0\n"
    sample = parse_linux_proc_stat_cpu(line)
    assert sample.user == 9873557
    assert sample.nice == 90303
    assert sample.system == 4083584
    assert sample.idle == 953548416
    assert sample.iowait == 1555937
    assert sample.irq == 0
    assert sample.softirq == 1972478
    assert sample.total_ticks == (
        9873557 + 90303 + 4083584 + 953548416 + 1555937 + 0 + 1972478
    )
    assert sample.busy_ticks == sample.total_ticks - (953548416 + 1555937)


def test_calculate_host_cpu_percent():
    s1 = HostCpuSample(
        total_ticks=1000, busy_ticks=200, idle_ticks=800, timestamp_monotonic=1.0
    )
    s2 = HostCpuSample(
        total_ticks=2000, busy_ticks=700, idle_ticks=1300, timestamp_monotonic=2.0
    )
    pct = calculate_host_cpu_percent(s2, s1)
    assert pytest.approx(pct, 0.1) == 50.0


def test_10cpu_no_quota_low_total_load_no_false_positive():
    """One fully busy core is only 10% host load on this ten-core VM."""
    config = ResourcePolicyConfig(
        overload_cpu_threshold_pct=75.0,
        recovery_cpu_threshold_pct=40.0,
        overload_window_samples=2,
        throttled_fps_cap=8.0,
        min_measurement_interval_sec=0.0,
    )
    service = ResourcePolicyService(docker_client=None, config=config)
    profile_id = "prof_10cpu_unlimited"
    container_id = "c_unlimited"

    # One busy core: 1e9 ns usage over 10e9 ns aggregate system time.
    # nano_cpus_limit = 0 (unlimited)
    for i in range(1, 4):
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": (i + 1) * 1_000_000_000},
                "system_cpu_usage": (i + 1) * 10_000_000_000,
                "online_cpus": 10,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": i * 1_000_000_000},
                "system_cpu_usage": i * 10_000_000_000,
            },
        }
        decision = service.record_stats(
            profile_id,
            container_id,
            stats,
            nano_cpus_limit=0,
            has_foreground_viewers=True,
        )
        # Observed CPU percent on total host capacity is only 10.0%
        assert pytest.approx(decision.observed_cpu_pct, 0.1) == 10.0
        assert decision.is_throttled is False
        assert decision.max_fps_cap is None


def test_container_quota_overload_vs_host_scope_disclosure():
    """Quota pressure reports its actual container scope and reason."""
    config = ResourcePolicyConfig(
        overload_cpu_threshold_pct=80.0,
        recovery_cpu_threshold_pct=40.0,
        overload_window_samples=2,
        min_measurement_interval_sec=0.0,
    )
    service = ResourcePolicyService(docker_client=None, config=config)
    profile_id = "prof_quota"
    container_id = "c_quota"
    limit = 500_000_000  # 0.5 core quota

    for i in range(1, 4):
        stats = {
            # Consuming 0.45 core = 90% of its 0.5 core quota
            "cpu_stats": {
                "cpu_usage": {"total_usage": (i + 1) * 450_000_000},
                "system_cpu_usage": (i + 1) * 10_000_000_000,
                "online_cpus": 10,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": i * 450_000_000},
                "system_cpu_usage": i * 10_000_000_000,
            },
        }
        decision = service.record_stats(
            profile_id,
            container_id,
            stats,
            nano_cpus_limit=limit,
            has_foreground_viewers=True,
        )

    assert decision.is_throttled is True
    assert decision.max_fps_cap == 8.0
    assert "container_quota_overload" in decision.reason
    assert decision.observed_scope == "container_quota"
    assert pytest.approx(decision.observed_cpu_pct, 0.1) == 90.0


def test_monotonic_and_min_measurement_interval_dedup():
    """Duplicate counters and rapid polling must not advance pressure windows."""
    config = ResourcePolicyConfig(
        overload_cpu_threshold_pct=80.0,
        overload_window_samples=2,
        min_measurement_interval_sec=0.5,
    )
    service = ResourcePolicyService(docker_client=None, config=config)
    profile_id = "prof_rate_limit"
    container_id = "c_fast"
    limit = 1_000_000_000

    stats = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 1_900_000_000},
            "system_cpu_usage": 20_000_000_000,
            "online_cpus": 10,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 1_000_000_000},
            "system_cpu_usage": 10_000_000_000,
        },
    }

    # First record
    d1 = service.record_stats(
        profile_id, container_id, stats, nano_cpus_limit=limit, current_monotonic=1.0
    )
    assert d1.sample_count == 1

    # Immediate second call with same timestamp/counter (< 0.5s interval)
    d2 = service.record_stats(
        profile_id, container_id, stats, nano_cpus_limit=limit, current_monotonic=1.1
    )
    assert d2.sample_count == 1
    assert not d2.is_throttled


def test_missing_or_corrupt_stats_preserves_state():
    """Corrupt or missing stats must not be treated as 0% load to falsely unthrottle."""
    config = ResourcePolicyConfig(
        overload_window_samples=1,
        throttled_fps_cap=8.0,
        min_measurement_interval_sec=0.0,
    )
    service = ResourcePolicyService(docker_client=None, config=config)
    profile_id = "prof_corrupt"
    container_id = "c_err"

    stats_overload = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 1_900_000_000},
            "system_cpu_usage": 20_000_000_000,
            "online_cpus": 10,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 1_000_000_000},
            "system_cpu_usage": 10_000_000_000,
        },
    }
    d1 = service.record_stats(
        profile_id, container_id, stats_overload, nano_cpus_limit=1_000_000_000
    )
    assert d1.is_throttled is True

    d2 = service.record_stats(
        profile_id, container_id, {}, nano_cpus_limit=1_000_000_000
    )
    assert d2.is_throttled is True
    assert "invalid_stats_retained" in d2.reason
