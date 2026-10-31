"""Full-application E2E: real ICE failure diagnostics (AC-007).

Runs a dedicated relay-only topology so that removing coturn leaves no
direct host/srflx path and the page's PeerConnection genuinely reaches the
ICE failed state.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from gateway_probe.evidence import save_evidence
from playwright.async_api import Page, async_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
for p in (str(REPO_ROOT), str(FIXTURES_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from frontend_app_probe.harness import FrontendAppTopologyHarness  # noqa: E402

logger = logging.getLogger("cbrowser.frontend_ice.e2e")


@pytest.fixture(scope="module")
def harness(tmp_path_factory: pytest.TempPathFactory):
    h = FrontendAppTopologyHarness(
        tmp_path_factory.mktemp("fe_ice"), webrtc_mode="relay-only"
    )
    asyncio.run(h.start())
    try:
        yield h
    finally:
        asyncio.run(h.cleanup())


async def ui_login(page: Page, harness: FrontendAppTopologyHarness) -> None:
    await page.goto(f"{harness.origin}/login", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="login-page"]', timeout=15000)
    await page.fill('[data-testid="login-password"]', harness.admin_password)
    await page.click('[data-testid="login-submit"]')
    await page.wait_for_url(re.compile(r"/$"), timeout=20000)


async def create_profile_via_ui(
    page: Page, harness: FrontendAppTopologyHarness, name: str
) -> str:
    await page.goto(f"{harness.origin}/profiles/new", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="profile-new-page"]', timeout=15000)
    await page.fill('[data-testid="profile-name-input"]', name)
    await page.click('[data-testid="profile-create-submit"]')
    await page.wait_for_url(re.compile(r"/\?profileId="), timeout=20000)
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(page.url).query)["profileId"][0]


async def open_session(
    page: Page, harness: FrontendAppTopologyHarness, profile_id: str
) -> None:
    await page.goto(
        f"{harness.origin}/?profileId={profile_id}", wait_until="domcontentloaded"
    )


async def launch_profile_via_ui(page: Page, timeout: float = 120.0) -> None:
    await page.click('[data-testid="session-launch-btn"]', timeout=15000)
    await page.wait_for_selector(
        '[data-testid="header-stop-btn"]', timeout=timeout * 1000
    )


def _save(tmp_path: Path, name: str, payload: Any) -> Path:
    return save_evidence(name, payload, target_dir=tmp_path / "evidence")


@pytest.mark.asyncio
async def test_ac007_ice_failure_stage(
    harness: FrontendAppTopologyHarness, tmp_path: Path
) -> None:
    pw = await async_playwright().start()
    browser = None
    try:
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
        page = await context.new_page()
        await ui_login(page, harness)
        profile_id = await create_profile_via_ui(page, harness, "ICE Failure Profile")
        await open_session(page, harness, profile_id)
        await launch_profile_via_ui(page)
        await harness.wait_runtime(profile_id, desired="running", observed="running")

        console_messages: list[str] = []
        page.on("console", lambda m: console_messages.append(m.text))
        await page.wait_for_selector(
            '[data-testid="browser-session-view"]', timeout=60000
        )

        # Relay-only means coturn is the sole transport. Establish the media
        # path, then pause coturn so ICE consent/connectivity really fails.
        deadline = time.monotonic() + 90
        pc_state: Any = None
        while time.monotonic() < deadline:
            pc_state = await page.evaluate(
                """async () => {
                    const f = document.querySelector(
                        'iframe[data-testid="browser-session-iframe"]');
                    const w = f && f.contentWindow;
                    if (!w || typeof w.__getWebRTCStats !== 'function') return null;
                    const stats = await w.__getWebRTCStats();
                    return stats ? {
                        connected: stats.connected,
                        frames: stats.video ? stats.video.framesDecoded : 0,
                        ice: stats.iceConnectionState,
                    } : null;
                }"""
            )
            if pc_state and pc_state.get("connected") and pc_state.get("frames", 0) > 0:
                break
            await asyncio.sleep(0.3)
        assert pc_state and pc_state.get("connected"), pc_state

        harness.coturn_container.pause()
        try:
            deadline = time.monotonic() + 240
            stage = ""
            title = ""
            debug_state: Any = None
            while time.monotonic() < deadline:
                stage = (
                    await page.locator(
                        '[data-testid="browser-session-view"]'
                    ).get_attribute("data-stage")
                    or ""
                )
                debug_state = await page.evaluate(
                    """() => {
                        const f = document.querySelector(
                            'iframe[data-testid="browser-session-iframe"]');
                        const w = f && f.contentWindow;
                        const pc = w && w.__activePC;
                        return {
                            pc: pc ? pc.connectionState : null,
                            ice: pc ? pc.iceConnectionState : null,
                        };
                    }"""
                )
                if stage == "ice_failed":
                    title = await page.inner_text('[data-testid="session-stage-title"]')
                    break
                await asyncio.sleep(0.5)
            assert stage == "ice_failed", (
                f"stage={stage} debug={debug_state} console={console_messages[-20:]}"
            )
            assert "ICE 协商失败" in title, title
            ice_state = (
                await page.inner_text('[data-testid="diag-ice-state"]')
            ).strip()
            assert ice_state in ("failed", "disconnected"), ice_state
            assert (
                await page.query_selector('[data-testid="session-reconnect-btn"]')
                is not None
            )
            assert (
                await page.query_selector('[data-testid="session-view-status-btn"]')
                is not None
            )
        finally:
            harness.coturn_container.unpause()
        _save(
            tmp_path,
            "ac007_ice_failure",
            {"profile_id": profile_id, "stage_title": title},
        )
    finally:
        if browser is not None:
            await browser.close()
        await pw.stop()
