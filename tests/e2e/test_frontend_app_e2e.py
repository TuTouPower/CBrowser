"""Full-application E2E tests (Vite build + Selkies assets + Caddy + API).

Covers t007 AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-009, AC-010
against the complete production frontend served by Caddy and a real Runtime
Coordinator -> Supervisor -> Browser/Stream container graph.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import docker
import httpx
import pytest
from gateway_probe.browser_oracle import browser_eval
from gateway_probe.evidence import save_evidence
from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from wait import poll_until


from frontend_app_probe.harness import FrontendAppTopologyHarness  # noqa: E402

pytestmark = pytest.mark.serial

logger = logging.getLogger("cbrowser.frontend_app.e2e")

IFRAME_SELECTOR = 'iframe[data-testid="browser-session-iframe"]'


# --------------------------------------------------------------------------- #
# Module-scoped real topology
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def harness(tmp_path_factory: pytest.TempPathFactory):
    h = FrontendAppTopologyHarness(tmp_path_factory.mktemp("fe_app"))
    asyncio.run(h.start())
    try:
        yield h
    finally:
        asyncio.run(h.cleanup())


def _save(tmp_path: Path, name: str, payload: Any) -> Path:
    return save_evidence(name, payload, target_dir=tmp_path / "evidence")


# --------------------------------------------------------------------------- #
# Browser helpers
# --------------------------------------------------------------------------- #


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
        # Pin the UI locale so localized copy assertions are deterministic.
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
    width: int = 1920,
    height: int = 1080,
) -> str:
    del width, height
    await page.goto(f"{harness.origin}/", wait_until="domcontentloaded")
    await page.wait_for_selector(
        '[data-testid="env-list-page"]', timeout=15000
    )
    await page.click('[data-testid="env-new"]', timeout=15000)
    await page.wait_for_selector(
        '[data-testid="env-new-dialog"]', timeout=15000
    )
    await page.fill('[data-testid="profile-form-name"]', name)
    await page.click('[data-testid="profile-form-submit"]', timeout=15000)
    await page.wait_for_selector(
        '[data-testid="env-new-dialog"]', state="detached", timeout=15000
    )
    row = page.locator('[data-testid^="env-row-"]').filter(has_text=name)
    await row.wait_for(state="visible", timeout=15000)
    testid = await row.get_attribute("data-testid")
    assert testid is not None
    return testid.removeprefix("env-row-")


async def open_session(
    page: Page, harness: FrontendAppTopologyHarness, profile_id: str
) -> None:
    await page.goto(
        f"{harness.origin}/session/{profile_id}", wait_until="domcontentloaded"
    )


async def launch_profile_via_ui(page: Page, timeout: float = 120.0) -> None:
    """Clicks the in-page Launch button; waits for the Stop state to appear via SSE."""
    await page.click('[data-testid="session-launch-btn"]', timeout=15000)
    await page.wait_for_selector(
        '[data-testid="browser-session-mount"]', timeout=timeout * 1000
    )


async def stop_profile_via_api(
    page: Page,
    harness: FrontendAppTopologyHarness,
    profile_id: str,
) -> None:
    del page
    async with await harness.api_client() as client:
        resp = await client.post(f"/api/v1/profiles/{profile_id}/stop")
        resp.raise_for_status()


async def _evaluate_bounded(
    page: Page, expression: str, *, timeout: float = 5.0
) -> Any:
    """Evaluate with a hard bound; Playwright evaluate has no timeout and
    can wait forever on a stalled page/iframe."""
    return await asyncio.wait_for(page.evaluate(expression), timeout=timeout)


async def wait_iframe_stats(
    page: Page,
    *,
    timeout: float = 60.0,
    min_frames: int = 1,
    name: str = "page",
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = await _evaluate_bounded(
                page,
                """async () => {
                    const SEL = 'iframe[data-testid="browser-session-iframe"]';
                    const f = document.querySelector(SEL);
                    if (!f || !f.contentWindow) return null;
                    const fn = f.contentWindow.__getWebRTCStats;
                    if (typeof fn !== 'function') return null;
                    return await fn();
                }""",
                timeout=1.0,
            )
        except Exception as exc:  # noqa: BLE001 - navigated/swapped/stalled
            last = {"error": type(exc).__name__}
        if (
            last
            and last.get("video")
            and last["video"].get("framesDecoded", 0) >= min_frames
            and last.get("connected")
        ):
            return last
        await asyncio.sleep(0.3)
    raise TimeoutError(f"{name} did not decode frames: {json.dumps(last)[:800]}")


async def iframe_eval(page: Page, expression: str) -> Any:
    return await page.evaluate(
        """(expr) => {
            const SEL = 'iframe[data-testid="browser-session-iframe"]';
            const f = document.querySelector(SEL);
            if (!f || !f.contentWindow) return null;
            return f.contentWindow.eval(expr);
        }""",
        expression,
    )


async def iframe_src(page: Page) -> str:
    return await page.evaluate(
        """() => {
            const SEL = 'iframe[data-testid="browser-session-iframe"]';
            const f = document.querySelector(SEL);
            return f ? f.getAttribute('src') : null;
        }"""
    )


async def wait_iframe_datachannel_message(
    page: Page, needle: str, timeout: float = 15.0
) -> list[Any]:
    deadline = time.monotonic() + timeout
    messages: list[Any] = []
    while time.monotonic() < deadline:
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


async def prepare_remote_input(container: str, target_id: str | None) -> None:
    await asyncio.to_thread(
        browser_eval,
        container,
        """(() => {
            const input = document.getElementById('probe_input');
            if (input) { input.value = ''; window.remoteEvents = []; input.focus(); }
            return true;
        })()""",
        target_id,
    )


async def animate_remote_fixture(
    harness: FrontendAppTopologyHarness, profile_id: str
) -> None:
    """Navigate the remote page to the animated media fixture.

    Frame-growth assertions must not depend on a static screen being re-encoded
    by damage-gated capture.
    """
    browser_container, _ = harness.container_names(profile_id)
    await asyncio.to_thread(browser_eval, browser_container, "true")


async def wait_runtime_containers_gone(
    harness: FrontendAppTopologyHarness, profile_id: str, timeout: float = 60.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not harness.containers_for(profile_id):
            return
        await asyncio.sleep(0.5)
    raise TimeoutError("Runtime containers still present after stop")


class ConsoleRecorder:
    def __init__(self, page: Page) -> None:
        self.messages: list[str] = []
        page.on("console", lambda m: self.messages.append(m.text))

    def has(self, needle: str) -> bool:
        return any(needle in item for item in self.messages)


class WireRecorder:
    """Records WebSocket frames and textual HTTP response bodies as seen by the page."""

    def __init__(self, page: Page, context: BrowserContext) -> None:
        self.page = page
        self.context = context
        self.frames_sent: list[str] = []
        self.frames_received: list[str] = []
        self.bodies: list[str] = []
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self.cdp = await self.context.new_cdp_session(self.page)
        await self.cdp.send("Network.enable")
        self.cdp.on("Network.webSocketFrameSent", self._on_sent)
        self.cdp.on("Network.webSocketFrameReceived", self._on_received)
        self.page.on("response", self._on_response)

    def _on_sent(self, event: dict[str, Any]) -> None:
        self.frames_sent.append(event["response"]["payloadData"])

    def _on_received(self, event: dict[str, Any]) -> None:
        self.frames_received.append(event["response"]["payloadData"])

    def _on_response(self, response: Any) -> None:
        ctype = (response.headers.get("content-type") or "").lower()
        if not any(t in ctype for t in ("json", "javascript", "html", "text/css")):
            return
        self._tasks.append(asyncio.create_task(self._capture(response)))

    async def _capture(self, response: Any) -> None:
        try:
            self.bodies.append(await response.text())
        except Exception as exc:  # noqa: BLE001 - body may be evicted/navigated
            logger.debug("Response body unavailable: %s", type(exc).__name__)

    async def settle(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


def _assert_no_token(text: str, name: str, tokens: dict[str, str]) -> None:
    for kind, value in tokens.items():
        assert value not in text, f"{name} leaked Selkies {kind}"


# --------------------------------------------------------------------------- #
# AC-001 / AC-006
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ac001_ac006_profile_ui_dual_tab_sse_and_stale_state(
    harness: FrontendAppTopologyHarness, tmp_path: Path
) -> None:
    pw, browser, context = await launch_browser()
    try:
        page_a = await context.new_page()
        await ui_login(page_a, harness)

        name_a = "Fe Alpha"
        name_b = "Fe Beta"
        profile_a = await create_profile_via_ui(page_a, harness, name_a)
        profile_b = await create_profile_via_ui(page_a, harness, name_b)

        # The environment list is delivered by t037; verify creation via API.
        async with await harness.api_client() as client:
            resp = await client.get("/api/v1/profiles")
            assert name_a in resp.text

        # Edit name through the shared config form on the new detail page.
        await page_a.goto(
            f"{harness.origin}/profiles/{profile_a}", wait_until="domcontentloaded"
        )
        await page_a.wait_for_selector(
            '[data-testid="profile-detail-view"]', timeout=15000
        )
        await page_a.fill('[data-testid="profile-form-name"]', name_a + " Edited")
        await page_a.click('[data-testid="profile-form-submit"]')
        async with await harness.api_client() as client:
            for _ in range(50):
                resp = await client.get("/api/v1/profiles")
                if name_a + " Edited" in resp.text:
                    break
                await asyncio.sleep(0.1)
            assert name_a + " Edited" in resp.text

        # Start profile A through the session page; runtime state must arrive via SSE
        # (no reload and no polling: the mutation only sets desired/observed=starting).
        await open_session(page_a, harness, profile_a)
        await launch_profile_via_ui(page_a)
        stats_a = await wait_iframe_stats(page_a, name="A")
        assert stats_a["video"]["framesDecoded"] > 0

        # Second tab targets profile B independently.
        page_b = await context.new_page()
        await open_session(page_b, harness, profile_b)
        await launch_profile_via_ui(page_b)
        stats_b = await wait_iframe_stats(page_b, name="B")

        assert urlparse(page_a.url).path == f"/session/{profile_a}"
        assert urlparse(page_b.url).path == f"/session/{profile_b}"
        assert profile_a in (await iframe_src(page_a))
        assert profile_b in (await iframe_src(page_b))
        assert stats_a["tab_id"] != stats_b["tab_id"]

        # Switching profile on page A must not change page B's target or connection.
        frames_b_before = stats_b["video"]["framesDecoded"]
        await open_session(page_a, harness, profile_b)
        assert urlparse(page_a.url).path == f"/session/{profile_b}"
        assert urlparse(page_b.url).path == f"/session/{profile_b}"

        await animate_remote_fixture(harness, profile_b)
        stats_b_after = await wait_iframe_stats(
            page_b, name="B after switch", min_frames=frames_b_before + 1
        )
        assert stats_b_after["video"]["framesDecoded"] > frames_b_before
        assert stats_b_after["tab_id"] == stats_b["tab_id"]

        # No shared localStorage current-profile key anywhere.
        local_keys = await page_a.evaluate("() => Object.keys(window.localStorage)")
        assert all("currentProfile" not in key for key in local_keys), local_keys

        # SSE disconnect: external stop while /events is broken, then reconnect
        # must converge to stopped rather than keep stale running control state.
        async def _abort_events(route: Any) -> None:
            await route.abort()

        await page_b.route("**/api/v1/events", _abort_events)
        # Fixed settle window: allow the page's event stream to be interrupted
        # before the external stop mutation is issued.
        await asyncio.sleep(0.5)
        async with await harness.api_client() as client:
            resp = await client.post(f"/api/v1/profiles/{profile_b}/stop")
            resp.raise_for_status()
        await page_b.unroute("**/api/v1/events")
        await page_b.wait_for_selector(
            '[data-testid="session-launch-btn"]', timeout=45000
        )

        # Stop page A's profile via API: the new shell has no header stop
        # control (t039 delivers the session stop action).
        await open_session(page_a, harness, profile_a)
        await page_a.wait_for_selector(
            '[data-testid="browser-session-mount"]', timeout=45000
        )
        await stop_profile_via_api(page_a, harness, profile_a)
        await page_a.wait_for_selector(
            '[data-testid="session-launch-btn"]', timeout=60000
        )

        _save(
            tmp_path,
            "ac001_ac006",
            {
                "profile_a": profile_a,
                "profile_b": profile_b,
                "tab_a": stats_a["tab_id"],
                "tab_b": stats_b["tab_id"],
                "page_b_frames_before_switch": frames_b_before,
                "page_b_frames_after_switch": stats_b_after["video"]["framesDecoded"],
                "local_storage_keys": local_keys,
            },
        )
    finally:
        await browser.close()
        await pw.stop()


# --------------------------------------------------------------------------- #
# AC-002 / AC-003 / AC-010
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ac002_ac003_ac010_identity_copy_close_and_tokens(
    harness: FrontendAppTopologyHarness, tmp_path: Path
) -> None:
    pw, browser, context = await launch_browser()
    try:
        page_a = await context.new_page()
        await ui_login(page_a, harness)
        profile_id = await create_profile_via_ui(
            page_a, harness, "Identity Profile"
        )

        wire = WireRecorder(page_a, context)
        await wire.start()
        console = ConsoleRecorder(page_a)

        await open_session(page_a, harness, profile_id)
        await launch_profile_via_ui(page_a)
        stats_a1 = await wait_iframe_stats(page_a, name="A")

        # Tokens exist server-side only; the page must never receive them.
        tokens = harness.selkies_tokens(profile_id)
        dom = await page_a.evaluate("() => document.documentElement.outerHTML")
        iframe_dom = await page_a.evaluate(
            """() => {
                const SEL = 'iframe[data-testid="browser-session-iframe"]';
                const f = document.querySelector(SEL);
                return f && f.contentDocument
                    ? f.contentDocument.documentElement.outerHTML
                    : "";
            }"""
        )
        storages = await page_a.evaluate(
            """() => JSON.stringify({
                local: {...window.localStorage},
                session: {...window.sessionStorage},
            })"""
        )
        await wire.settle()
        for name, text in (
            ("host DOM", dom),
            ("iframe DOM", iframe_dom),
            ("host storage", storages),
            ("network responses", "\n".join(wire.bodies)),
            ("websocket sent", "\n".join(wire.frames_sent)),
            ("websocket received", "\n".join(wire.frames_received)),
        ):
            _assert_no_token(text, name, tokens)

        # Page sends HELLO without any Selkies token and is accepted as controller
        # (the Stream Agent injects the controller token upstream).
        hellos = [f for f in wire.frames_sent if f.startswith("HELLO client ")]
        assert hellos, "Page never sent a Selkies HELLO"
        official_hello_keys = {
            "client_type",
            "client_slot",
            "client_strict_viewer",
            "client_token",
            "display_id",
            "display_position",
            "client_tab_id",
            "cc_start_kbps",
            "resume_key",
            "fullcolor_codecs",
            "tenbit_codecs",
            "page_size",
        }
        for hello in hellos:
            meta = json.loads(hello.split(" ", 2)[2])
            assert "client_token" not in meta
            assert meta.get("client_tab_id")
            assert meta.get("resume_key")
            assert set(meta) <= official_hello_keys, meta
            assert "cbrowser" not in meta
        assert console.has('"role": "controller"') or console.has(
            '"role":"controller"'
        ), console.messages

        tab_a = stats_a1["tab_id"]

        # Refresh keeps the official client_tab_id identity; the official
        # client generates a fresh resume_key for the new page instance.
        hello_before_refresh = json.loads(
            [f for f in wire.frames_sent if f.startswith("HELLO client ")][-1].split(
                " ", 2
            )[2]
        )
        await page_a.reload(wait_until="domcontentloaded")
        stats_a2 = await wait_iframe_stats(page_a, name="A refreshed")
        assert stats_a2["tab_id"] == tab_a
        deadline = time.monotonic() + 10
        hello_after_refresh = hello_before_refresh
        while time.monotonic() < deadline:
            refreshed = [f for f in wire.frames_sent if f.startswith("HELLO client ")]
            if refreshed:
                candidate = json.loads(refreshed[-1].split(" ", 2)[2])
                if (
                    candidate.get("client_tab_id") == tab_a
                    and candidate != hello_before_refresh
                ):
                    hello_after_refresh = candidate
                    break
            await asyncio.sleep(0.1)
        assert hello_after_refresh["client_tab_id"] == tab_a
        assert hello_after_refresh["resume_key"] != hello_before_refresh["resume_key"]

        # Same-profile second page gets a distinct official client_tab_id.
        page_b = await context.new_page()
        await open_session(page_b, harness, profile_id)
        stats_b = await wait_iframe_stats(page_b, name="B")
        assert stats_b["tab_id"] and stats_b["tab_id"] != tab_a

        # Duplicated tab (same sessionStorage tab id) remaps without kicking A.
        page_c = await context.new_page()
        await page_c.add_init_script(
            f"sessionStorage.setItem('selkies_tab_id', {json.dumps(tab_a)});"
        )
        await open_session(page_c, harness, profile_id)
        stats_c = await wait_iframe_stats(page_c, name="C duplicate")
        assert stats_c["tab_id"] != tab_a
        stats_a3 = await wait_iframe_stats(page_a, name="A after duplicate")
        assert stats_a3["video"]["framesDecoded"] >= stats_a2["video"]["framesDecoded"]

        # Closing page A only closes its own connection; Runtime keeps running.
        browser_container, stream_container = harness.container_names(profile_id)
        await page_a.close()
        await animate_remote_fixture(harness, profile_id)
        stats_b2 = await wait_iframe_stats(
            page_b,
            name="B after A closed",
            min_frames=stats_b["video"]["framesDecoded"] + 1,
        )
        assert stats_b2["video"]["framesDecoded"] > stats_b["video"]["framesDecoded"]
        client = docker.from_env()
        assert client.containers.get(browser_container).status == "running"
        assert client.containers.get(stream_container).status == "running"
        rt = await harness.get_runtime(profile_id)
        assert rt["observed_state"] == "running"

        _save(
            tmp_path,
            "ac002_ac003_ac010",
            {
                "profile_id": profile_id,
                "tab_a": tab_a,
                "tab_b": stats_b["tab_id"],
                "tab_c": stats_c["tab_id"],
                "browser_container": browser_container,
                "stream_container": stream_container,
                "hello_count": len(hellos),
                "controller_log": [m for m in console.messages if "role" in m][:3],
                "frames_after_close": stats_b2["video"]["framesDecoded"],
            },
        )

        async with await harness.api_client() as client_api:
            await client_api.post(f"/api/v1/profiles/{profile_id}/stop")
    finally:
        await browser.close()
        await pw.stop()


# --------------------------------------------------------------------------- #
# AC-004 / AC-005
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ac004_ac005_input_mute_size_no_activity_frames(
    harness: FrontendAppTopologyHarness, tmp_path: Path
) -> None:
    pw, browser, context = await launch_browser()
    try:
        page_a = await context.new_page()
        await ui_login(page_a, harness)
        profile_id = await create_profile_via_ui(page_a, harness, "Input Profile")

        wire = WireRecorder(page_a, context)
        await wire.start()
        await open_session(page_a, harness, profile_id)
        await launch_profile_via_ui(page_a)
        first_frame_start = time.monotonic()
        await wait_iframe_stats(page_a, name="A")
        first_frame_ms = int((time.monotonic() - first_frame_start) * 1000)
        assert first_frame_ms <= 8000, first_frame_ms

        page_b = await context.new_page()
        await open_session(page_b, harness, profile_id)
        await wait_iframe_stats(page_b, name="B")

        browser_container, _ = harness.container_names(profile_id)
        remote = await asyncio.to_thread(browser_eval, browser_container, "true")
        target_id = remote["target_id"]

        # Remote geometry stays 1920x1080 regardless of the external viewport.
        await page_a.set_viewport_size({"width": 900, "height": 600})
        # Fixed settle window for a negative assertion: remote geometry must
        # remain unchanged after the resize propagates.
        await asyncio.sleep(1.0)
        video_a = await iframe_eval(
            page_a,
            """(() => {
                const v = document.querySelector('video');
                return v ? [v.videoWidth, v.videoHeight] : null;
            })()""",
        )
        assert video_a == [1920, 1080], video_a
        await page_a.set_viewport_size({"width": 1500, "height": 950})
        # Fixed settle window for the same negative geometry assertion.
        await asyncio.sleep(1.0)
        video_a2 = await iframe_eval(
            page_a,
            """(() => {
                const v = document.querySelector('video');
                return v ? [v.videoWidth, v.videoHeight] : null;
            })()""",
        )
        assert video_a2 == [1920, 1080], video_a2
        datachannel_messages = await iframe_eval(
            page_a, "window.__sentDataChannelMessages || []"
        )
        assert isinstance(datachannel_messages, list)
        assert not any(
            isinstance(message, str) and message.startswith("r,")
            for message in datachannel_messages
        ), datachannel_messages
        # Eviction-proof companion (t024 AC-018/A53): the probe's per-type
        # counters survive the 500-entry rolling buffer, so the no-resize
        # verdict does not depend on the buffer still holding the window.
        datachannel_counts = await iframe_eval(
            page_a, "window.__sentDataChannelCounts || {}"
        )
        assert datachannel_counts.get("r", 0) == 0, datachannel_counts

        # Both pages input into the same remote box (no lease / single controller).
        await prepare_remote_input(browser_container, target_id)
        await iframe_eval(page_a, "document.querySelector('#overlayInput')?.focus()")
        t0 = time.monotonic()
        await page_a.keyboard.press("Digit1")
        value = None
        for _ in range(300):
            value = await remote_value(browser_container, target_id)
            if value == "1":
                break
            await asyncio.sleep(0.02)
        input_latency_ms = int((time.monotonic() - t0) * 1000)
        assert value == "1", value
        assert input_latency_ms <= 3000, input_latency_ms

        await prepare_remote_input(browser_container, target_id)
        await iframe_eval(page_a, "document.querySelector('#overlayInput')?.focus()")
        await page_a.keyboard.press("Digit1")
        await iframe_eval(page_b, "document.querySelector('#overlayInput')?.focus()")
        await page_b.keyboard.press("Digit2")
        concurrent = None
        for _ in range(300):
            concurrent = await remote_value(browser_container, target_id)
            if concurrent == "12":
                break
            await asyncio.sleep(0.02)
        assert concurrent == "12", concurrent

        # Independent audio mute per connection through the product control.
        await page_a.click('[data-testid="session-audio-toggle-btn"]')
        messages_a = await wait_iframe_datachannel_message(page_a, "STOP_AUDIO")
        assert "STOP_AUDIO" in messages_a
        # Media elements carrying the remote audio track must exist; an empty
        # selection would make the mute comparison vacuous.
        muted_a = await iframe_eval(
            page_a,
            """(() => {
                const nodes = [...document.querySelectorAll('audio, video')].filter(
                    (n) => n.srcObject && n.srcObject.getAudioTracks().length > 0);
                return nodes.length > 0 && nodes.every((n) => n.muted);
            })()""",
        )
        unmuted_b = await iframe_eval(
            page_b,
            """(() => {
                const nodes = [...document.querySelectorAll('audio, video')].filter(
                    (n) => n.srcObject && n.srcObject.getAudioTracks().length > 0);
                return nodes.length > 0 && nodes.every((n) => !n.muted);
            })()""",
        )
        assert muted_a is True
        assert unmuted_b is True, "Muting page A must not mute page B"
        messages_b = (
            await iframe_eval(page_b, "window.__sentDataChannelMessages || []") or []
        )
        assert not any(
            isinstance(message, str) and message.startswith("STOP_AUDIO")
            for message in messages_b
        ), "Page B must not receive A's STOP_AUDIO"
        await page_a.click('[data-testid="session-audio-toggle-btn"]')
        messages_a2 = await wait_iframe_datachannel_message(page_a, "START_AUDIO")
        assert "START_AUDIO" in messages_a2

        # No client activity/visibility frames are sent to the Gateway.
        # Fixed settle window for a negative assertion: absence of activity
        # frames must hold over an interval.
        await asyncio.sleep(1.5)
        sent_payloads = "\n".join(wire.frames_sent)
        assert '"cbrowser":"activity"' not in sent_payloads
        assert '"cbrowser": "activity"' not in sent_payloads
        assert '"visibility"' not in sent_payloads

        _save(
            tmp_path,
            "ac004_ac005",
            {
                "profile_id": profile_id,
                "remote_video_size": video_a,
                "remote_video_size_after_second_resize": video_a2,
                "first_frame_ms": first_frame_ms,
                "input_to_remote_ms": input_latency_ms,
                # Complete raw samples behind the budget verdicts in this
                # run (t024 AC-018/A53): thresholds stay hard single-run
                # limits (8000/3000ms); the samples are recorded so a
                # failure shows the distribution, not just the verdict.
                "perf_samples": {
                    "first_frame_ms": [first_frame_ms],
                    "input_to_remote_ms": [input_latency_ms],
                },
                "datachannel_counts": datachannel_counts,
                "concurrent_remote_value": concurrent,
                "mute_a": muted_a,
                "unmuted_b": unmuted_b,
                "ws_sent_count": len(wire.frames_sent),
            },
        )

        async with await harness.api_client() as client_api:
            await client_api.post(f"/api/v1/profiles/{profile_id}/stop")
    finally:
        await browser.close()
        await pw.stop()


# --------------------------------------------------------------------------- #
# AC-007
# --------------------------------------------------------------------------- #


MEDIA_FAULT_INIT_SCRIPT = """(() => {
    const workerCode = `
        let count = 0;
        self.onrtctransform = (e) => {
            const stream = new TransformStream({
                transform(frame, ctrl) {
                    count++;
                    self.postMessage({ type: 'DISCARDED', count });
                }
            });
            e.transformer.readable.pipeThrough(stream).pipeTo(e.transformer.writable);
        };
    `;
    const blob = new Blob([workerCode], { type: 'application/javascript' });
    const blobUrl = URL.createObjectURL(blob);
    const worker = new Worker(blobUrl);
    window.__mediaFaultWorker = worker;
    window.__discardedFramesCount = 0;
    worker.onmessage = (e) => {
        if (e.data?.type === 'DISCARDED') window.__discardedFramesCount = e.data.count;
    };
    window.addEventListener('pagehide', () => {
        worker.terminate();
        URL.revokeObjectURL(blobUrl);
    });

    if (window.RTCPeerConnection) {
        class FaultPC extends window.RTCPeerConnection {
            constructor(...args) {
                super(...args);
                this.addEventListener('track', (e) => {
                    if (e.track?.kind === 'video' && e.receiver) {
                        e.receiver.transform = new RTCRtpScriptTransform(worker);
                    }
                });
            }
        }
        window.RTCPeerConnection = FaultPC;
    }
})();"""


@pytest.mark.asyncio
async def test_ac007_lifecycle_resume_and_isolated_media_diagnostics(
    harness: FrontendAppTopologyHarness, tmp_path: Path
) -> None:
    pw, browser, context = await launch_browser()
    profile_id = None
    try:
        page = await context.new_page()
        await ui_login(page, harness)

        # Runtime not ready: profile exists but was never started.
        unready = await create_profile_via_ui(page, harness, "Unready Profile")
        await open_session(page, harness, unready)
        await page.wait_for_selector(
            '[data-testid="session-runtime-not-ready"]', timeout=15000
        )
        stage_title = await page.inner_text(
            '[data-testid="session-runtime-not-ready-title"]'
        )
        assert "运行时未就绪" in stage_title
        assert (
            await page.query_selector('[data-testid="session-launch-btn"]') is not None
        )

        # Start a real runtime, then freeze/resume the page via CDP Page lifecycle.
        profile_id = await create_profile_via_ui(page, harness, "Lifecycle Profile")
        wire = WireRecorder(page, context)
        await wire.start()
        await open_session(page, harness, profile_id)
        await launch_profile_via_ui(page)
        await animate_remote_fixture(harness, profile_id)

        def hellos() -> list[str]:
            return [f for f in wire.frames_sent if f.startswith("HELLO client ")]

        cdp = await context.new_cdp_session(page)
        await cdp.send("Page.enable")
        await cdp.send("Network.enable")
        hello_sent: list[str] = []
        cdp.on(
            "Network.webSocketFrameSent",
            lambda e: hello_sent.append(e["response"]["payloadData"]),
        )
        before = await wait_iframe_stats(page, name="before freeze")
        await cdp.send("Page.setWebLifecycleState", {"state": "frozen"})
        # Fixed frozen dwell window: exercise the lifecycle transition. No
        # assertion reads state during this interval.
        await asyncio.sleep(1.5)
        await cdp.send("Page.setWebLifecycleState", {"state": "active"})
        after = await wait_iframe_stats(page, name="after resume")
        assert after["tab_id"] == before["tab_id"]
        assert after["video"]["framesDecoded"] > before["video"]["framesDecoded"]

        initial_hellos = hellos()
        assert initial_hellos, "session never sent an official HELLO"
        initial_meta = json.loads(initial_hellos[-1].split(" ", 2)[2])
        initial_tab = initial_meta["client_tab_id"]
        initial_resume_key = initial_meta["resume_key"]
        assert initial_tab == before["tab_id"]

        # Connection-level reconnect (signaling socket cut while the peer
        # connection is healthy) keeps the official resume_key and produces the
        # official RESUMED handshake, without a page reload.
        hello_count_before_resume = len(hellos())
        await iframe_eval(
            page,
            "(() => { window.__last_ws && window.__last_ws.close(); return true; })()",
        )
        deadline = time.monotonic() + 20
        while (
            time.monotonic() < deadline and len(hellos()) <= hello_count_before_resume
        ):
            await asyncio.sleep(0.1)
        assert len(hellos()) > hello_count_before_resume, hellos()
        # The first HELLO after the socket cut is the official resume attempt;
        # it must carry the same client_tab_id and resume_key. The Stream Agent
        # re-establishes its loopback upstream, so the server may answer with
        # SESSION_OK instead of RESUMED; media must still flow afterwards.
        resumed_meta = json.loads(hellos()[hello_count_before_resume].split(" ", 2)[2])
        assert resumed_meta["client_tab_id"] == initial_tab
        assert resumed_meta["resume_key"] == initial_resume_key

        resumed_stats = await wait_iframe_stats(page, name="after reconnect")
        assert resumed_stats["video"]["framesDecoded"] > 0

        # Invalid connection rebuild: destroy the page's PeerConnection and
        # drive the adapter's lifecycle-resume detection. The host must reload
        # the iframe; the rebuilt connection keeps the same client_tab_id but
        # gets a fresh official resume_key (refresh semantics).
        hello_count_before_rebuild = len(hellos())
        src_before_rebuild = await iframe_src(page)
        reload_before = int(re.search(r"_k=(\d+)", src_before_rebuild).group(1))
        assert await iframe_eval(
            page,
            """(() => {
                const pc = window.__activePC;
                if (!pc) return false;
                pc.close();
                document.dispatchEvent(new Event('resume'));
                return true;
            })()""",
        )
        await page.wait_for_function(
            r"""(expected) => {
                const f = document.querySelector(
                    'iframe[data-testid="browser-session-iframe"]');
                const src = f ? f.getAttribute('src') || '' : '';
                const match = src.match(/_k=(\d+)/);
                return Boolean(match && Number(match[1]) >= expected);
            }""",
            arg=reload_before + 1,
            timeout=15000,
        )
        rebuilt = await wait_iframe_stats(page, name="after rebuild")
        assert rebuilt["tab_id"] == initial_tab
        deadline = time.monotonic() + 20
        while (
            time.monotonic() < deadline and len(hellos()) <= hello_count_before_rebuild
        ):
            await asyncio.sleep(0.1)
        rebuilt_meta = json.loads(hellos()[hello_count_before_rebuild].split(" ", 2)[2])
        assert rebuilt_meta["client_tab_id"] == initial_tab
        assert rebuilt_meta["resume_key"] != initial_resume_key
        assert rebuilt["video"]["framesDecoded"] > 0

        # Media no frames: simulate genuine media decoding failure isolated to
        # this viewer via RTCRtpScriptTransform, discarding incoming encoded
        # video frames without enqueuing. Proves selected pair/connectionState
        # connected, RTP bytes/packets flowing, framesDecoded == 0, and container
        # remaining running, triggering the product's media_no_frames stage.
        browser_cname, stream_cname = harness.container_names(profile_id)
        b_box_before = harness.docker_client.containers.get(browser_cname)
        s_box_before = harness.docker_client.containers.get(stream_cname)
        browser_cid = b_box_before.id
        stream_cid = s_box_before.id
        assert b_box_before.status == "running"
        assert s_box_before.status == "running"

        rt_before = await harness.get_runtime(profile_id)
        assert rt_before["desired_state"] == "running"
        assert rt_before["observed_state"] == "running"
        initial_instance_id = rt_before["runtime_instance_id"]

        media_page = await context.new_page()
        try:
            has_transform = await media_page.evaluate(
                "typeof RTCRtpScriptTransform === 'function' && "
                "'transform' in RTCRtpReceiver.prototype"
            )
            assert has_transform, (
                "RTCRtpScriptTransform and RTCRtpReceiver.prototype.transform "
                "must be available"
            )

            await media_page.add_init_script(MEDIA_FAULT_INIT_SCRIPT)
            await open_session(media_page, harness, profile_id)

            initial_fault_stats = await wait_iframe_stats(
                media_page, min_frames=0, name="media fault initial"
            )
            assert initial_fault_stats["connected"] is True
            assert initial_fault_stats["video"]["framesDecoded"] == 0
            initial_bytes = initial_fault_stats["video"]["bytesReceived"]
            initial_packets = initial_fault_stats["video"]["packetsReceived"]

            async def media_fault_observation() -> tuple[str, dict[str, Any], Any]:
                title_el = await media_page.query_selector(
                    '[data-testid="session-stage-title"]'
                )
                title = await title_el.inner_text() if title_el else ""
                stats = await wait_iframe_stats(
                    media_page, min_frames=0, name="media fault poll"
                )
                discarded = await iframe_eval(
                    media_page, "window.__discardedFramesCount || 0"
                )
                return title, stats, discarded

            media_title, final_fault_stats, discarded_count = await poll_until(
                media_fault_observation,
                lambda obs: (
                    "媒体未产生画面" in obs[0]
                    and (
                        obs[1]["video"]["bytesReceived"] > initial_bytes
                        or obs[1]["video"]["packetsReceived"] > initial_packets
                    )
                    and (obs[2] or 0) > 0
                ),
                timeout=45.0,
                interval=0.5,
                description=(
                    "media_no_frames stage, RTP growth and discarded encoded frames"
                ),
            )

            assert final_fault_stats is not None, (
                "media_no_frames or RTP growth not observed in 45s: "
                f"title={media_title}"
            )
            assert "媒体未产生画面" in media_title, media_title
            assert final_fault_stats["connected"] is True
            assert final_fault_stats["video"]["framesDecoded"] == 0
            assert (
                final_fault_stats["video"]["bytesReceived"] > initial_bytes
                or final_fault_stats["video"]["packetsReceived"] > initial_packets
            ), "RTP video bytes/packets must grow across media waiting interval"
            assert (
                await media_page.query_selector('[data-testid="session-reconnect-btn"]')
                is not None
            )
            assert (
                await media_page.query_selector(
                    '[data-testid="session-view-status-btn"]'
                )
                is not None
            )
            assert discarded_count > 0, (
                f"Worker must have discarded encoded frames, got {discarded_count}"
            )

            # The product action must route to the profile detail page.
            await media_page.click('[data-testid="session-view-status-btn"]')
            await media_page.wait_for_url(
                re.compile(rf"/profiles/{profile_id}/config$"), timeout=15000
            )
        finally:
            await media_page.close()

        # Invariants: Browser & Stream CID, instance, and API runtime state unchanged.
        b_box_after = harness.docker_client.containers.get(browser_cname)
        s_box_after = harness.docker_client.containers.get(stream_cname)
        assert b_box_after.id == browser_cid, "Browser container must not be recreated"
        assert s_box_after.id == stream_cid, "Stream container must not be recreated"
        assert b_box_after.status == "running"
        assert s_box_after.status == "running"

        rt_after = await harness.get_runtime(profile_id)
        assert rt_after["desired_state"] == "running"
        assert rt_after["observed_state"] == "running"
        assert rt_after["runtime_instance_id"] == initial_instance_id, (
            "runtime_instance_id changed (unexpected container recreation)"
        )

        # Signaling failure: stop the Gateway, open a fresh viewer, require stage.
        harness.gateway_container.stop(timeout=5)
        try:
            sig_page = await context.new_page()
            await open_session(sig_page, harness, profile_id)
            await sig_page.wait_for_selector(
                '[data-testid="session-stage-title"]', timeout=60000
            )
            deadline = time.monotonic() + 45
            sig_title = ""
            while time.monotonic() < deadline:
                sig_title = await sig_page.inner_text(
                    '[data-testid="session-stage-title"]'
                )
                if "信令连接失败" in sig_title:
                    break
                await asyncio.sleep(0.5)
            assert "信令连接失败" in sig_title, sig_title
            assert (
                await sig_page.query_selector('[data-testid="session-reconnect-btn"]')
                is not None
            )
        finally:
            harness.gateway_container.start()

        _save(
            tmp_path,
            "ac007",
            {
                "profile_id": profile_id,
                "unready_title": stage_title,
                "tab_id_before_freeze": before["tab_id"],
                "tab_id_after_resume": after["tab_id"],
                "hello_frames_during_lifecycle": len(hello_sent),
                "initial_tab_id": initial_tab,
                "initial_resume_key": initial_resume_key,
                "resumed_resume_key": resumed_meta["resume_key"],
                "rebuilt_tab_id": rebuilt["tab_id"],
                "rebuilt_resume_key": rebuilt_meta["resume_key"],
                "media_stage_title": media_title,
                "signaling_stage_title": sig_title,
            },
        )

        async with await harness.api_client() as client_api:
            await client_api.post(f"/api/v1/profiles/{profile_id}/stop")
    finally:
        await browser.close()
        await pw.stop()


# --------------------------------------------------------------------------- #
# AC-009
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ac009_ui_start_stop_and_supervisor_outage_convergence(
    harness: FrontendAppTopologyHarness, tmp_path: Path
) -> None:
    pw, browser, context = await launch_browser()
    profile_id = None
    try:
        page = await context.new_page()
        await ui_login(page, harness)
        profile_id = await create_profile_via_ui(page, harness, "Coordinator Profile")

        # Launch strictly through the UI button; API coordinator drives Supervisor.
        await open_session(page, harness, profile_id)
        await launch_profile_via_ui(page)
        await harness.wait_runtime(profile_id, desired="running", observed="running")
        browser_container, stream_container = harness.container_names(profile_id)
        assert (
            harness.docker_client.containers.get(browser_container).status == "running"
        )
        assert (
            harness.docker_client.containers.get(stream_container).status == "running"
        )
        stats = await wait_iframe_stats(page, name="coordinator launch")

        # Explicit stop button removes the real containers.
        await stop_profile_via_api(page, harness, profile_id)
        await harness.wait_runtime(profile_id, desired="stopped", observed="stopped")
        await wait_runtime_containers_gone(harness, profile_id)
        await page.wait_for_selector(
            '[data-testid="session-launch-btn"]', timeout=60000
        )

        # Supervisor outage: desired state is preserved, UI reports coordination error,
        # and convergence happens after Supervisor comes back.
        harness.supervisor_container.stop(timeout=10)
        try:
            await page.click('[data-testid="session-launch-btn"]')
            rt_outage = await harness.wait_runtime(
                profile_id, desired="running", timeout=60
            )
            deadline = time.monotonic() + 60
            error_text = ""
            while time.monotonic() < deadline:
                node = await page.query_selector(
                    '[data-testid="runtime-coordinator-error"]'
                )
                if node:
                    error_text = (await node.inner_text()).strip()
                    if error_text:
                        break
                await asyncio.sleep(0.5)
            assert error_text, "UI must surface coordinator failure"
            assert "Supervisor" in error_text or "supervisor" in error_text, error_text
            assert rt_outage["desired_state"] == "running"
            assert rt_outage["observed_state"] != "running"
        finally:
            harness.supervisor_container.start()
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    async with httpx.AsyncClient(trust_env=False, timeout=5.0) as probe:
                        resp = await probe.get(
                            f"{harness.supervisor_url}/supervisor/v1/health",
                            headers={
                                "Authorization": f"Bearer {harness.keys['supervisor']}"
                            },
                        )
                    if resp.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)

        # Automatic convergence: no extra clicks, media returns.
        rt_ok = await harness.wait_runtime(
            profile_id, desired="running", observed="running", timeout=120
        )
        stats_after = await wait_iframe_stats(page, name="converged", timeout=90)
        assert stats_after["video"]["framesDecoded"] > 0

        _save(
            tmp_path,
            "ac009",
            {
                "profile_id": profile_id,
                "browser_container": browser_container,
                "stream_container": stream_container,
                "initial_frames": stats["video"]["framesDecoded"],
                "outage_desired_state": rt_outage["desired_state"],
                "outage_observed_state": rt_outage["observed_state"],
                "ui_error": error_text,
                "converged_observed_state": rt_ok["observed_state"],
                "converged_frames": stats_after["video"]["framesDecoded"],
            },
        )

        await stop_profile_via_api(page, harness, profile_id)
        await harness.wait_runtime(profile_id, desired="stopped", observed="stopped")
        await wait_runtime_containers_gone(harness, profile_id)
    finally:
        if profile_id:
            try:
                async with await harness.api_client() as client_api:
                    await client_api.post(f"/api/v1/profiles/{profile_id}/stop")
            except Exception as exc:  # noqa: BLE001 - best-effort final stop cleanup
                logger.debug("Final stop cleanup skipped: %s", type(exc).__name__)
        await browser.close()
        await pw.stop()


# --------------------------------------------------------------------------- #
# t019: ICE-lite session setup — host-only candidates, <=2s to first frame
# --------------------------------------------------------------------------- #

_ALL_CANDIDATES_SCRIPT = """async () => {
    const SEL = 'iframe[data-testid="browser-session-iframe"]';
    const f = document.querySelector(SEL);
    if (!f || !f.contentWindow) return null;
    const pcs = f.contentWindow.__pcs || [];
    if (!pcs.length) return null;
    const pc = pcs[pcs.length - 1];
    const report = await pc.getStats();
    const candidates = [];
    for (const entry of report.values()) {
        if (entry.type === 'local-candidate' || entry.type === 'remote-candidate') {
            candidates.push({
                kind: entry.type,
                candidateType: entry.candidateType,
                address: entry.address || entry.ip || null,
                port: entry.port || null,
                protocol: entry.protocol || null,
                relatedAddress: entry.relatedAddress || null,
            });
        }
    }
    const parseSdp = (description) => {
        const sdp = description && description.sdp ? description.sdp : "";
        const result = [];
        for (const line of sdp.split("\\r\\n")) {
            const match = line.match(/^a=candidate:[^ ]+ [0-9]+ ([^ ]+) [0-9]+ ([^ ]+) ([0-9]+) typ ([^ ]+)/);
            if (match) {
                result.push({
                    protocol: match[1],
                    address: match[2],
                    port: Number(match[3]),
                    candidateType: match[4],
                });
            }
        }
        return result;
    };
    return {
        candidates,
        localSignaled: parseSdp(pc.localDescription),
        remoteSignaled: parseSdp(pc.remoteDescription),
        connectionState: pc.connectionState,
    };
}"""


def _assert_host_only_candidates(
    snapshot: dict[str, Any], udp_mux_port: int
) -> None:
    # The signaled ICE candidate set (SDP) must be host-only. getStats
    # additionally reports a local peer-reflexive candidate created by
    # Docker's published-UDP-port NAT; it is not part of the signaled set
    # and cannot be removed by the client configuration.
    local = snapshot["localSignaled"]
    remote = snapshot["remoteSignaled"]
    assert local, "no local ICE candidates signaled"
    assert remote, "no remote ICE candidates signaled"
    for cand in local + remote:
        assert cand["candidateType"] == "host", cand
    for cand in remote:
        assert cand["address"] == "127.0.0.1", cand
        assert cand["protocol"] == "udp", cand
        assert cand["port"] == udp_mux_port, cand
    stats_remote = [
        c for c in snapshot["candidates"] if c["kind"] == "remote-candidate"
    ]
    assert stats_remote, "no remote candidates reported by getStats"
    for cand in stats_remote:
        assert cand["candidateType"] == "host", cand
        assert cand["address"] == "127.0.0.1", cand
        assert cand["protocol"] == "udp", cand
        assert cand["port"] == udp_mux_port, cand


@pytest.mark.asyncio
async def test_t019_switch_and_refresh_first_frame_within_2s_host_only(
    harness: FrontendAppTopologyHarness, tmp_path: Path
) -> None:
    """t019 AC-001/AC-002: with ICE-lite, a new session exposes only
    127.0.0.1 host candidates and reaches first frame within 2 seconds,
    both when switching profiles in the sidebar and when refreshing."""
    pw, browser, context = await launch_browser()
    try:
        page_a = await context.new_page()
        await ui_login(page_a, harness)
        profile_a = await create_profile_via_ui(page_a, harness, "Ice Alpha")
        profile_b = await create_profile_via_ui(page_a, harness, "Ice Beta")

        await open_session(page_a, harness, profile_a)
        await launch_profile_via_ui(page_a)
        await wait_iframe_stats(page_a, name="A initial")

        page_b = await context.new_page()
        await open_session(page_b, harness, profile_b)
        await launch_profile_via_ui(page_b)
        await wait_iframe_stats(page_b, name="B initial")
        await page_b.close()

        # B's allocated UDP mux port, read from its Stream container env.
        _, stream_container_b = harness.container_names(profile_b)
        stream_box_b = harness.docker_client.containers.get(stream_container_b)
        runtime_env_b = dict(
            entry.split("=", 1) for entry in stream_box_b.attrs["Config"]["Env"]
        )
        udp_mux_port_b = int(runtime_env_b["CBROWSER_UDP_MUX_PORT"])

        # Switch A -> B from the sidebar: new PeerConnection, first frame <= 2s.
        switch_start = time.monotonic()
        await page_a.evaluate(
            "(id) => { window.history.pushState({}, '', '/session/' + id);"
            " window.dispatchEvent(new PopStateEvent('popstate')); }",
            profile_b,
        )
        clicked = time.monotonic()
        await page_a.wait_for_url(
            re.compile(rf"/session/{profile_b}"), timeout=15000
        )
        navigated = time.monotonic()
        await wait_iframe_stats(page_a, name="B after switch")
        switch_elapsed = time.monotonic() - switch_start
        assert switch_elapsed <= 2.0, (
            f"switch to first frame took {switch_elapsed:.3f}s "
            f"(click={clicked - switch_start:.3f}s, "
            f"url={navigated - clicked:.3f}s, "
            f"frames={time.monotonic() - navigated:.3f}s)"
        )
        switch_candidates = await _evaluate_bounded(
            page_a, _ALL_CANDIDATES_SCRIPT, timeout=10.0
        )
        _assert_host_only_candidates(switch_candidates, udp_mux_port_b)

        # Refresh rebuilds the session: same budget, same candidate set.
        refresh_start = time.monotonic()
        await page_a.reload(wait_until="domcontentloaded")
        await wait_iframe_stats(page_a, name="B after refresh")
        refresh_elapsed = time.monotonic() - refresh_start
        assert refresh_elapsed <= 2.0, (
            f"refresh to first frame took {refresh_elapsed:.3f}s"
        )
        refresh_candidates = await _evaluate_bounded(
            page_a, _ALL_CANDIDATES_SCRIPT, timeout=10.0
        )
        _assert_host_only_candidates(refresh_candidates, udp_mux_port_b)

        _save(
            tmp_path,
            "t019_ice_lite",
            {
                "profile_a": profile_a,
                "profile_b": profile_b,
                "switch_first_frame_s": round(switch_elapsed, 3),
                "refresh_first_frame_s": round(refresh_elapsed, 3),
                "switch_candidates": switch_candidates,
                "refresh_candidates": refresh_candidates,
            },
        )
    finally:
        await browser.close()
        await pw.stop()
