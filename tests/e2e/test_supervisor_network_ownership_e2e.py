"""A colliding Docker resource name must never grant ownership."""

import uuid

import docker
import pytest
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.path_validator import PathValidator


@pytest.mark.asyncio
async def test_foreign_network_is_neither_reused_nor_removed(tmp_path):
    client = docker.from_env()
    prefix = f"t005-owner-{uuid.uuid4().hex[:10]}"
    (tmp_path / "engine_cache").mkdir()
    (tmp_path / "engine_cache" / "geoip").mkdir()
    adapter = DockerAdapter(
        PathValidator(tmp_path),
        tmp_path / "engine_cache",
        docker_client=client,
        browser_image="sha256:unused-browser",
        stream_image="sha256:unused-stream",
        resource_prefix=prefix,
    )
    name = adapter.get_network_name("profile_a")
    foreign = client.networks.create(name, labels={"test.owner": prefix})
    try:
        with pytest.raises(DockerSandboxError, match="ownership"):
            await adapter.create_profile_network("profile_a")
        with pytest.raises(DockerSandboxError, match="ownership"):
            adapter.cleanup_network_by_name(name)
        assert client.networks.get(foreign.id).id == foreign.id
    finally:
        foreign.remove()
        client.close()


@pytest.mark.asyncio
async def test_owned_network_creation_is_idempotent_and_cleanup_is_exact(tmp_path):
    client = docker.from_env()
    prefix = f"t005-owner-{uuid.uuid4().hex[:10]}"
    (tmp_path / "engine_cache").mkdir()
    (tmp_path / "engine_cache" / "geoip").mkdir()
    adapter = DockerAdapter(
        PathValidator(tmp_path),
        tmp_path / "engine_cache",
        docker_client=client,
        browser_image="sha256:unused-browser",
        stream_image="sha256:unused-stream",
        resource_prefix=prefix,
    )
    name = adapter.get_network_name("profile_a")
    try:
        first = await adapter.create_profile_network("profile_a")
        assert (await adapter.create_profile_network("profile_a")).id == first.id
        adapter.cleanup_network_by_name(name)
        with pytest.raises(docker.errors.NotFound):
            client.networks.get(first.id)
        adapter.cleanup_network_by_name(name)
    finally:
        for network in client.networks.list(
            filters={"label": f"com.cbrowser.prefix={prefix}"}
        ):
            network.remove()
        client.close()

pytestmark = pytest.mark.e2e_images()
