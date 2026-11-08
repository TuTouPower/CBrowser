"""Display size is controlled by Profile config and explicitly applied on restart.

Covers AC-004 display contract end to end against the production frontend build,
Caddy, API Runtime Coordinator, Supervisor and real Browser/Stream containers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from e2e_env import require_e2e_env
from gateway_probe.browser_oracle import browser_eval
from gateway_probe.evidence import save_evidence
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT  # noqa: E402
from frontend_app_probe.harness import FrontendAppTopologyHarness  # noqa: E402

pytestmark = pytest.mark.serial


@pytest.fixture(scope="module")
def harness(tmp_path_factory: pytest.TempPathFactory):
    h = FrontendAppTopologyHarness(
        tmp_path_factory.mktemp("fe_display")
    )
    asyncio.run(h.start())
    try:
        yield h
    finally:
        asyncio.run(h.cleanup())


def _save(tmp_path: Path, name: str, payload: Any) -> Path:
    return save_evidence(name, payload, target_dir=tmp_path / "evidence")


async def launch_browser() -> tuple[Any, Browser, BrowserContext]:
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        channel="chrome",
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--ignore-certificate-errors",
            "--autoplay-policy=no-user-gesture-required",
        ],
    )
    context = await browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1280, "height": 720},
        locale="zh-CN",
    )
    return pw, browser, context


async def ui_login(page: Page, harness: FrontendAppTopologyHarness) -> None:
    await page.goto(f"{harness.origin}/login", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="login-page"]', timeout=15000)
    await page.fill('[data-testid="login-password"]', harness.admin_password)
    await page.click('[data-testid="login-submit"]')
    await page.wait_for_url(re.compile(r"/$"), timeout=20000)


async def create_profile_via_ui(
    page: Page,
    harness: FrontendAppTopologyHarness,
    name: str,
    width: int,
    height: int,
) -> str:
    del page
    async with await harness.api_client() as client:
        resp = await client.post(
            "/api/v1/profiles",
            json={"name": name, "screen_width": width, "screen_height": height},
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def wait_iframe_stats(
    page: Page,
    *,
    timeout: float = 90.0,
    min_frames: int = 1,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = await page.evaluate(
                """async () => {
                    const SEL = 'iframe[data-testid="browser-session-iframe"]';
                    const f = document.querySelector(SEL);
                    if (!f || !f.contentWindow) return null;
                    const fn = f.contentWindow.__getWebRTCStats;
                    if (typeof fn !== 'function') return null;
                    return await fn();
                }"""
            )
        except Exception as exc:  # noqa: BLE001 - page navigating / iframe swapped
            last = {"error": type(exc).__name__}
        if (
            last
            and last.get("video")
            and last["video"].get("framesDecoded", 0) >= min_frames
            and last.get("connected")
        ):
            return last
        await asyncio.sleep(0.3)
    raise TimeoutError(f"iframe did not decode frames: {json.dumps(last)[:800]}")


async def iframe_video_size(page: Page) -> list[int] | None:
    return await page.evaluate(
        """() => {
            const SEL = 'iframe[data-testid="browser-session-iframe"]';
            const f = document.querySelector(SEL);
            if (!f || !f.contentWindow) return null;
            const v = f.contentWindow.document.querySelector('video');
            return v ? [v.videoWidth, v.videoHeight] : null;
        }"""
    )


async def wait_video_size(
    page: Page, expected: list[int], timeout: float = 120.0
) -> list[int]:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = await iframe_video_size(page)
        if last == expected:
            return last
        await asyncio.sleep(0.3)
    raise TimeoutError(f"video size never became {expected}: {last}")


async def remote_geometry(container: str) -> list[int]:
    result = await asyncio.to_thread(
        browser_eval,
        container,
        "(() => [window.outerWidth, screen.width, screen.height])()",
    )
    return result["value"]


def assert_remote_geometry(geometry: list[int], width: int, height: int) -> None:
    # Chrome outerHeight is reduced by the openbox title bar; the X screen and
    # outer width prove the remote display geometry.
    assert geometry == [width, width, height], geometry


@pytest.mark.asyncio
def test_stream_entrypoint_rejects_missing_supervised_screen_config() -> None:
    image = require_e2e_env("CBROWSER_STREAM_TEST_IMAGE")[
        "CBROWSER_STREAM_TEST_IMAGE"
    ]

    env = {
        "CBROWSER_PROFILE_ID": "display_probe",
        "CBROWSER_RUNTIME_INSTANCE_ID": "inst_display_probe",
        "CBROWSER_GATEWAY_URL": f"ws://127.0.0.1:{DEFAULT_GATEWAY_PORT}",
        "CBROWSER_CONFIG_VERSION": "1",
        "CBROWSER_WEBRTC_PUBLIC_IP": "127.0.0.1",
        "CBROWSER_AGENT_TOKEN": secrets.token_urlsafe(32),
        "CBROWSER_SELKIES_CREDENTIALS_FILE": "/tmp/missing_credentials.json",
    }
    command = ["docker", "run", "--rm", "--name", "t007-display-config-probe"]
    for key, value in env.items():
        command.extend(["-e", f"{key}={value}"])
    command.append(image)

    result = subprocess.run(
        command, capture_output=True, text=True, timeout=120, check=False
    )
    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0, output
    assert "CONFIG_ERROR" in output and "CBROWSER_SCREEN_WIDTH" in output, output
