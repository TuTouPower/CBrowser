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
from collections.abc import Awaitable, Callable
from typing import Any


import httpx  # noqa: E402
import pytest  # noqa: E402
from frontend_probe.harness import FrontendTopologyHarness  # noqa: E402
from gateway_probe.browser_oracle import browser_eval  # noqa: E402
from playwright.async_api import Page, async_playwright  # noqa: E402
from wait import poll_until  # noqa: E402

pytestmark = pytest.mark.serial

logger = logging.getLogger("cbrowser.frontend_session.e2e")


class SharedContainerStack:
    def __init__(
        self,
        harness: Any,
        profiles: dict[str, str] | None = None,
        stop_profile: Callable[[str], Awaitable[None]] | None = None,
        delete_profile: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.harness = harness
        self.profiles = profiles if profiles is not None else {}
        self._stop_profile = stop_profile
        self._delete_profile = delete_profile
        self._started = False
        self._cleaned = False

    async def start(self) -> None:
        if not self._started:
            await self.harness.start()
            self._started = True

    async def cleanup(self) -> None:
        if self._started and not self._cleaned:
            self._cleaned = True
            await self.harness.cleanup()

    def register_profile(self, case_key: str, profile_id: str) -> None:
        self.profiles[case_key] = profile_id

    async def reset_profile_state(
        self,
        case_key: str,
        stop_profile: Callable[[str], Awaitable[None]] | None = None,
        delete_profile: Callable[[str], Awaitable[None]] | None = None,
    ) -> str | None:
        profile_id = self.profiles.get(case_key)
        if profile_id is None:
            return None
        stop = stop_profile if stop_profile is not None else self._stop_profile
        delete = delete_profile if delete_profile is not None else self._delete_profile
        if stop is None or delete is None:
            raise RuntimeError('SharedContainerStack profile actions are not configured')
        await stop(profile_id)
        await delete(profile_id)
        self.profiles.pop(case_key, None)
        return profile_id


def _profile_actions(
    harness: FrontendTopologyHarness,
) -> tuple[
    Callable[[str], Awaitable[None]],
    Callable[[str], Awaitable[None]],
]:
    async def stop_profile(profile_id: str) -> None:
        headers = await harness.login_api()
        async with httpx.AsyncClient(
            base_url=harness.origin,
            headers=headers,
            verify=False,
            trust_env=False,
            timeout=30.0,
        ) as api:
            resp = await api.post(f'/api/v1/profiles/{profile_id}/stop')
            resp.raise_for_status()
            await poll_until(
                lambda: api.get(f'/api/v1/profiles/{profile_id}/runtime'),
                lambda result: (
                    result.status_code == 200
                    and result.json().get('observed_state') == 'stopped'
                    and result.json().get('runtime_instance_id') is None
                ),
                timeout=60.0,
                interval=0.3,
                description=f'profile {profile_id} runtime stopped',
            )

    async def delete_profile(profile_id: str) -> None:
        headers = await harness.login_api()
        async with httpx.AsyncClient(
            base_url=harness.origin,
            headers=headers,
            verify=False,
            trust_env=False,
            timeout=30.0,
        ) as api:
            resp = await api.delete(f'/api/v1/profiles/{profile_id}')
            assert resp.status_code in (200, 204), (
                f'Failed to delete profile {profile_id}: {resp.text}'
            )

    return stop_profile, delete_profile


@pytest.fixture(scope='module')
def shared_stack(tmp_path_factory: pytest.TempPathFactory):
    harness = FrontendTopologyHarness(tmp_path_factory.mktemp('fe_session'))
    stop_profile, delete_profile = _profile_actions(harness)
    stack = SharedContainerStack(
        harness,
        stop_profile=stop_profile,
        delete_profile=delete_profile,
    )
    asyncio.run(stack.start())
    try:
        yield stack
    finally:
        asyncio.run(stack.cleanup())


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
                        'iframe[data-testid="sess-iframe"]');
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
                'iframe[data-testid="sess-iframe"]');
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
                'iframe[data-testid="sess-iframe"]');
            if (!iframe || !iframe.contentWindow) return null;
            const getStats = iframe.contentWindow.__getWebRTCStats;
            if (typeof getStats !== 'function') return null;
            return await getStats();
        }"""
    )


@pytest.mark.asyncio
async def test_frontend_session_dual_tab_identity_refresh_copy_no_kick_and_close(
    shared_stack: SharedContainerStack,
) -> None:
    """AC-002, AC-003: tab identity, refresh, copy conflict and close isolation."""
    harness = shared_stack.harness
    case_key = 'dual_tab_identity'
    try:
        # 1. Create and start a real profile
        profile = await harness.create_and_start_profile("fe_session_identity_prof")
        shared_stack.register_profile(case_key, profile["profile_id"])
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
            session_url = f"{harness.origin}/session/{profile_id}"
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
        await shared_stack.reset_profile_state(case_key)


@pytest.mark.asyncio
async def test_frontend_session_independent_input_and_mute(
    shared_stack: SharedContainerStack,
) -> None:
    """AC-004, AC-005: lease-free input, independent mute, no activity frames."""
    harness = shared_stack.harness
    case_key = 'independent_input_mute'
    try:
        profile = await harness.create_and_start_profile("fe_session_input_prof")
        shared_stack.register_profile(case_key, profile["profile_id"])
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

            session_url = f"{harness.origin}/session/{profile_id}"
            await pageA.goto(session_url, wait_until="domcontentloaded")
            await wait_for_iframe_decode(pageA, name="Page A")

            pageB = await context.new_page()
            await pageB.goto(session_url, wait_until="domcontentloaded")
            await wait_for_iframe_decode(pageB, name="Page B")

            # Product mute control in Page A must send STOP_AUDIO only on A's
            # own data channel and must not affect Page B.
            await pageA.click('[data-testid="sess-audio-toggle"]')
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

            await pageA.click('[data-testid="sess-audio-toggle"]')
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
                        'iframe[data-testid="sess-iframe"]');
                    if (!iframe || !iframe.contentWindow) return false;
                    return iframe.contentWindow.enable_resize === false
                        && iframe.contentWindow.manual_resolution === true;
                }"""
            )
            assert blocked_resize, "Remote resize must be disabled in client adapter"

            await browser.close()
    finally:
        await shared_stack.reset_profile_state(case_key)


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
    shared_stack: SharedContainerStack,
) -> None:
    """AC-007: freeze/resume via CDP and diagnostic overlay for unready profiles."""
    harness = shared_stack.harness
    case_key = 'freeze_resume_diagnostics'
    try:
        profile = await harness.create_and_start_profile("fe_session_lifecycle_prof")
        shared_stack.register_profile(case_key, profile["profile_id"])
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

            session_url = f"{harness.origin}/session/{profile_id}"
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
            unready_url = f"{harness.origin}/session/stopped-or-unready-profile-id"
            await pageUnready.goto(unready_url, wait_until="domcontentloaded")

            # The diagnostic overlay must be visible (no unexplained black screen!)
            overlay_visible = await pageUnready.wait_for_selector(
                '[data-testid="sess-diag-overlay"]',
                timeout=10000,
            )
            assert overlay_visible, (
                "Diagnostic overlay must be visible for unready profile"
            )

            title_text = await pageUnready.inner_text(
                '[data-testid="sess-stage-title"]'
            )
            assert (
                "运行时未就绪" in title_text
                or "信令连接失败" in title_text
                or "检查运行时状态" in title_text
            ), f"Diagnostic title unexpected: {title_text}"

            # Reconnect and status buttons must be present
            reconnect_btn = await pageUnready.query_selector(
                '[data-testid="sess-stage-action-reconnect"]'
            )
            assert reconnect_btn is not None, "Reconnect button must be available"

            status_btn = await pageUnready.query_selector(
                '[data-testid="sess-stage-action-view-status"]'
            )
            assert status_btn is not None, "View status button must be available"

            await browser.close()
    finally:
        await shared_stack.reset_profile_state(case_key)
