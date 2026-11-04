"""Real-stack E2E tests for Frontend Browser Session.

Covers AC-002, AC-003, AC-004, AC-005 and AC-007.

Validates:
- Dual Chrome pages connecting to same profile with distinct client_tab_id
- Refresh preserves tab identity and resume key
- Duplicated tab conflict resolution via Web Locks without kicking the original page
- Closing a page only closes its own connection and never calls profile stop
- Both pages can input independently and have independent audio mute settings
- Page Lifecycle freeze/resume via CDP (Page.setWebLifecycleState)
- Connection diagnostic overlay for unready runtimes without unexplained black screen
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any


import pytest  # noqa: E402
from frontend_probe.harness import FrontendTopologyHarness  # noqa: E402
from gateway_probe.browser_oracle import browser_eval  # noqa: E402
from playwright.async_api import Page, async_playwright  # noqa: E402
from wait import poll_until  # noqa: E402

logger = logging.getLogger("cbrowser.frontend_session.e2e")


async def wait_for_iframe_decode(
    page: Page,
    name: str = "Page",
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Waits until the BrowserSessionView iframe negotiates and decodes video frames."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            stats = await page.evaluate(
                """async () => {
                    const iframe = document.querySelector(
                        'iframe[data-testid="browser-session-iframe"]');
                    if (!iframe || !iframe.contentWindow) return null;
                    const getStats = iframe.contentWindow.__getWebRTCStats;
                    if (typeof getStats !== 'function') return null;
                    return await getStats();
                }"""
            )
            if (
                stats
                and stats.get("video")
                and stats["video"].get("framesDecoded", 0) > 0
                and stats.get("pair")
                and stats["pair"].get("remoteAddress")
            ):
                return stats
        except (TimeoutError, RuntimeError, OSError) as err:
            logger.debug("Transient error while querying stats: %s", err)
        await asyncio.sleep(0.3)

    raise TimeoutError(f"{name} iframe failed to decode video frames within {timeout}s")


async def iframe_eval(page: Page, expression: str) -> Any:
    """Evaluates an expression inside the Selkies iframe document."""
    return await page.evaluate(
        """(expr) => {
            const iframe = document.querySelector(
                'iframe[data-testid="browser-session-iframe"]');
            if (!iframe || !iframe.contentWindow) return null;
            return iframe.contentWindow.eval(expr);
        }""",
        expression,
    )


async def wait_iframe_datachannel_message(
    page: Page, needle: str, timeout: float = 10.0
) -> list[Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    messages: list[Any] = []
    while asyncio.get_running_loop().time() < deadline:
        messages = (
            await iframe_eval(page, "window.__sentDataChannelMessages || []") or []
        )
        if any(isinstance(m, str) and needle in m for m in messages):
            return messages
        await asyncio.sleep(0.1)
    raise AssertionError(f"DataChannel never received {needle}: {messages}")


async def remote_value(container: str, target_id: str | None) -> Any:
    res = await asyncio.to_thread(
        browser_eval,
        container,
        "document.getElementById('probe_input') ? "
        "document.getElementById('probe_input').value : null",
        target_id,
    )
    return res.get("value")


async def get_iframe_webrtc_stats(page: Page) -> dict[str, Any] | None:
    """Retrieves WebRTC stats directly from the Selkies iframe window."""
    return await page.evaluate(
        """async () => {
            const iframe = document.querySelector(
                'iframe[data-testid="browser-session-iframe"]');
            if (!iframe || !iframe.contentWindow) return null;
            const getStats = iframe.contentWindow.__getWebRTCStats;
            if (typeof getStats !== 'function') return null;
            return await getStats();
        }"""
    )


@pytest.mark.asyncio
async def test_frontend_session_dual_tab_identity_refresh_copy_no_kick_and_close(
    tmp_path: Path,
) -> None:
    """AC-002, AC-003: tab identity, refresh, copy conflict and close isolation."""
    harness = FrontendTopologyHarness(tmp_path)
    try:
        await harness.start()

        # 1. Create and start a real profile
        profile = await harness.create_and_start_profile("fe_session_identity_prof")
        profile_id = profile["profile_id"]

        async with async_playwright() as p:
            browser = await p.chromium.launch(
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
            )

            # Login via Page A
            pageA = await context.new_page()
            await pageA.goto(harness.origin, wait_until="domcontentloaded")
            login_resp = await pageA.evaluate(
                """async (password) => {
                    const res = await fetch('/api/v1/auth/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({password})
                    });
                    return res.status;
                }""",
                harness.admin_password,
            )
            assert login_resp == 200, "Login failed"

            # Navigate Page A to profile session
            session_url = f"{harness.origin}/?profileId={profile_id}"
            await pageA.goto(session_url, wait_until="domcontentloaded")
            statsA1 = await wait_for_iframe_decode(pageA, name="Page A")
            tab_id_A = statsA1["tab_id"]
            assert tab_id_A, "Page A must have a client_tab_id"

            # 2. Open Page B on same profile
            pageB = await context.new_page()
            await pageB.goto(session_url, wait_until="domcontentloaded")
            statsB1 = await wait_for_iframe_decode(pageB, name="Page B")
            tab_id_B = statsB1["tab_id"]
            assert tab_id_B, "Page B must have a client_tab_id"

            # AC-002: Both pages must have distinct official client_tab_id
            assert tab_id_A != tab_id_B, (
                f"Tab IDs must be distinct: {tab_id_A} == {tab_id_B}"
            )

            # 3. Test Refresh identity retention (AC-002)
            await pageA.reload(wait_until="domcontentloaded")
            statsA2 = await wait_for_iframe_decode(pageA, name="Page A refreshed")
            tab_id_A_after = statsA2["tab_id"]
            assert tab_id_A_after == tab_id_A, (
                "Reloading page must retain original tab identity: "
                f"{tab_id_A} != {tab_id_A_after}"
            )

            # 4. Test Duplicate tab conflict without kicking original (AC-002)
            # Simulate duplicating tab A: new tab starts with same sessionStorage
            pageC = await context.new_page()
            await pageC.add_init_script(
                f"sessionStorage.setItem('selkies_tab_id', '{tab_id_A}');"
            )
            # Navigate Page C to session url
            await pageC.goto(session_url, wait_until="domcontentloaded")
            statsC = await wait_for_iframe_decode(pageC, name="Page C (duplicate)")
            tab_id_C = statsC["tab_id"]

            # Page C must have detected conflict and remapped to new ID
            assert tab_id_C, "Page C must have a valid tab ID"
            assert tab_id_C != tab_id_A, (
                f"Duplicate tab must remap its tab ID: {tab_id_C} == {tab_id_A}"
            )

            # Page A must still be connected and receiving frames (NOT kicked!)
            statsA3 = await get_iframe_webrtc_stats(pageA)
            assert statsA3 and statsA3.get("connected"), "Page A must remain connected"
            assert (
                statsA3["video"]["framesDecoded"] >= statsA2["video"]["framesDecoded"]
            ), "Page A must not stop receiving frames when a duplicate connects"

            # 5. AC-003: Close Page A and verify runtime is NOT stopped
            await pageA.close()

            # Poll for Page B to remain connected after Page A closes.
            statsB2 = await poll_until(
                lambda: get_iframe_webrtc_stats(pageB),
                lambda stats: bool(stats and stats.get("connected")),
                timeout=5.0,
                interval=0.1,
                description="Page B connected after Page A closes",
            )
            assert statsB2 and statsB2.get("connected"), "Page B must remain connected"

            # Check runtime container status in Supervisor / Docker
            client = harness.docker_client
            browser_box = client.containers.get(profile["browser_container"])
            assert browser_box.status == "running", (
                "Browser container must remain running after closing viewer: "
                f"{browser_box.status}"
            )
            assert (
                browser_box.labels.get("com.cbrowser.instance-id")
                == profile["runtime_instance_id"]
            ), "Browser instance changed after closing viewer"
            stream_box = client.containers.get(profile["stream_container"])
            assert stream_box.status == "running", (
                "Stream container must remain running after closing viewer: "
                f"{stream_box.status}"
            )
            assert (
                stream_box.labels.get("com.cbrowser.instance-id")
                == profile["runtime_instance_id"]
            ), "Stream instance changed after closing viewer"

            await browser.close()
    finally:
        await harness.cleanup()


@pytest.mark.asyncio
async def test_frontend_session_independent_input_and_mute(
    tmp_path: Path,
) -> None:
    """AC-004, AC-005: lease-free input, independent mute, no activity frames."""
    harness = FrontendTopologyHarness(tmp_path)
    try:
        await harness.start()

        profile = await harness.create_and_start_profile("fe_session_input_prof")
        profile_id = profile["profile_id"]

        async with async_playwright() as p:
            browser = await p.chromium.launch(
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
            )

            pageA = await context.new_page()
            await pageA.goto(harness.origin, wait_until="domcontentloaded")
            await pageA.evaluate(
                """async (password) => {
                    await fetch('/api/v1/auth/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({password})
                    });
                }""",
                harness.admin_password,
            )

            session_url = f"{harness.origin}/?profileId={profile_id}"
            await pageA.goto(session_url, wait_until="domcontentloaded")
            await wait_for_iframe_decode(pageA, name="Page A")

            pageB = await context.new_page()
            await pageB.goto(session_url, wait_until="domcontentloaded")
            await wait_for_iframe_decode(pageB, name="Page B")

            # Product mute control in Page A must send STOP_AUDIO only on A's
            # own data channel and must not affect Page B.
            await pageA.click('[data-testid="session-audio-toggle-btn"]')
            messages_a = await wait_iframe_datachannel_message(pageA, "STOP_AUDIO")
            assert "STOP_AUDIO" in messages_a
            muted_a = await iframe_eval(
                pageA,
                """(() => {
                const nodes = [...document.querySelectorAll('audio, video')].filter(
                    (n) => n.srcObject && n.srcObject.getAudioTracks().length > 0);
                return nodes.length > 0 && nodes.every((n) => n.muted);
            })()""",
            )
            assert muted_a is True, "Page A audio element must be muted"
            messages_b = (
                await iframe_eval(pageB, "window.__sentDataChannelMessages || []") or []
            )
            assert not any(
                isinstance(m, str) and m.startswith("STOP_AUDIO") for m in messages_b
            ), "Page B must not receive A's STOP_AUDIO"

            await pageA.click('[data-testid="session-audio-toggle-btn"]')
            messages_a2 = await wait_iframe_datachannel_message(pageA, "START_AUDIO")
            assert "START_AUDIO" in messages_a2

            # Real keyboard input from both pages reaches the remote probe input.
            browser_container = profile["browser_container"]
            remote = await asyncio.to_thread(browser_eval, browser_container, "true")
            target_id = remote["target_id"]
            await asyncio.to_thread(
                browser_eval,
                browser_container,
                """(() => {
                    const input = document.getElementById('probe_input');
                    if (input) { input.value = ''; input.focus(); }
                    return true;
                })()""",
                target_id,
            )
            await iframe_eval(pageA, "document.querySelector('#overlayInput')?.focus()")
            await pageA.keyboard.press("Digit1")
            await iframe_eval(pageB, "document.querySelector('#overlayInput')?.focus()")
            await pageB.keyboard.press("Digit2")
            value = await poll_until(
                lambda: remote_value(browser_container, target_id),
                lambda current: current == "12",
                timeout=6.0,
                interval=0.02,
                description="remote input from both pages",
            )
            assert value == "12", value

            # Verify remote resize is blocked (AC-004)
            blocked_resize = await pageA.evaluate(
                """() => {
                    const iframe = document.querySelector(
                        'iframe[data-testid="browser-session-iframe"]');
                    if (!iframe || !iframe.contentWindow) return false;
                    return iframe.contentWindow.enable_resize === false
                        && iframe.contentWindow.manual_resolution === true;
                }"""
            )
            assert blocked_resize, "Remote resize must be disabled in client adapter"

            await browser.close()
    finally:
        await harness.cleanup()


@pytest.mark.asyncio
async def animate_remote_page(browser_container: str) -> None:
    """Paint continuously in the remote page so damage-gated capture has
    fresh frames after the Page Lifecycle resume."""
    script = """(() => {
        const canvas = document.createElement('canvas');
        canvas.width = 640;
        canvas.height = 480;
        canvas.style.cssText =
            'position:fixed;left:0;top:0;width:640px;height:480px;z-index:2147483647';
        document.body.appendChild(canvas);
        const ctx = canvas.getContext('2d');
        let tick = 0;
        setInterval(() => {
            tick += 1;
            ctx.fillStyle = `hsl(${(tick * 7) % 360}, 80%, 50%)`;
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }, 40);
        return 'animating';
    })()"""
    await asyncio.to_thread(browser_eval, browser_container, script)


async def test_frontend_session_freeze_resume_and_diagnostics(
    tmp_path: Path,
) -> None:
    """AC-007: freeze/resume via CDP and diagnostic overlay for unready profiles."""
    harness = FrontendTopologyHarness(tmp_path)
    try:
        await harness.start()

        profile = await harness.create_and_start_profile("fe_session_lifecycle_prof")
        profile_id = profile["profile_id"]

        async with async_playwright() as p:
            browser = await p.chromium.launch(
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
            )

            pageA = await context.new_page()
            await pageA.goto(harness.origin, wait_until="domcontentloaded")
            await pageA.evaluate(
                """async (password) => {
                    await fetch('/api/v1/auth/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({password})
                    });
                }""",
                harness.admin_password,
            )

            session_url = f"{harness.origin}/?profileId={profile_id}"
            await pageA.goto(session_url, wait_until="domcontentloaded")
            stats_before = await wait_for_iframe_decode(pageA, name="Page A initial")
            tab_id_before = stats_before["tab_id"]

            # Damage-gated capture emits no frames for a static page; paint
            # continuously so the resume assertion measures lifecycle, not
            # an idle screen.
            await animate_remote_page(profile["browser_container"])

            # 1. Page Lifecycle freeze & resume via CDP (AC-007)
            cdp = await context.new_cdp_session(pageA)
            await cdp.send("Page.enable")
            await cdp.send("Page.setWebLifecycleState", {"state": "frozen"})
            # Fixed frozen dwell window: exercise the lifecycle transition.
            # No assertion reads state during this interval.
            await asyncio.sleep(1.5)
            await cdp.send("Page.setWebLifecycleState", {"state": "active"})

            # Wait for frames to advance after reactivation instead of assuming
            # a fixed delay is enough.
            stats_after = await poll_until(
                lambda: get_iframe_webrtc_stats(pageA),
                lambda stats: bool(
                    stats
                    and stats.get("connected")
                    and stats.get("video", {}).get("framesDecoded", 0)
                    > stats_before["video"]["framesDecoded"]
                ),
                timeout=15.0,
                interval=0.2,
                description="frames after Page Lifecycle resume",
            )
            assert stats_after and stats_after.get("connected"), (
                "Page A must remain connected after Page Lifecycle resume"
            )
            assert (
                stats_after["video"]["framesDecoded"]
                > stats_before["video"]["framesDecoded"]
            ), "Frames must grow after Page Lifecycle resume"
            assert stats_after["tab_id"] == tab_id_before, (
                "Page A tab identity must be preserved across lifecycle resume"
            )

            # 2. Diagnostics display for unready / stopped profile (AC-007)
            pageUnready = await context.new_page()
            unready_url = f"{harness.origin}/?profileId=stopped-or-unready-profile-id"
            await pageUnready.goto(unready_url, wait_until="domcontentloaded")

            # The diagnostic overlay must be visible (no unexplained black screen!)
            overlay_visible = await pageUnready.wait_for_selector(
                '[data-testid="session-diagnostics-overlay"]',
                timeout=10000,
            )
            assert overlay_visible, (
                "Diagnostic overlay must be visible for unready profile"
            )

            title_text = await pageUnready.inner_text(
                '[data-testid="session-stage-title"]'
            )
            assert (
                "运行时未就绪" in title_text
                or "信令连接失败" in title_text
                or "检查运行时状态" in title_text
            ), f"Diagnostic title unexpected: {title_text}"

            # Reconnect and status buttons must be present
            reconnect_btn = await pageUnready.query_selector(
                '[data-testid="session-reconnect-btn"]'
            )
            assert reconnect_btn is not None, "Reconnect button must be available"

            status_btn = await pageUnready.query_selector(
                '[data-testid="session-view-status-btn"]'
            )
            assert status_btn is not None, "View status button must be available"

            await browser.close()
    finally:
        await harness.cleanup()
