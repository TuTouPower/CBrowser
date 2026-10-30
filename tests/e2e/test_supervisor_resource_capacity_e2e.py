"""Sampler must discover the actual container limit without caller hints."""

import os
import time
import uuid

import docker
import pytest
from cbrowser.supervisor.resource_policy import (
    ResourcePolicyConfig,
    ResourcePolicyService,
)


def test_sampler_discovers_real_container_cpu_limit():
    image = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    if not image:
        pytest.skip(
            "Missing required E2E environment variable: CBROWSER_STREAM_TEST_IMAGE"
        )
    assert image.startswith("sha256:"), (
        f"CBROWSER_STREAM_TEST_IMAGE must be sha256 immutable digest, got {image}"
    )
    client = docker.from_env()
    client.images.get(image)
    container = None
    try:
        container = client.containers.run(
            image,
            [
                "-c",
                (
                    "import time\nend=time.monotonic()+12\n"
                    "while time.monotonic()<end: sum(x*x for x in range(10000))"
                ),
            ],
            entrypoint="python3",
            name="t005_capacity_" + uuid.uuid4().hex[:12],
            detach=True,
            user="1000:1000",
            read_only=True,
            cap_drop=["ALL"],
            network_mode="none",
            nano_cpus=500_000_000,
        )
        policy = ResourcePolicyService(
            client,
            ResourcePolicyConfig(
                overload_window_samples=2,
                overload_cpu_threshold_pct=70,
            ),
        )
        for _ in range(4):
            time.sleep(0.75)
            decision = policy.sample_container_stats("profile", container.id)
            assert decision is not None
        assert decision.observed_scope == "container_quota"
        assert decision.is_throttled
    finally:
        if container is not None:
            container.remove(force=True)
        client.close()
