"""Fresh cache initialization must finish in one real helper process."""

import shutil
import uuid
from pathlib import Path

import docker
import pytest

from e2e_env import require_e2e_env
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathValidator


@pytest.mark.asyncio
async def test_fresh_pinned_engine_and_geoip_cache_complete_once(tmp_path):
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        "CBROWSER_RUNTIME_GEOIP_CACHE",
    )
    browser_img = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    stream_img = env["CBROWSER_STREAM_TEST_IMAGE"]
    engine_cache_val = env["CBROWSER_RUNTIME_ENGINE_CACHE"]
    geoip_cache_val = env["CBROWSER_RUNTIME_GEOIP_CACHE"]

    assert browser_img.startswith("sha256:"), (
        "CBROWSER_RUNTIME_TEST_IMAGE must be sha256 immutable digest, "
        f"got {browser_img}"
    )
    assert stream_img.startswith("sha256:"), (
        f"CBROWSER_STREAM_TEST_IMAGE must be sha256 immutable digest, got {stream_img}"
    )
    engine_src = Path(engine_cache_val)
    geoip_src = Path(geoip_cache_val)
    assert engine_src.is_dir(), (
        f"CBROWSER_RUNTIME_ENGINE_CACHE is not a valid directory: {engine_cache_val}"
    )
    assert geoip_src.is_dir(), (
        f"CBROWSER_RUNTIME_GEOIP_CACHE is not a valid directory: {geoip_cache_val}"
    )

    root = tmp_path / "data"
    engine = root / "engine_cache"
    shutil.copytree(engine_src, engine)
    shutil.copytree(geoip_src, engine / "geoip", dirs_exist_ok=True)
    assert not (engine / ".last_update_check").exists()
    client = docker.from_env()
    client.images.get(browser_img)
    client.images.get(stream_img)
    prefix = f"t005-cache-{uuid.uuid4().hex[:12]}"
    try:
        adapter = DockerAdapter(
            PathValidator(root),
            engine,
            docker_client=client,
            resource_prefix=prefix,
            browser_image=browser_img,
            stream_image=stream_img,
        )
        await adapter.ensure_runtime_cache(need_geoip=True)
        assert list((engine / "geoip").glob("*.mmdb"))
        assert not list(engine.glob("cache_init_*.json"))
        assert not client.containers.list(
            all=True, filters={"label": f"com.cbrowser.prefix={prefix}"}
        )
        # The pinned SDK branch must not launch its binary updater.
        assert not (engine / ".last_update_check").exists()
        await adapter.ensure_runtime_cache(need_geoip=True)
    finally:
        for container in client.containers.list(
            all=True, filters={"label": f"com.cbrowser.prefix={prefix}"}
        ):
            container.remove(force=True)
        client.close()

pytestmark = pytest.mark.e2e_images('CBROWSER_RUNTIME_TEST_IMAGE', 'CBROWSER_STREAM_TEST_IMAGE')
