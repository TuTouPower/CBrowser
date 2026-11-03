"""Display size is controlled by Profile config and explicitly applied on restart.

Covers AC-004 display contract end to end against the production frontend build,
Caddy, API Runtime Coordinator, Supervisor and real Browser/Stream containers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from gateway_probe.browser_oracle import browser_eval
from gateway_probe.evidence import save_evidence
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
BACKEND_DIR = REPO_ROOT / "src" / "backend"
from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT  # noqa: E402
from frontend_app_probe.harness import FrontendAppTopologyHarness  # noqa: E402


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
    await page.goto(f"{harness.origin}/profiles/new", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="profile-new-page"]', timeout=15000)
    await page.fill('[data-testid="profile-name-input"]', name)
    await page.fill('[data-testid="profile-width-input"]', str(width))
    await page.fill('[data-testid="profile-height-input"]', str(height))
    await page.click('[data-testid="profile-create-submit"]')
    await page.wait_for_url(re.compile(r"/\?profileId="), timeout=20000)
    return parse_qs(urlparse(page.url).query)["profileId"][0]


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
async def test_display_profile_size_requires_explicit_apply(
    harness: FrontendAppTopologyHarness, tmp_path: Path
) -> None:
    pw, browser, context = await launch_browser()
    profile_id = ""
    try:
        page = await context.new_page()
        await ui_login(page, harness)
        profile_id = await create_profile_via_ui(
            page, harness, "Display Apply Profile", width=1280, height=720
        )

        await page.goto(
            f"{harness.origin}/?profileId={profile_id}",
            wait_until="domcontentloaded",
        )
        await page.wait_for_selector(
            '[data-testid="session-launch-btn"]', timeout=20000
        )
        await page.click('[data-testid="session-launch-btn"]', timeout=15000)
        await page.wait_for_selector('[data-testid="header-stop-btn"]', timeout=120000)
        await wait_iframe_stats(page)

        assert await wait_video_size(page, [1280, 720]) == [1280, 720]
        browser_container, _ = harness.container_names(profile_id)
        initial_geometry = await remote_geometry(browser_container)
        assert_remote_geometry(initial_geometry, 1280, 720)

        # Change Profile dimensions while running. No restart happens yet.
        await page.goto(
            f"{harness.origin}/profiles/{profile_id}",
            wait_until="domcontentloaded",
        )
        await page.wait_for_selector(
            '[data-testid="profile-detail-page"]', timeout=15000
        )
        await page.fill('[data-testid="profile-width-input"]', "1600")
        await page.fill('[data-testid="profile-height-input"]', "900")
        await page.click('[data-testid="profile-edit-submit"]')
        await page.wait_for_selector(
            '[data-testid="profile-display-pending"]', timeout=20000
        )
        pending_text = await page.inner_text('[data-testid="profile-display-pending"]')
        assert "重启后生效" in pending_text or "restart" in pending_text.lower()

        assert_remote_geometry(await remote_geometry(browser_container), 1280, 720)

        # Session page header also surfaces the pending change; remote stays 1280.
        await page.goto(
            f"{harness.origin}/?profileId={profile_id}",
            wait_until="domcontentloaded",
        )
        await page.wait_for_selector(
            '[data-testid="display-pending-badge"]', timeout=30000
        )
        await wait_iframe_stats(page)
        assert await iframe_video_size(page) == [1280, 720]

        # External viewport resize must never change remote geometry.
        await page.set_viewport_size({"width": 900, "height": 600})
        # Fixed settle window for a negative assertion: remote geometry must
        # stay unchanged after the resize has had time to propagate.
        await asyncio.sleep(1.0)
        assert await iframe_video_size(page) == [1280, 720]
        assert_remote_geometry(await remote_geometry(browser_container), 1280, 720)

        # Explicit apply: stop + start through /api/v1 (Runtime Coordinator).
        await page.click('[data-testid="display-apply-restart-btn"]', timeout=15000)
        await page.wait_for_selector('[data-testid="header-stop-btn"]', timeout=180000)
        runtime = await harness.wait_runtime(
            profile_id, desired="running", observed="running", timeout=180.0
        )
        assert runtime["config_version"] == 2, runtime

        await wait_iframe_stats(page)
        assert await wait_video_size(page, [1600, 900], timeout=120.0) == [1600, 900]
        await page.wait_for_selector(
            '[data-testid="display-pending-badge"]',
            state="detached",
            timeout=30000,
        )

        browser_container, _ = harness.container_names(profile_id)
        new_geometry = await remote_geometry(browser_container)
        assert_remote_geometry(new_geometry, 1600, 900)
        new_stats = await wait_iframe_stats(page)

        _save(
            tmp_path,
            "ac004_display_apply",
            {
                "profile_id": profile_id,
                "initial_geometry": initial_geometry,
                "applied_geometry": new_geometry,
                "video_size": await iframe_video_size(page),
                "frames_decoded": new_stats["video"]["framesDecoded"],
                "runtime_config_version": runtime["config_version"],
            },
        )
    finally:
        if profile_id:
            try:
                async with await harness.api_client() as client:
                    await client.post(f"/api/v1/profiles/{profile_id}/stop")
            except Exception as exc:  # noqa: BLE001 - best-effort profile stop cleanup
                logger.debug("Profile stop cleanup skipped: %s", type(exc).__name__)
        await browser.close()
        await pw.stop()


def test_stream_entrypoint_rejects_missing_supervised_screen_config() -> None:
    image = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    assert image, "CBROWSER_STREAM_TEST_IMAGE is required"

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
