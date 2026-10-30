import json
import os
import time
import uuid

import docker
import pytest
from cbrowser.supervisor.resource_policy import (
    ResourcePolicyConfig,
    ResourcePolicyService,
)


def get_stream_test_image(client: docker.DockerClient) -> str:
    stream_img = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    if not stream_img:
        pytest.skip(
            "Missing required E2E environment variable: CBROWSER_STREAM_TEST_IMAGE"
        )
    assert stream_img.startswith("sha256:"), (
        f"CBROWSER_STREAM_TEST_IMAGE must be sha256 immutable digest, got {stream_img}"
    )
    client.images.get(stream_img)
    return stream_img


@pytest.fixture(scope="module")
def docker_client():
    client = docker.from_env()
    assert client.ping() is True
    return client


def test_docker_real_cpu_sampling_and_overload_e2e(docker_client):
    stream_image = get_stream_test_image(docker_client)
    run_id = uuid.uuid4().hex[:8]
    created_container_ids = []

    # 0.5 CPU quota = 500_000_000 nano_cpus
    nano_cpus = 500_000_000
    container_name = f"t005_resource_burner_{run_id}"
    profile_id = f"t005_e2e_profile_{run_id}"

    config = ResourcePolicyConfig(
        overload_cpu_threshold_pct=70.0,
        recovery_cpu_threshold_pct=30.0,
        overload_window_samples=2,
        recovery_window_samples=2,
        throttled_fps_cap=8.0,
        min_measurement_interval_sec=0.2,
    )
    service = ResourcePolicyService(docker_client=docker_client, config=config)

    records = {
        "run_id": run_id,
        "image_sha": stream_image,
        "nano_cpus": nano_cpus,
        "samples": [],
    }

    # Burn CPU for 3.5 seconds with python3 busy loop then sleep
    cmd = [
        "-u",
        "-c",
        (
            "import time; end=time.time()+3.5;\n"
            "while time.time()<end:\n"
            "    _=[x*x for x in range(5000)]\n"
            "time.sleep(15)"
        ),
    ]
    try:
        container = docker_client.containers.run(
            stream_image,
            entrypoint="python3",
            command=cmd,
            name=container_name,
            nano_cpus=nano_cpus,
            detach=True,
            remove=False,
            user=1000,
            read_only=True,
            cap_drop=["ALL"],
            network_mode="none",
        )
        created_container_ids.append(container.id)

        # 1. Warm-up wait for container process
        time.sleep(0.5)

        # Sample 1
        d1 = service.sample_container_stats(
            profile_id,
            container.id,
            nano_cpus_limit=nano_cpus,
            has_foreground_viewers=True,
        )
        raw_stats_1 = container.stats(stream=False, one_shot=True)
        records["samples"].append(
            {
                "step": "sample_1",
                "decision": d1.__dict__ if d1 else None,
                "raw_stats": raw_stats_1,
            }
        )

        # Sample 2 (1.0s later, burning CPU)
        time.sleep(1.0)
        d2 = service.sample_container_stats(
            profile_id,
            container.id,
            nano_cpus_limit=nano_cpus,
            has_foreground_viewers=True,
        )
        raw_stats_2 = container.stats(stream=False, one_shot=True)
        records["samples"].append(
            {
                "step": "sample_2",
                "decision": d2.__dict__ if d2 else None,
                "raw_stats": raw_stats_2,
            }
        )

        # Sample 3 (1.0s later, burning CPU, hits overload window count >= 2)
        time.sleep(1.0)
        d3 = service.sample_container_stats(
            profile_id,
            container.id,
            nano_cpus_limit=nano_cpus,
            has_foreground_viewers=True,
        )
        raw_stats_3 = container.stats(stream=False, one_shot=True)
        records["samples"].append(
            {
                "step": "sample_3",
                "decision": d3.__dict__ if d3 else None,
                "raw_stats": raw_stats_3,
            }
        )

        assert d3 is not None
        assert d3.observed_cpu_pct > 60.0
        assert d3.is_throttled is True
        assert d3.max_fps_cap == 8.0
        assert "overload" in d3.reason
        assert d3.observed_scope == "container_quota"

        # 2. Burner loop ended at t=3.5s, now in sleep(15).
        # Wait 2.0s for load to settle to 0.
        time.sleep(2.0)

        # Sample 4 (settling / low load sample 1)
        d4 = service.sample_container_stats(
            profile_id,
            container.id,
            nano_cpus_limit=nano_cpus,
            has_foreground_viewers=True,
        )
        raw_stats_4 = container.stats(stream=False, one_shot=True)
        records["samples"].append(
            {
                "step": "sample_4",
                "decision": d4.__dict__ if d4 else None,
                "raw_stats": raw_stats_4,
            }
        )

        # Sample 5 (recovery sample 1 under sleep)
        time.sleep(1.0)
        d5 = service.sample_container_stats(
            profile_id,
            container.id,
            nano_cpus_limit=nano_cpus,
            has_foreground_viewers=True,
        )
        raw_stats_5 = container.stats(stream=False, one_shot=True)
        records["samples"].append(
            {
                "step": "sample_5",
                "decision": d5.__dict__ if d5 else None,
                "raw_stats": raw_stats_5,
            }
        )

        # Sample 6 (recovery sample 2 under sleep -> UNTHROTTLED)
        time.sleep(1.0)
        d6 = service.sample_container_stats(
            profile_id,
            container.id,
            nano_cpus_limit=nano_cpus,
            has_foreground_viewers=True,
        )
        raw_stats_6 = container.stats(stream=False, one_shot=True)
        records["samples"].append(
            {
                "step": "sample_6",
                "decision": d6.__dict__ if d6 else None,
                "raw_stats": raw_stats_6,
            }
        )

        assert d6 is not None
        assert d6.observed_cpu_pct <= 30.0
        assert d6.is_throttled is False
        assert d6.max_fps_cap is None
        assert "recovered" in d6.reason or "nominal" in d6.reason

        # Write raw verified machine record if record directory configured
        record_dir = os.environ.get("CBROWSER_RECORD_DIR")
        if record_dir and os.path.isdir(record_dir):
            out_file = os.path.join(record_dir, f"real_sampling_record_{run_id}.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)

    finally:
        for cid in created_container_ids:
            try:
                c = docker_client.containers.get(cid)
                c.remove(force=True)
            except Exception:
                pass


def test_docker_real_host_proc_stat_sampling(docker_client):
    stream_image = get_stream_test_image(docker_client)
    run_id = uuid.uuid4().hex[:8]

    def host_stat_reader() -> str:
        cmd = ["-n", "10", "/proc/stat"]
        out = docker_client.containers.run(
            stream_image,
            entrypoint="head",
            command=cmd,
            remove=True,
            user=1000,
            read_only=True,
            cap_drop=["ALL"],
            network_mode="none",
        )
        return out.decode()

    config = ResourcePolicyConfig(
        overload_cpu_threshold_pct=85.0,
        recovery_cpu_threshold_pct=40.0,
        overload_window_samples=2,
    )
    service = ResourcePolicyService(
        docker_client=docker_client, config=config, host_stat_reader=host_stat_reader
    )
    profile_id = f"t005_e2e_host_{run_id}"

    service.sample_host_proc_stat()
    time.sleep(0.5)
    res2 = service.sample_host_proc_stat()

    assert res2 is not None
    dec = service.evaluate_profile(profile_id, has_foreground_viewers=True)
    assert dec.is_throttled is False
    assert dec.max_fps_cap is None


def test_docker_background_profile_with_high_cpu_not_throttled(docker_client):
    """High CPU burning container with has_foreground_viewers=False.

    Must NOT throttle max_fps_cap.
    """
    stream_image = get_stream_test_image(docker_client)
    run_id = uuid.uuid4().hex[:8]
    created_container_ids = []
    nano_cpus = 500_000_000
    container_name = f"t005_resource_burner_bg_{run_id}"
    profile_id = f"t005_e2e_bg_profile_{run_id}"

    config = ResourcePolicyConfig(
        overload_cpu_threshold_pct=70.0,
        recovery_cpu_threshold_pct=30.0,
        overload_window_samples=2,
    )
    service = ResourcePolicyService(docker_client=docker_client, config=config)

    cmd = [
        "-u",
        "-c",
        (
            "import time; end=time.time()+3.0;\n"
            "while time.time()<end:\n"
            "    _=[x*x for x in range(5000)]"
        ),
    ]
    try:
        container = docker_client.containers.run(
            stream_image,
            entrypoint="python3",
            command=cmd,
            name=container_name,
            nano_cpus=nano_cpus,
            detach=True,
            remove=False,
            user=1000,
            read_only=True,
            cap_drop=["ALL"],
            network_mode="none",
        )
        created_container_ids.append(container.id)

        time.sleep(0.5)
        for _ in range(3):
            time.sleep(0.8)
            d = service.sample_container_stats(
                profile_id,
                container.id,
                nano_cpus_limit=nano_cpus,
                has_foreground_viewers=False,
            )
            assert d is not None
            assert d.is_throttled is False
            assert d.max_fps_cap is None
            assert d.reason == "nominal_background"

    finally:
        for cid in created_container_ids:
            try:
                c = docker_client.containers.get(cid)
                c.remove(force=True)
            except Exception:
                pass
