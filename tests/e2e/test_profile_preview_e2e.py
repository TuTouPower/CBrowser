from __future__ import annotations

import asyncio
import io
import json
import stat
import subprocess
import urllib.parse
from pathlib import Path

import httpx
import pytest
from cbrowser.preview import frame_path, read_meta
from gateway_probe.browser_oracle import browser_eval
from gateway_probe.topology import GatewayTopologyHarness
from PIL import Image
from wait import poll_until

MARKER_HTML = """<html><head><title>preview-marker</title></head>
<body style="margin:0;background:white">
<input id="probe_input" style="display:none">
<div id="marker" style="display:none">PREVIEW_MARKER_40</div>
<div style="position:fixed;left:0;top:0;width:50vw;height:100vh;background:black"></div>
</body></html>"""
SECOND_HTML = MARKER_HTML.replace(
    "width:50vw;height:100vh", "width:100vw;height:50vh"
).replace("preview-marker", "second-marker")
PAGE_STATE = """({visibility:document.visibilityState,hidden:document.hidden,
focus:document.hasFocus(),marker:document.getElementById('marker')?.textContent ?? null,
title:document.title,viewport_height:innerHeight})"""


def tab_command(container: str, method: str, params: dict) -> dict:
    script = """import asyncio,json,websockets
from cbrowser.runtime_agent.socket_root import container_agent_socket_path
async def main():
    async with websockets.unix_connect(container_agent_socket_path(), 'ws://localhost/cdp') as ws:
        await ws.send(json.dumps({'id':1,'method':method,'params':params}))
        while True:
            result=json.loads(await asyncio.wait_for(ws.recv(),10))
            if result.get('id')==1:
                assert 'error' not in result, result
                print(json.dumps(result['result']))
                return
asyncio.run(main())
"""
    result = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "python",
            "-c",
            f"method={method!r};params={params!r}\n" + script,
        ],
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def assert_container_frame_validation(container: str) -> None:
    script = """import asyncio,io,tempfile
from pathlib import Path
from PIL import Image
from cbrowser.preview import PreviewPolicy,read_meta,write_policy
from cbrowser.runtime_agent.preview_capture import PreviewCaptureLoop
async def main():
    with tempfile.TemporaryDirectory(prefix='t057-decoder-') as temp:
        directory=Path(temp)
        write_policy(directory,PreviewPolicy(enabled=True,epoch=1,runtime_instance_id='decoder-probe'))
        output=io.BytesIO()
        Image.new('RGB',(480,300),'white').save(output,'JPEG')
        valid=output.getvalue()
        for data in [b'not JPEG',valid[:-20],valid[:-1000]+bytes([255,217])]:
            loop=PreviewCaptureLoop(directory,':99','decoder-probe',capture=lambda _display:(data,(480,300)))
            await loop.capture_once()
            assert read_meta(directory) is None
            assert loop.last_captured_at is None
            assert list(directory.glob('*.jpg'))==[]
        loop=PreviewCaptureLoop(directory,':99','decoder-probe',capture=lambda _display:(valid,(480,300)))
        await loop.capture_once()
        assert read_meta(directory).captured_at==loop.last_captured_at
asyncio.run(main())
"""
    result = subprocess.run(
        ["docker", "exec", container, "python", "-c", script],
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def assert_layout(data: bytes, layout: str, viewport_height: int) -> None:
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        assert image.format == "JPEG"
        assert image.size == (480, 270), "must include full 1920x1080 browser display"
        top = 270 - round(viewport_height * 480 / 1920)
        assert 10 <= top <= 60, "browser tab and address bars must be present"
        # Spatial structure distinguishes the two pages; no mean-color oracle.
        for x, y, dark in [
            (120, top + (270 - top) // 4, True),
            (360, top + (270 - top) // 4, layout == "horizontal"),
            (120, top + 3 * (270 - top) // 4, layout == "vertical"),
            (360, top + 3 * (270 - top) // 4, False),
        ]:
            pixel = image.getpixel((x, y))
            assert max(pixel) < 40 if dark else min(pixel) > 215, (layout, x, y, pixel)
        assert min(image.getpixel((120, 3))) > 40, (
            "page content must not replace browser chrome"
        )


async def _wait_for_preview(api: httpx.AsyncClient, profile_id: str) -> httpx.Response:
    async def read():
        response = await api.get(f"/api/v1/profiles/{profile_id}/preview")
        return response if response.status_code == 200 else None

    return await poll_until(
        read,
        lambda value: value is not None,
        timeout=50.0,
        interval=1.0,
        description="first preview JPEG",
    )


async def wait_for_layout_frame(
    api: httpx.AsyncClient,
    profile_id: str,
    old_etag: str,
    layout: str,
    viewport_height: int,
) -> httpx.Response:
    async def read():
        response = await api.get(f"/api/v1/profiles/{profile_id}/preview")
        return (
            response
            if response.status_code == 200 and response.headers.get("etag") != old_etag
            else None
        )

    def matches(response):
        if response is None:
            return False
        try:
            assert_layout(response.content, layout, viewport_height)
        except AssertionError:
            # Another valid frame may have been captured before tab switch.
            return False
        return True

    return await poll_until(
        read,
        matches,
        timeout=40.0,
        interval=1.0,
        description="new preview with foreground layout",
    )


@pytest.mark.asyncio
async def test_whole_browser_preview_switches_tabs_and_preserves_http_contract(
    tmp_path: Path,
) -> None:
    harness = GatewayTopologyHarness(tmp_path)
    try:
        await harness.start()
        profile = await harness.create_and_start_profile("preview_capture")
        profile_id, container = profile["profile_id"], profile["browser_container"]
        headers = await harness.login_api()
        first = await asyncio.to_thread(
            browser_eval, container, PAGE_STATE, None, MARKER_HTML
        )
        assert first["value"]["marker"] == "PREVIEW_MARKER_40"
        first_id = first["target_id"]
        async with httpx.AsyncClient(
            base_url=harness.origin,
            headers=headers,
            verify=False,
            trust_env=False,
            timeout=30.0,
        ) as api:
            # Ignore an in-flight frame captured before marker navigation.
            baseline = await _wait_for_preview(api, profile_id)
            response = await wait_for_layout_frame(
                api,
                profile_id,
                baseline.headers["etag"],
                "vertical",
                first["value"]["viewport_height"],
            )
            assert_layout(
                response.content, "vertical", first["value"]["viewport_height"]
            )
            assert response.headers["content-type"].startswith("image/jpeg")
            assert "no-store" in response.headers["cache-control"]
            etag = response.headers["etag"]
            cached = await api.get(
                f"/api/v1/profiles/{profile_id}/preview",
                headers={"If-None-Match": etag},
            )
            assert cached.status_code == 304
            runtime = await api.get(f"/api/v1/profiles/{profile_id}/runtime")
            assert runtime.json()["preview_captured_at"]
            second = (
                await asyncio.to_thread(
                    tab_command,
                    container,
                    "Target.createTarget",
                    {"url": "data:text/html," + urllib.parse.quote(SECOND_HTML)},
                )
            )["targetId"]
            await asyncio.to_thread(
                tab_command, container, "Target.activateTarget", {"targetId": second}
            )

            async def second_ready():
                return await asyncio.to_thread(
                    browser_eval, container, PAGE_STATE, second
                )

            second_state = await poll_until(
                second_ready,
                lambda v: v["value"]["marker"] == "PREVIEW_MARKER_40",
                timeout=10,
                interval=0.1,
                description="second tab marker",
            )
            changed = await wait_for_layout_frame(
                api,
                profile_id,
                etag,
                "horizontal",
                second_state["value"]["viewport_height"],
            )
            assert_layout(
                changed.content, "horizontal", second_state["value"]["viewport_height"]
            )
            await asyncio.to_thread(
                tab_command, container, "Target.activateTarget", {"targetId": first_id}
            )
            restored = await wait_for_layout_frame(
                api,
                profile_id,
                changed.headers["etag"],
                "vertical",
                first["value"]["viewport_height"],
            )
            assert_layout(
                restored.content, "vertical", first["value"]["viewport_height"]
            )
        async with httpx.AsyncClient(
            base_url=harness.origin, verify=False, trust_env=False, timeout=15.0
        ) as anonymous:
            assert (
                await anonymous.get(f"/api/v1/profiles/{profile_id}/preview")
            ).status_code in (401, 403)
        await asyncio.to_thread(assert_container_frame_validation, container)
        directory = harness.data_dir / "profiles" / profile_id / "preview"
        assert (
            stat.S_IMODE(frame_path(directory, read_meta(directory)).stat().st_mode)
            == 0o600
        )
        assert stat.S_IMODE((directory / "meta.json").stat().st_mode) == 0o600
    finally:
        await harness.cleanup()


@pytest.mark.asyncio
async def test_profile_preview_revocation_retention_and_page_invariance(
    tmp_path: Path,
) -> None:
    harness = GatewayTopologyHarness(tmp_path)
    try:
        await harness.start()
        profile = await harness.create_and_start_profile("preview_lifecycle")
        profile_id = profile["profile_id"]
        container = profile["browser_container"]
        headers = await harness.login_api()

        first = await asyncio.to_thread(
            browser_eval, container, PAGE_STATE, None, MARKER_HTML
        )
        target_id = first["target_id"]

        async with httpx.AsyncClient(
            base_url=harness.origin,
            headers=headers,
            verify=False,
            trust_env=False,
            timeout=30.0,
        ) as api:
            await _wait_for_preview(api, profile_id)

            before = await asyncio.to_thread(
                browser_eval, container, PAGE_STATE, target_id
            )
            await asyncio.sleep(17.0)
            after = await asyncio.to_thread(
                browser_eval, container, PAGE_STATE, target_id
            )
            for key in ("visibility", "hidden", "focus", "marker", "title"):
                assert after["value"][key] == before["value"][key], key

            disabled = await api.patch(
                f"/api/v1/profiles/{profile_id}",
                json={"capture_preview": False},
            )
            assert disabled.status_code == 200
            revoked = await api.get(f"/api/v1/profiles/{profile_id}/preview")
            assert revoked.status_code == 404

            enabled = await api.patch(
                f"/api/v1/profiles/{profile_id}",
                json={"capture_preview": True},
            )
            assert enabled.status_code == 200
            await _wait_for_preview(api, profile_id)

            stopped = await api.post(f"/api/v1/profiles/{profile_id}/stop")
            assert stopped.status_code in (200, 202)
            kept = await api.get(f"/api/v1/profiles/{profile_id}/preview")
            assert kept.status_code == 200
    finally:
        await harness.cleanup()


pytestmark = pytest.mark.e2e_images(
    "CBROWSER_API_TEST_IMAGE",
    "CBROWSER_CADDY_TEST_IMAGE",
    "CBROWSER_GATEWAY_IMAGE",
    "CBROWSER_RUNTIME_TEST_IMAGE",
    "CBROWSER_STREAM_TEST_IMAGE",
    "CBROWSER_SUPERVISOR_TEST_IMAGE",
)
