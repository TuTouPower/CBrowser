"""Browser egress and Stream media are separate bridges for one Profile."""

import uuid

import docker
import pytest

from e2e_env import require_e2e_env
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathValidator


@pytest.mark.asyncio
async def test_browser_egress_has_its_own_owned_bridge(tmp_path):
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE", "CBROWSER_STREAM_TEST_IMAGE"
    )
    browser_img = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    stream_img = env["CBROWSER_STREAM_TEST_IMAGE"]
    assert browser_img.startswith("sha256:"), (
        "CBROWSER_RUNTIME_TEST_IMAGE must be sha256 immutable digest, "
        f"got {browser_img}"
    )
    assert stream_img.startswith("sha256:"), (
        f"CBROWSER_STREAM_TEST_IMAGE must be sha256 immutable digest, got {stream_img}"
    )

    cache = tmp_path / "engine_cache"
    (cache / "geoip").mkdir(parents=True)
    client = docker.from_env()
    client.images.get(browser_img)
    client.images.get(stream_img)
    prefix = "t005-two-net-" + uuid.uuid4().hex[:10]
    adapter = DockerAdapter(
        PathValidator(tmp_path),
        cache,
        docker_client=client,
        browser_image=browser_img,
        stream_image=stream_img,
        resource_prefix=prefix,
    )
    try:
        media = await adapter.create_profile_network("profile")
        browser = await adapter.create_browser_network("profile")
        assert media.id != browser.id
        assert browser.name == adapter.get_browser_network_name("profile")
        assert (await adapter.create_browser_network("profile")).id == browser.id
        await adapter.teardown_profile("profile")
        for network_id in (media.id, browser.id):
            with pytest.raises(docker.errors.NotFound):
                client.networks.get(network_id)
    finally:
        for network in client.networks.list(
            filters={"label": f"com.cbrowser.prefix={prefix}"}
        ):
            adapter.cleanup_network_by_name(network.name)
        client.close()
