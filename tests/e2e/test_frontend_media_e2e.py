"""Full-application media E2E tests for t007 AC-004 and AC-005.

Runs the complete production frontend (Vite build + vendored Selkies client)
inside a real Caddy/API/Supervisor/Stream/Browser topology. Visibility and
audio are exercised through the official Selkies client running in the
BrowserSessionView iframe; no visibility/activity data is sent to the Gateway.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pytest
from gateway_probe.browser_oracle import browser_eval
from gateway_probe.evidence import save_evidence
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from wait import poll_until

from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT  # noqa: E402
from frontend_app_probe.harness import FrontendAppTopologyHarness  # noqa: E402

pytestmark = [pytest.mark.serial, pytest.mark.e2e_images('CBROWSER_API_TEST_IMAGE', 'CBROWSER_CADDY_TEST_IMAGE', 'CBROWSER_GATEWAY_IMAGE', 'CBROWSER_RUNTIME_TEST_IMAGE', 'CBROWSER_STREAM_TEST_IMAGE', 'CBROWSER_SUPERVISOR_TEST_IMAGE')]

logger = logging.getLogger("cbrowser.frontend_media.e2e")


class MediaTopologyHarness(FrontendAppTopologyHarness):
    """Lane-scoped Docker prefix; no objects outside t007-media are created."""

    prefix_base = "t007-media"
    test_label = "t007-media"


IFRAME_SELECTOR = 'iframe[data-testid="sess-iframe"]'

# Plan 9.2 targets 30 FPS for an active foreground viewer and 8 FPS for a
# static visible viewer. Over a 3 s sample we require at least 20 FPS
# (>= 60 frames), well above the 8 FPS idle floor while tolerating capture
# pacing and keyframe scheduling jitter. A hidden viewer must decode 0 frames.
ACTIVE_FPS_FLOOR = 20.0
ACTIVE_SAMPLE_SECONDS = 3.0


# --------------------------------------------------------------------------- #
# Module-scoped real topology and remote browser page
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def harness(tmp_path_factory: pytest.TempPathFactory):
    h = MediaTopologyHarness(tmp_path_factory.mktemp("fe_media"))
    asyncio.run(h.start())
    try:
        yield h
    finally:
        asyncio.run(h.cleanup())


@pytest.fixture(scope="module")
def media_profile(harness: FrontendAppTopologyHarness) -> dict[str, Any]:
    return asyncio.run(harness.create_and_start_profile("fe_media_profile"))


@pytest.fixture(scope="module")
def remote_page(media_profile: dict[str, Any]) -> dict[str, Any]:
    """Navigates the remote Chrome page to the motion + WebAudio fixture."""
    result = browser_eval(media_profile["browser_container"], "true")
    return {
        "target_id": result["target_id"],
        "container": media_profile["browser_container"],
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def launch_browser() -> tuple[Any, Browser, BrowserContext, dict[str, str]]:
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
    return pw, browser, context, {}


async def add_session_cookie(
    context: BrowserContext, harness: FrontendAppTopologyHarness
) -> None:
    headers = await harness.login_api()
    cookie = headers["Cookie"].split("cbrowser_session=", 1)[1]
    await context.add_cookies(
        [{"name": "cbrowser_session", "value": cookie, "url": harness.origin}]
    )


async def open_session(
    page: Page, harness: FrontendAppTopologyHarness, profile_id: str
) -> None:
    await page.goto(
        f"{harness.origin}/session/{profile_id}", wait_until="domcontentloaded"
    )
    await page.wait_for_selector(IFRAME_SELECTOR, timeout=30000)


async def iframe_eval(page: Page, expression: str) -> Any:
    return await page.evaluate(
        """(expr) => {
            const f = document.querySelector(
                'iframe[data-testid="sess-iframe"]');
            if (!f || !f.contentWindow) return null;
            return f.contentWindow.eval(expr);
        }""",
        expression,
    )


async def iframe_stats(page: Page) -> dict[str, Any] | None:
    return await page.evaluate(
        """async () => {
            const f = document.querySelector(
                'iframe[data-testid="sess-iframe"]');
            if (!f || !f.contentWindow) return null;
            if (typeof f.contentWindow.__getWebRTCStats !== 'function') return null;
            return await f.contentWindow.__getWebRTCStats();
        }"""
    )


async def wait_iframe_stats(
    page: Page, *, timeout: float = 60.0, name: str = "page"
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = await iframe_stats(page)
        except (PlaywrightError, RuntimeError) as exc:  # iframe navigation
            last = {"error": str(exc)}
        if (
            last
            and last.get("video")
            and last["video"].get("framesDecoded", 0) > 0
            and last.get("connected")
        ):
            return last
        await asyncio.sleep(0.3)
    raise TimeoutError(f"{name} did not decode frames: {json.dumps(last)[:800]}")


async def data_channel_messages(page: Page) -> list[str]:
    messages = await iframe_eval(
        page,
        "window.__sentDataChannelMessages ? [...window.__sentDataChannelMessages] : []",
    )
    return [m for m in (messages or []) if isinstance(m, str)]


async def wait_data_channel_message(
    page: Page, needle: str, *, timeout: float = 10.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(needle in message for message in await data_channel_messages(page)):
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(
        f"iframe never sent data channel message {needle!r}: "
        f"{await data_channel_messages(page)}"
    )


async def set_iframe_visibility(page: Page, hidden: bool) -> None:
    """Overrides visibility in the iframe document per d023 (headless Chrome)."""
    await page.evaluate(
        """(hidden) => {
            const state = hidden ? 'hidden' : 'visible';
            const f = document.querySelector(
                'iframe[data-testid="sess-iframe"]');
            if (!f || !f.contentDocument) throw new Error('iframe document missing');
            const doc = f.contentDocument;
            Object.defineProperty(doc, 'visibilityState', {
                configurable: true,
                get: () => state,
            });
            Object.defineProperty(doc, 'hidden', {
                configurable: true,
                get: () => hidden,
            });
            doc.dispatchEvent(new Event('visibilitychange'));
        }""",
        hidden,
    )


async def frame_delta(
    page: Page, seconds: float
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Measure frames decoded across a fixed sampling window."""
    before = await wait_iframe_stats(page)
    # Genuine sampling window: frame growth is the measured quantity, so the
    # interval cannot be replaced by polling for a settled value.
    await asyncio.sleep(seconds)
    after = await iframe_stats(page)
    assert after and after.get("video"), after
    return (
        after["video"]["framesDecoded"] - before["video"]["framesDecoded"],
        before,
        after,
    )


