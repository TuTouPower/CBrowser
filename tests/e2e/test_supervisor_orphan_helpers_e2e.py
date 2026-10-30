"""Startup reaps only positively owned transient helpers using real Docker."""

import os
import uuid

import docker
import pytest
from cbrowser.supervisor.coordinator_lock import CoordinatorLock
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.path_validator import PathValidator


@pytest.mark.asyncio
async def test_locked_startup_reaps_helpers_without_touching_other_containers(tmp_path):
    image = os.environ.get("CBROWSER_RUNTIME_TEST_IMAGE")
    if not image:
        pytest.skip("CBROWSER_RUNTIME_TEST_IMAGE is required")
    assert image.startswith("sha256:") or "@sha256:" in image
    client = docker.from_env()
    client.images.get(image)
    cache = tmp_path / "engine_cache"
    (cache / "geoip").mkdir(parents=True)
    prefix = "t005-orphans-" + uuid.uuid4().hex[:10]
    adapter = DockerAdapter(
        PathValidator(tmp_path),
        cache,
        docker_client=client,
        browser_image=image,
        stream_image=image,
        resource_prefix=prefix,
    )
    containers = []

    def launch(name, role, *, managed="supervisor", owned_prefix=prefix):
        container = client.containers.run(
            image,
            entrypoint="python3",
            command=["-c", "import time; time.sleep(120)"],
            name=name,
            detach=True,
            network_mode="none",
            user="1000:1000",
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            labels={
                "com.cbrowser.prefix": owned_prefix,
                "com.cbrowser.managed-by": managed,
                "com.cbrowser.role": role,
            },
        )
        containers.append(container)
        return container

    try:
        cache_helper = launch(prefix + "-cache-" + uuid.uuid4().hex[:12], "cache-init")
        policy_helper = launch(
            prefix + "-policy-" + uuid.uuid4().hex[:12], "network-policy"
        )
        policy_helper.stop(timeout=1)
        runtime = launch(prefix + "-browser-profile", "browser")
        gateway = launch(prefix + "-gateway", "gateway")
        foreign = launch(
            prefix + "-cache-" + uuid.uuid4().hex[:12], "cache-init", managed="other"
        )
        with CoordinatorLock(tmp_path / "supervisor.lock"):
            await adapter.cleanup_orphan_helpers()
            await adapter.cleanup_orphan_helpers()
        for removed in (cache_helper, policy_helper):
            with pytest.raises(docker.errors.NotFound):
                client.containers.get(removed.id)
        for retained in (runtime, gateway, foreign):
            retained.reload()
            assert retained.status == "running"
        # Even matching ownership labels cannot authorize an unrelated name.
        mismatched = launch(prefix + "-unrelated", "cache-init")
        with CoordinatorLock(tmp_path / "supervisor.lock"):
            with pytest.raises(DockerSandboxError, match="helper ownership"):
                await adapter.cleanup_orphan_helpers()
        mismatched.reload()
        assert mismatched.status == "running"
    finally:
        try:
            for container in containers:
                try:
                    container.remove(force=True)
                except docker.errors.NotFound:
                    pass
        finally:
            client.close()
