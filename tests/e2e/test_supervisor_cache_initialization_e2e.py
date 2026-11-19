"""Fresh cache initialization must finish in one real helper process."""

import uuid
from pathlib import Path

import docker
import pytest

from e2e_env import require_e2e_env
from e2e_volumes import init_prefix_volumes, remove_prefix_volumes, run_volume_json

pytestmark = [
    pytest.mark.e2e_images(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_SUPERVISOR_TEST_IMAGE",
    )
]

_CACHE_INIT_DRIVER = """
import asyncio
import json
import os
from pathlib import Path

import docker
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathValidator


async def main() -> None:
    root = Path("/data")
    engine = root / "engine-cache"
    assert not (engine / ".last_update_check").exists()
    client = docker.from_env()
    try:
        adapter = DockerAdapter(
            PathValidator(root),
            engine,
            docker_client=client,
            resource_prefix=os.environ["CB_TEST_PREFIX"],
            browser_image=os.environ["CB_TEST_BROWSER_IMAGE"],
            stream_image=os.environ["CB_TEST_STREAM_IMAGE"],
        )
        await adapter.ensure_runtime_cache(need_geoip=True)
        mmdb = [p.name for p in (engine / "geoip").glob("*.mmdb")]
        markers = [p.name for p in engine.glob("cache_init_*.json")]
        leftovers = [
            c.name
            for c in client.containers.list(
                all=True,
                filters={"label": f"com.cbrowser.prefix={os.environ['CB_TEST_PREFIX']}"},
            )
            if c.labels.get("com.cbrowser.role") != "e2e-driver"
        ]
        last_update = (engine / ".last_update_check").exists()
        await adapter.ensure_runtime_cache(need_geoip=True)
        print(
            "CBROWSER_E2E_RESULT="
            + json.dumps(
                {
                    "mmdb": mmdb,
                    "markers": markers,
                    "leftovers": leftovers,
                    "last_update": last_update,
                }
            )
        )
    finally:
        client.close()


asyncio.run(main())
"""


@pytest.mark.asyncio
async def test_fresh_pinned_engine_and_geoip_cache_complete_once() -> None:
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_SUPERVISOR_TEST_IMAGE",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        "CBROWSER_RUNTIME_GEOIP_CACHE",
    )
    browser_img = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    stream_img = env["CBROWSER_STREAM_TEST_IMAGE"]
    supervisor_img = env["CBROWSER_SUPERVISOR_TEST_IMAGE"]
    engine_cache_val = env["CBROWSER_RUNTIME_ENGINE_CACHE"]
    geoip_cache_val = env["CBROWSER_RUNTIME_GEOIP_CACHE"]

    for var_name, val in (
        ("CBROWSER_RUNTIME_TEST_IMAGE", browser_img),
        ("CBROWSER_STREAM_TEST_IMAGE", stream_img),
        ("CBROWSER_SUPERVISOR_TEST_IMAGE", supervisor_img),
    ):
        assert val.startswith("sha256:"), (
            f"{var_name} must be sha256 immutable digest, got {val}"
        )
    engine_src = Path(engine_cache_val)
    geoip_src = Path(geoip_cache_val)
    assert engine_src.is_dir(), (
        f"CBROWSER_RUNTIME_ENGINE_CACHE is not a valid directory: {engine_cache_val}"
    )
    assert geoip_src.is_dir(), (
        f"CBROWSER_RUNTIME_GEOIP_CACHE is not a valid directory: {geoip_cache_val}"
    )

    client = docker.from_env()
    client.images.get(browser_img)
    client.images.get(stream_img)
    client.images.get(supervisor_img)
    prefix = f"t005-cache-{uuid.uuid4().hex[:12]}"
    try:
        init_prefix_volumes(
            client,
            prefix,
            supervisor_img,
            roles=("data", "runtime", "fonts"),
            engine_cache_src=engine_src,
            geoip_cache_src=geoip_src,
        )
        result = run_volume_json(
            client,
            prefix,
            supervisor_img,
            _CACHE_INIT_DRIVER,
            roles=("data", "runtime", "fonts"),
            mount_docker_sock=True,
            env={
                "CB_TEST_PREFIX": prefix,
                "CB_TEST_BROWSER_IMAGE": browser_img,
                "CB_TEST_STREAM_IMAGE": stream_img,
            },
        )
        assert result["mmdb"]
        assert not result["markers"]
        assert not result["leftovers"]
        assert not result["last_update"]
    finally:
        for container in client.containers.list(
            all=True, filters={"label": f"com.cbrowser.prefix={prefix}"}
        ):
            container.remove(force=True)
        remove_prefix_volumes(client, prefix)
        client.close()