async def gateway_visibility(
    harness: FrontendAppTopologyHarness,
    profile_id: str,
    runtime_instance_id: str,
) -> dict[str, Any]:
    port = harness.gateway_container.attrs["NetworkSettings"]["Ports"][
        f"{DEFAULT_GATEWAY_PORT}/tcp"
    ][0]["HostPort"]
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{port}",
        headers={"Authorization": f"Bearer {harness.keys['gateway']}"},
        trust_env=False,
        timeout=10.0,
    ) as client:
        resp = await client.get(
            f"/gateway/v1/internal/profiles/{profile_id}/visibility",
            params={"runtime_instance_id": runtime_instance_id},
        )
        resp.raise_for_status()
        return resp.json()


async def wait_gateway_visibility(
    harness: FrontendAppTopologyHarness,
    profile_id: str,
    runtime_instance_id: str,
    predicate: Any,
    *,
    timeout: float = 20.0,
    name: str = "visibility",
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            last = await gateway_visibility(harness, profile_id, runtime_instance_id)
        except httpx.HTTPError as exc:
            last = {"error": str(exc)}
        if predicate(last):
            return last
        await asyncio.sleep(0.5)
    raise TimeoutError(f"{name} did not converge: {json.dumps(last)}")


async def sample_iframe_pixel(page: Page) -> list[int] | None:
    return await page.evaluate(
        """() => {
            const f = document.querySelector(
                'iframe[data-testid="sess-iframe"]');
            if (!f || !f.contentDocument) return null;
            const doc = f.contentDocument;
            const tmp = doc.createElement('canvas');
            tmp.width = 1;
            tmp.height = 1;
            const ctx = tmp.getContext('2d', {willReadFrequently: true});
            const canvases = ['videoCanvas', 'videoWorkerCanvas'];
            for (const id of canvases) {
                const canvas = doc.getElementById(id);
                if (!canvas || canvas.width <= 0 || canvas.height <= 0) continue;
                try {
                    ctx.drawImage(
                        canvas,
                        Math.floor(canvas.width / 2),
                        Math.floor(canvas.height / 2),
                        1,
                        1,
                        0,
                        0,
                        1,
                        1
                    );
                    return [...ctx.getImageData(0, 0, 1, 1).data];
                } catch (err) {
                    // Try the next sink.
                }
            }
            const video =
                doc.getElementById('stream') || doc.getElementById('videoStream');
            if (video && video.videoWidth > 0 && video.videoHeight > 0) {
                try {
                    ctx.drawImage(
                        video,
                        Math.floor(video.videoWidth / 2),
                        Math.floor(video.videoHeight / 2),
                        1,
                        1,
                        0,
                        0,
                        1,
                        1
                    );
                    return [...ctx.getImageData(0, 0, 1, 1).data];
                } catch (err) {
                    return null;
                }
            }
            return null;
        }"""
    )


async def wait_iframe_pixel(
    page: Page,
    predicate: Any,
    *,
    timeout: float = 20.0,
    name: str = "pixel",
) -> list[int]:
    deadline = time.monotonic() + timeout
    last: list[int] | None = None
    while time.monotonic() < deadline:
        last = await sample_iframe_pixel(page)
        if last and predicate(last):
            return last
        await asyncio.sleep(0.3)
    raise TimeoutError(f"{name} pixel never matched: {last}")


def pixel_close(
    actual: list[int], expected: tuple[int, int, int], tolerance: int = 24
) -> bool:
    return all(abs(actual[i] - expected[i]) <= tolerance for i in range(3))


def remote_cdp(container: str, commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Runs arbitrary CDP commands in the remote Browser via its agent socket."""
    script = """import asyncio, json, websockets

async def main():
    from cbrowser.runtime_agent.socket_root import container_agent_socket_path
    async with websockets.unix_connect(
        container_agent_socket_path(), "ws://localhost/cdp"
    ) as ws:
        counter = 0

        async def command(method, params=None):
            nonlocal counter
            counter += 1
            await ws.send(json.dumps({
                "id": counter, "method": method, "params": params or {}
            }))
            while True:
                result = json.loads(await asyncio.wait_for(ws.recv(), 15))
                if result.get("id") == counter:
                    if "error" in result:
                        raise RuntimeError(f"CDP {method} failed: {result['error']}")
                    return result.get("result", {})

        results = []
        for request in parameters:
            results.append(await command(request["method"], request.get("params")))
        print(json.dumps(results))

asyncio.run(main())
"""
    full = "parameters = " + repr(commands) + "\n" + script
    result = subprocess.run(
        ["docker", "exec", container, "python3", "-c", full],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, f"remote_cdp failed: {result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def save_artifacts(tmp_path: Path, name: str, payload: Any) -> Path:
    return save_evidence(name, payload, target_dir=tmp_path / "evidence")


class WireRecorder:
    """Records WebSocket frames to prove no activity/visibility frames are sent."""

    def __init__(self, page: Page, context: BrowserContext) -> None:
        self.page = page
        self.context = context
        self.frames_sent: list[str] = []
        self._cdp: Any = None

    async def start(self) -> None:
        self._cdp = await self.context.new_cdp_session(self.page)
        await self._cdp.send("Network.enable")
        self._cdp.on(
            "Network.webSocketFrameSent",
            lambda event: self.frames_sent.append(event["response"]["payloadData"]),
        )


# --------------------------------------------------------------------------- #
# AC-004: visibility through the complete application
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ac004_visibility_stop_start_through_full_app(
    harness: FrontendAppTopologyHarness,
    media_profile: dict[str, Any],
    remote_page: dict[str, Any],
    tmp_path: Path,
) -> None:
    profile_id = media_profile["profile_id"]
    runtime_instance_id = media_profile["runtime_instance_id"]

    pw, browser, context, _ = await launch_browser()
    try:
        await add_session_cookie(context, harness)
        page_a = await context.new_page()
        page_b = await context.new_page()
        wire_a = WireRecorder(page_a, context)
        wire_b = WireRecorder(page_b, context)
        await wire_a.start()
        await wire_b.start()

        await open_session(page_a, harness, profile_id)
        stats_a = await wait_iframe_stats(page_a, name="A")
        await open_session(page_b, harness, profile_id)
        stats_b = await wait_iframe_stats(page_b, name="B")

        initial = await wait_gateway_visibility(
            harness,
            profile_id,
            runtime_instance_id,
            lambda v: (
                v.get("unpaused_video_consumers") == 2
                and v.get("capture_running") is True
            ),
            name="two visible consumers",
        )
        assert initial["has_foreground_viewers"] is True

        # A goes to the background: official client sends STOP_VIDEO for A only.
        await set_iframe_visibility(page_a, True)
        await wait_data_channel_message(page_a, "STOP_VIDEO", timeout=10.0)
        # Fixed settle window so the pause takes effect before sampling; the
        # following frame_delta call is the actual measurement.
        await asyncio.sleep(1.0)

        delta_a, _, _ = await frame_delta(page_a, 2.0)
        assert delta_a == 0, f"hidden page A decoded {delta_a} frames"
        b_delta, _b_before, b_after = await frame_delta(page_b, ACTIVE_SAMPLE_SECONDS)
        b_fps = b_delta / ACTIVE_SAMPLE_SECONDS
        assert b_fps >= ACTIVE_FPS_FLOOR, (
            f"foreground page B dropped to {b_fps:.1f} FPS (delta={b_delta})"
        )
        assert b_after["tab_id"] == stats_b["tab_id"]

        one_hidden = await wait_gateway_visibility(
            harness,
            profile_id,
            runtime_instance_id,
            lambda v: (
                v.get("unpaused_video_consumers") == 1
                and v.get("capture_running") is True
            ),
            name="one hidden consumer",
        )
        assert one_hidden["has_foreground_viewers"] is True

        # B also hidden: capture pauses only after every consumer paused.
        await set_iframe_visibility(page_b, True)
        await wait_data_channel_message(page_b, "STOP_VIDEO", timeout=10.0)
        # Fixed settle window so the pause takes effect before sampling.
        await asyncio.sleep(1.0)
        delta_a_all, _, _ = await frame_delta(page_a, 2.0)
        delta_b_all, _, _ = await frame_delta(page_b, 2.0)
        assert delta_a_all == 0 and delta_b_all == 0, (delta_a_all, delta_b_all)

        all_hidden = await wait_gateway_visibility(
            harness,
            profile_id,
            runtime_instance_id,
            lambda v: (
                v.get("unpaused_video_consumers") == 0
                and v.get("capture_running") is False
            ),
            name="all hidden capture paused",
        )
        assert all_hidden["has_foreground_viewers"] is False

        # Restore A: START_VIDEO and frames flow again.
        await set_iframe_visibility(page_a, False)
        await wait_data_channel_message(page_a, "START_VIDEO", timeout=10.0)
        await wait_iframe_stats(page_a, name="A resumed")
        resumed_delta, _, _ = await frame_delta(page_a, 2.0)
        assert resumed_delta > 0, "visible page did not resume decoding"
        resumed_vis = await wait_gateway_visibility(
            harness,
            profile_id,
            runtime_instance_id,
            lambda v: (
                v.get("unpaused_video_consumers") == 1
                and v.get("capture_running") is True
            ),
            name="one resumed consumer",
        )

        await set_iframe_visibility(page_b, False)
        await wait_data_channel_message(page_b, "START_VIDEO", timeout=10.0)

        # No client-visible activity/visibility frames ever reach the Gateway.
        for name, frames in (("A", wire_a.frames_sent), ("B", wire_b.frames_sent)):
            payloads = "\n".join(frames)
            assert '"cbrowser":"activity"' not in payloads
            assert '"cbrowser": "activity"' not in payloads
            assert '"visibility"' not in payloads

        save_artifacts(
            tmp_path,
            "ac004_visibility",
            {
                "profile_id": profile_id,
                "tab_a": stats_a["tab_id"],
                "tab_b": stats_b["tab_id"],
                "initial_visibility": initial,
                "foreground_b_fps": b_fps,
                "foreground_b_frames": b_delta,
                "hidden_a_frames_2s": delta_a,
                "all_hidden_frames": [delta_a_all, delta_b_all],
                "all_hidden_visibility": all_hidden,
                "one_hidden_visibility": one_hidden,
                "resumed_frames_2s": resumed_delta,
                "resumed_visibility": resumed_vis,
                "a_data_channel_messages": await data_channel_messages(page_a),
                "b_data_channel_messages": await data_channel_messages(page_b),
                "ws_frames_sent_a": wire_a.frames_sent,
                "ws_frames_sent_b": wire_b.frames_sent,
            },
        )
    finally:
        await browser.close()
        await pw.stop()


# --------------------------------------------------------------------------- #
# AC-005: independent product mute through official pipelineControl
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ac005_product_mute_is_independent_per_page(
    harness: FrontendAppTopologyHarness,
    media_profile: dict[str, Any],
    remote_page: dict[str, Any],
    tmp_path: Path,
) -> None:
    profile_id = media_profile["profile_id"]

    pw, browser, context, _ = await launch_browser()
    try:
        await add_session_cookie(context, harness)
        page_a = await context.new_page()
        page_b = await context.new_page()
        await open_session(page_a, harness, profile_id)
        await wait_iframe_stats(page_a, name="A")
        await open_session(page_b, harness, profile_id)
        await wait_iframe_stats(page_b, name="B")

        # Wait for real audio from the remote WebAudio oscillator on both pages.
        audio_a, audio_b = await poll_until(
            lambda: asyncio.gather(iframe_stats(page_a), iframe_stats(page_b)),
            lambda stats: (
                stats[0]
                and stats[1]
                and (stats[0].get("audio") or {}).get("bytesReceived", 0) > 0
                and (stats[1].get("audio") or {}).get("bytesReceived", 0) > 0
            ),
            timeout=30.0,
            interval=0.5,
            description="audible audio on both pages",
        )
        audio_a = audio_a["audio"]
        audio_b = audio_b["audio"]
        assert audio_a and audio_a["bytesReceived"] > 0, audio_a
        assert audio_b and audio_b["bytesReceived"] > 0, audio_b

        # Mute page A through the product control, never by touching audio.muted.
        dc_a_before = await data_channel_messages(page_a)
        await page_a.click('[data-testid="sess-audio-toggle"]')
        assert (
            await page_a.get_attribute(
                '[data-testid="sess-audio-toggle"]', "aria-pressed"
            )
            == "true"
        )
        await wait_data_channel_message(page_a, "STOP_AUDIO", timeout=10.0)
        # Fixed settle window so the mute takes effect before sampling.
        await asyncio.sleep(0.8)

        a_before = (await iframe_stats(page_a))["audio"]
        b_before = (await iframe_stats(page_b))["audio"]
        # Fixed 2 s sampling window: audio byte growth is measured across an
        # interval, not a settled state value.
        await asyncio.sleep(2.0)
        a_after = (await iframe_stats(page_a))["audio"]
        b_after = (await iframe_stats(page_b))["audio"]

        a_growth = a_after["bytesReceived"] - a_before["bytesReceived"]
        b_growth = b_after["bytesReceived"] - b_before["bytesReceived"]
        b_energy_growth = b_after["totalAudioEnergy"] - b_before["totalAudioEnergy"]
        assert a_growth <= 512, f"muted page A still received {a_growth} audio bytes"
        assert b_growth > 0, "page B stopped receiving audio when A muted"
        assert b_energy_growth > 0, "page B audio was silent while A muted"
        assert (
            await page_b.get_attribute(
                '[data-testid="sess-audio-toggle"]', "aria-pressed"
            )
            == "false"
        )

        # Unmute A through the same product control.
        await page_a.click('[data-testid="sess-audio-toggle"]')
        assert (
            await page_a.get_attribute(
                '[data-testid="sess-audio-toggle"]', "aria-pressed"
            )
            == "false"
        )
        await wait_data_channel_message(page_a, "START_AUDIO", timeout=10.0)
        a_resume_before = (await iframe_stats(page_a))["audio"]
        # Fixed 2 s sampling window: audio byte growth after unmute.
        await asyncio.sleep(2.0)
        a_resume_after = (await iframe_stats(page_a))["audio"]
        a_resume_growth = (
            a_resume_after["bytesReceived"] - a_resume_before["bytesReceived"]
        )
        assert a_resume_growth > 0, "unmuted page A did not resume audio"

        b_final = (await iframe_stats(page_b))["audio"]
        assert b_final["bytesReceived"] > b_before["bytesReceived"]

        save_artifacts(
            tmp_path,
            "ac005_product_mute",
            {
                "profile_id": profile_id,
                "dc_messages_before": dc_a_before,
                "dc_messages_after": await data_channel_messages(page_a),
                "a_muted_audio_growth": a_growth,
                "b_audio_growth_while_a_muted": b_growth,
                "b_audio_energy_growth_while_a_muted": b_energy_growth,
                "a_resume_audio_growth": a_resume_growth,
            },
        )
    finally:
        await browser.close()
        await pw.stop()


# --------------------------------------------------------------------------- #
# AC-005: internal browser tab changes are mirrored to both viewers
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ac005_remote_tab_switch_is_visible_on_both_pages(
    harness: FrontendAppTopologyHarness,
    media_profile: dict[str, Any],
    remote_page: dict[str, Any],
    tmp_path: Path,
) -> None:
    profile_id = media_profile["profile_id"]
    container = remote_page["container"]
    original_target = remote_page["target_id"]

    pw, browser, context, _ = await launch_browser()
    try:
        await add_session_cookie(context, harness)
        page_a = await context.new_page()
        page_b = await context.new_page()
        await open_session(page_a, harness, profile_id)
        await wait_iframe_stats(page_a, name="A")
        await open_session(page_b, harness, profile_id)
        await wait_iframe_stats(page_b, name="B")

        # Freeze the motion page on a known solid color first.
        await asyncio.to_thread(
            browser_eval,
            container,
            """(() => {
                window.motionEnabled = false;
                const c = document.getElementById('motion');
                const ctx = c.getContext('2d');
                ctx.fillStyle = '#ff0000';
                ctx.fillRect(0, 0, c.width, c.height);
                return 'red';
            })()""",
            original_target,
        )
        red_a = await wait_iframe_pixel(
            page_a,
            lambda px: pixel_close(px, (255, 0, 0)),
            name="page A red",
        )
        red_b = await wait_iframe_pixel(
            page_b,
            lambda px: pixel_close(px, (255, 0, 0)),
            name="page B red",
        )

        # Open a pure green tab in the remote Browser and bring it to front.
        green_html = (
            "<!doctype html><html><body style='margin:0;background:#00ff00;"
            "width:100vw;height:100vh'></body></html>"
        )
        created = await asyncio.to_thread(
            remote_cdp,
            container,
            [
                {
                    "method": "Target.createTarget",
                    "params": {
                        "url": "data:text/html;charset=utf-8,"
                        + quote(green_html, safe="")
                    },
                }
            ],
        )
        created_target = created[0]["targetId"]
        await asyncio.to_thread(
            remote_cdp,
            container,
            [
                {
                    "method": "Target.activateTarget",
                    "params": {"targetId": created_target},
                }
            ],
        )

        try:
            green_a = await wait_iframe_pixel(
                page_a,
                lambda px: pixel_close(px, (0, 255, 0)),
                timeout=25.0,
                name="page A green after tab switch",
            )
            green_b = await wait_iframe_pixel(
                page_b,
                lambda px: pixel_close(px, (0, 255, 0)),
                timeout=25.0,
                name="page B green after tab switch",
            )
        finally:
            await asyncio.to_thread(
                remote_cdp,
                container,
                [
                    {
                        "method": "Target.closeTarget",
                        "params": {"targetId": created_target},
                    },
                    {
                        "method": "Target.activateTarget",
                        "params": {"targetId": original_target},
                    },
                ],
            )

        restored_a = await wait_iframe_pixel(
            page_a,
            lambda px: pixel_close(px, (255, 0, 0)),
            timeout=25.0,
            name="page A restored red",
        )
        restored_b = await wait_iframe_pixel(
            page_b,
            lambda px: pixel_close(px, (255, 0, 0)),
            timeout=25.0,
            name="page B restored red",
        )

        save_artifacts(
            tmp_path,
            "ac005_tab_switch",
            {
                "profile_id": profile_id,
                "original_target": original_target,
                "switched_target": created_target,
                "red_a": red_a,
                "red_b": red_b,
                "green_a": green_a,
                "green_b": green_b,
                "restored_a": restored_a,
                "restored_b": restored_b,
            },
        )
    finally:
        await browser.close()
        await pw.stop()


# --------------------------------------------------------------------------- #
# AC-005: audio diagnostics positive/negative (silence is not a fault)
# --------------------------------------------------------------------------- #


AUDIO_STATUS_SELECTOR = '[data-testid="sess-diag-audio-status"]'
CONN_STATE_SELECTOR = '[data-testid="sess-diag-conn-state"]'


async def read_audio_status(page: Page) -> str:
    node = await page.query_selector(AUDIO_STATUS_SELECTOR)
    if node is None:
        toggle = await page.query_selector('[data-testid="sess-diag-toggle"]')
        if toggle is not None:
            await toggle.click()
            await page.wait_for_selector(AUDIO_STATUS_SELECTOR, timeout=5000)
            node = await page.query_selector(AUDIO_STATUS_SELECTOR)
    return (await node.inner_text()).strip() if node else ""


async def read_conn_state(page: Page) -> str:
    node = await page.query_selector(CONN_STATE_SELECTOR)
    return (await node.inner_text()).strip() if node else ""


@pytest.mark.asyncio
async def test_ac005_audio_diagnostics_normal_silence_and_link_failure(
    harness: FrontendAppTopologyHarness,
    media_profile: dict[str, Any],
    remote_page: dict[str, Any],
    tmp_path: Path,
) -> None:
    profile_id = media_profile["profile_id"]
    container = remote_page["container"]
    target_id = remote_page["target_id"]

    pw, browser, context, _ = await launch_browser()
    try:
        await add_session_cookie(context, harness)
        page = await context.new_page()
        await open_session(page, harness, profile_id)
        await wait_iframe_stats(page, name="audio diagnostics")

        # Positive: audible oscillator -> normal audio, video stage connected.
        normal_text = await poll_until(
            lambda: read_audio_status(page),
            lambda text: text == "音频正常",
            timeout=30.0,
            interval=0.5,
            description="normal audio diagnostic",
        )
        assert normal_text == "音频正常", normal_text

        stage = await page.get_attribute(
            '[data-testid="sess-page"]', "data-stage"
        )
        assert stage == "connected", stage
        conn_state = await read_conn_state(page)
        assert conn_state == "connected", conn_state

        # Silence must not be reported as a fault: a zero-amplitude but running
        # audio source keeps emitting Opus packets (experiment in the report).
        silence_before = (await iframe_stats(page))["audio"]
        await asyncio.to_thread(
            browser_eval,
            container,
            "window.oscillator.frequency.setValueAtTime(0, 0); 'silent'",
            target_id,
        )
        # Fixed 4 s sampling window: enough silent Opus packets must arrive to
        # prove silence keeps the audio link alive.
        await asyncio.sleep(4.0)
        silence_text = await read_audio_status(page)
        silence_stats = await iframe_stats(page)
        assert silence_text == "音频正常", silence_text
        assert (
            silence_stats["audio"]["packetsReceived"]
            > silence_before["packetsReceived"]
        ), "silent Opus packets stopped flowing"

        # Negative: real audio link failure (PulseAudio stops in the Browser
        # container) while video keeps flowing and the video stage stays connected.
        frames_before_failure = (await iframe_stats(page))["video"]["framesDecoded"]
        await asyncio.to_thread(
            harness.docker_client.containers.get(container).exec_run,
            ["pkill", "-9", "pulseaudio"],
        )
        failure_text = await poll_until(
            lambda: read_audio_status(page),
            lambda text: text == "音频无数据",
            timeout=30.0,
            interval=0.5,
            description="audio link failure diagnostic",
        )
        assert failure_text == "音频无数据", failure_text

        stage = await page.get_attribute(
            '[data-testid="sess-page"]', "data-stage"
        )
        conn_state = await read_conn_state(page)
        assert stage == "connected", stage
        assert conn_state == "connected", conn_state
        # Fixed 1.5 s sampling window: frames must keep arriving after the audio
        # link failure, proving video is unaffected.
        await asyncio.sleep(1.5)
        frames_after_failure = (await iframe_stats(page))["video"]["framesDecoded"]
        assert frames_after_failure > frames_before_failure

        save_artifacts(
            tmp_path,
            "ac005_audio_diagnostics",
            {
                "profile_id": profile_id,
                "normal_status": normal_text,
                "normal_stage": stage,
                "silence_status": silence_text,
                "silence_audio": silence_stats["audio"],
                "failure_status": failure_text,
                "failure_stage": stage,
                "failure_conn_state": conn_state,
                "frames_before_failure": frames_before_failure,
                "frames_after_failure": frames_after_failure,
            },
        )
    finally:
        await browser.close()
        await pw.stop()
