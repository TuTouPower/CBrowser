from __future__ import annotations

import asyncio
import os
import stat
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from gateway_probe.browser_oracle import browser_eval
from gateway_probe.topology import GatewayTopologyHarness
from wait import poll_until

COLOR_A = (0, 51, 0)
COLOR_B = (204, 0, 0)
COLOR_TOLERANCE = 20.0

MARKER_HTML = """<html><head><title>preview-marker</title></head>
<body style="margin:0;background:#003300;width:100vw;height:100vh">
<input id="probe_input" style="display:none">
<div id="marker" style="display:none">PREVIEW_MARKER_40</div>
</body></html>"""

PAGE_STATE = """({
    visibility: document.visibilityState,
    hidden: document.hidden,
    focus: document.hasFocus(),
    marker: document.getElementById('marker')?.textContent ?? null,
    title: document.title
})"""

DECODE_SCRIPT = """
from PIL import Image, ImageStat
im = Image.open('/decode.jpg').convert('RGB')
width, height = im.size
box = (width // 4, height // 4, 3 * width // 4, 3 * height // 4)
mean = ImageStat.Stat(im.crop(box)).mean
print(width, height, round(mean[0], 2), round(mean[1], 2), round(mean[2], 2))
"""


def jpeg_width(data: bytes) -> int:
    offset = 2
    while offset + 9 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            return struct.unpack(">HH", data[offset + 5 : offset + 9])[1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue
        length = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
        offset += 2 + length
    return 0


def decode_center_color(data: bytes) -> tuple[int, tuple[float, float, float]]:
    image = os.environ["CBROWSER_STREAM_TEST_IMAGE"]
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
        handle.write(data)
        source = handle.name
    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "python3",
                "-v",
                f"{source}:/decode.jpg:ro",
                image,
                "-c",
                DECODE_SCRIPT,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        width, _height, red, green, blue = result.stdout.split()
        return int(width), (float(red), float(green), float(blue))
    finally:
        Path(source).unlink(missing_ok=True)


def assert_center_color(data: bytes, expected: tuple[int, int, int]) -> tuple[float, float, float]:
    width, color = decode_center_color(data)
    assert width == 480
    assert jpeg_width(data) == 480
    for channel, value, target in zip("RGB", color, expected):
        assert abs(value - target) <= COLOR_TOLERANCE, (
            f"{channel} channel: {value} vs {target}"
        )
    return color


async def _wait_for_preview(api: httpx.AsyncClient, profile_id: str) -> httpx.Response:
    async def read() -> httpx.Response | None:
        response = await api.get(f"/api/v1/profiles/{profile_id}/preview")
        return response if response.status_code == 200 else None

    return await poll_until(
        read,
        lambda value: value is not None,
        timeout=50.0,
        interval=1.0,
        description="first preview JPEG",
    )


@pytest.mark.asyncio
async def test_profile_preview_capture_and_http_contract(tmp_path: Path) -> None:
    harness = GatewayTopologyHarness(tmp_path)
    try:
        await harness.start()
        profile = await harness.create_and_start_profile("preview_capture")
        profile_id = profile["profile_id"]
        container = profile["browser_container"]
        headers = await harness.login_api()

        async with httpx.AsyncClient(
            base_url=harness.origin,
            headers=headers,
            verify=False,
            trust_env=False,
            timeout=30.0,
        ) as api:
            baseline = await _wait_for_preview(api, profile_id)
            baseline_etag = baseline.headers["etag"]

            first = await asyncio.to_thread(
                browser_eval, container, PAGE_STATE, None, MARKER_HTML
            )
            assert first["value"]["marker"] == "PREVIEW_MARKER_40"
            target_id = first["target_id"]

            async def frame_after_navigate() -> httpx.Response | None:
                result = await api.get(f"/api/v1/profiles/{profile_id}/preview")
                if result.status_code != 200:
                    return None
                return result if result.headers.get("etag") != baseline_etag else None

            response = await poll_until(
                frame_after_navigate,
                lambda value: value is not None,
                timeout=40.0,
                interval=1.0,
                description="preview after navigating to the marker page",
            )
            assert response.headers["content-type"].startswith("image/jpeg")
            assert "no-store" in response.headers["cache-control"]
            etag = response.headers["etag"]
            assert etag
            color_a = assert_center_color(response.content, COLOR_A)

            cached = await api.get(
                f"/api/v1/profiles/{profile_id}/preview",
                headers={"If-None-Match": etag},
            )
            assert cached.status_code == 304

            async def runtime_preview() -> str | None:
                result = await api.get(f"/api/v1/profiles/{profile_id}/runtime")
                if result.status_code != 200:
                    return None
                return result.json().get("preview_captured_at")

            preview_ts = await poll_until(
                runtime_preview,
                lambda value: value is not None,
                timeout=30.0,
                interval=1.0,
                description="runtime preview_captured_at",
            )
            assert preview_ts

            await asyncio.to_thread(
                browser_eval,
                container,
                "document.body.style.background = '#cc0000'; 'recolor'",
                target_id,
            )

            async def recolored() -> httpx.Response | None:
                result = await api.get(f"/api/v1/profiles/{profile_id}/preview")
                if result.status_code != 200:
                    return None
                return result if result.headers.get("etag") != etag else None

            changed = await poll_until(
                recolored,
                lambda value: value is not None,
                timeout=40.0,
                interval=1.0,
                description="preview after active tab recolor",
            )
            color_b = assert_center_color(changed.content, COLOR_B)
            assert color_a != color_b

        async with httpx.AsyncClient(
            base_url=harness.origin, verify=False, trust_env=False, timeout=15.0
        ) as anonymous:
            denied = await anonymous.get(f"/api/v1/profiles/{profile_id}/preview")
            assert denied.status_code in (401, 403)

        image_path = (
            harness.data_dir / "profiles" / profile_id / "preview" / "latest.jpg"
        )
        assert image_path.is_file()
        assert stat.S_IMODE(image_path.stat().st_mode) == 0o600
        meta_path = image_path.parent / "meta.json"
        assert stat.S_IMODE(meta_path.stat().st_mode) == 0o600

        after = await asyncio.to_thread(
            browser_eval, container, PAGE_STATE, target_id
        )
        assert after["value"]["marker"] == "PREVIEW_MARKER_40"
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
