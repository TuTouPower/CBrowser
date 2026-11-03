"""E2E verification of AC-007: Selkies STOP/START_VIDEO & visibility endpoint."""

from __future__ import annotations

import asyncio
from pathlib import Path

import docker
import httpx
import pytest
from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT
from gateway_probe.browser_oracle import browser_eval
from gateway_probe.evidence import save_evidence
from gateway_probe.topology import GatewayTopologyHarness
from playwright.async_api import async_playwright
from wait import poll_until, wait_until


@pytest.mark.asyncio
async def test_ac007_tab_visibility_pause_resume_and_gateway_endpoint(
    tmp_path: Path,
) -> None:
    harness = GatewayTopologyHarness(tmp_path)
    evidence: dict = {}
    try:
        await harness.start()

        # Start profile and remote motion canvas
        profile = await harness.create_and_start_profile("ac007_profile")
        profile_id = profile["profile_id"]
        runtime_instance_id = profile["runtime_instance_id"]
        browser_cname = profile["browser_container"]
        stream_cname = profile["stream_container"]

        await asyncio.to_thread(browser_eval, browser_cname, "true")

        gw_port = harness.gateway_container.attrs["NetworkSettings"]["Ports"][
            f"{DEFAULT_GATEWAY_PORT}/tcp"
        ][0]["HostPort"]
        gw_internal_url = f"http://127.0.0.1:{gw_port}"
        gw_headers = {"Authorization": f"Bearer {harness.keys['gateway']}"}

        async def get_visibility() -> dict:
            async with httpx.AsyncClient(
                base_url=gw_internal_url, headers=gw_headers, trust_env=False
            ) as client:
                resp = await client.get(
                    f"/gateway/v1/internal/profiles/{profile_id}/visibility",
                    params={"runtime_instance_id": runtime_instance_id},
                )
                assert resp.status_code == 200, (
                    f"Visibility endpoint error: {resp.status_code} {resp.text}"
                )
                return resp.json()

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

            # Log in through API to establish session cookie
            auth_headers = await harness.login_api()
            cookie_val = auth_headers["Cookie"].split("cbrowser_session=")[1]
            await context.add_cookies(
                [
                    {
                        "name": "cbrowser_session",
                        "value": cookie_val,
                        "url": harness.origin,
                    }
                ]
            )

            consoleA: list[str] = []
            consoleB: list[str] = []

            stream_url = f"{harness.origin}/?profile_id={profile_id}#primary"
            pageA = await context.new_page()
            pageA.on("console", lambda m: consoleA.append(f"[{m.type}] {m.text}"))
            await pageA.goto(stream_url, wait_until="domcontentloaded")

            pageB = await context.new_page()
            pageB.on("console", lambda m: consoleB.append(f"[{m.type}] {m.text}"))
            await pageB.goto(stream_url, wait_until="domcontentloaded")

            # Wait for both pages to decode video frames
            async def wait_for_decode(page, name: str, timeout: float = 45.0):
                deadline = asyncio.get_running_loop().time() + timeout
                last_s = None
                while asyncio.get_running_loop().time() < deadline:
                    stats = await page.evaluate(
                        "window.__getWebRTCStats ? window.__getWebRTCStats() : null"
                    )
                    last_s = stats
                    if (
                        stats
                        and stats.get("video")
                        and stats["video"].get("framesDecoded", 0) > 0
                    ):
                        return stats
                    await asyncio.sleep(0.3)
                s_box = harness.docker_client.containers.get(stream_cname)
                g_box = harness.gateway_container
                raise TimeoutError(
                    f"Page {name} failed to decode video frames in {timeout}s.\n"
                    f"last_stats={last_s}\nconsoleA={consoleA[-15:]}\n"
                    f"consoleB={consoleB[-15:]}\n"
                    f"stream_logs:\n{s_box.logs(tail=20).decode('utf-8')}\n"
                    f"gateway_logs:\n{g_box.logs(tail=20).decode('utf-8')}"
                )

            await wait_for_decode(pageA, "Page A")
            await wait_for_decode(pageB, "Page B")

            client = docker.from_env()
            stream_box = client.containers.get(stream_cname)

            async def read_stream_logs() -> str:
                return await asyncio.to_thread(
                    lambda: stream_box.logs().decode("utf-8")
                )

            # Wait until initial state has 2 unpaused video consumers
            initial_vis = await poll_until(
                get_visibility,
                lambda vis: vis.get("unpaused_video_consumers") == 2,
                timeout=15.0,
                interval=0.5,
                description="two unpaused video consumers",
            )
            assert initial_vis["unpaused_video_consumers"] == 2
            assert initial_vis["capture_running"] is True
            assert initial_vis["has_foreground_viewers"] is True
            evidence["initial_visibility"] = initial_vis

            # --- Phase 1: One foreground (Page A), one background (Page B hidden) ---
            # Trigger official visibilitychange on Page B via property override
            logs_before_p1 = len(stream_box.logs().decode("utf-8"))
            await pageB.evaluate("""() => {
                Object.defineProperty(
                    document, 'visibilityState',
                    {configurable: true, get: () => 'hidden'}
                );
                Object.defineProperty(
                    document, 'hidden', {configurable: true, get: () => true}
                );
                document.dispatchEvent(new Event('visibilitychange'));
            }""")

            # Verify Page B console logged STOP_VIDEO. Selkies debounces the
            # visibilitychange event for 250 ms before sending STOP_VIDEO.
            await wait_until(
                lambda: any("sent STOP_VIDEO" in line for line in consoleB),
                timeout=5.0,
                interval=0.05,
                description="Page B STOP_VIDEO console log",
            )
            assert any("sent STOP_VIDEO" in line for line in consoleB), (
                f"Page B must log STOP_VIDEO: {consoleB[-10:]}"
            )

            # Verify Stream container hooked handle_video_consumer_active active=False
            s_logs_all = await poll_until(
                read_stream_logs,
                lambda text: any(
                    "Hooked handle_video_consumer_active: peer=" in line
                    and "active=False" in line
                    for line in text[logs_before_p1:].splitlines()
                ),
                timeout=5.0,
                interval=0.1,
                description="Stream STOP_VIDEO hook",
            )
            s_logs = s_logs_all[logs_before_p1:]
            assert any(
                "Hooked handle_video_consumer_active: peer=" in line
                and "active=False" in line
                for line in s_logs.splitlines()
            ), f"Stream logs missing STOP_VIDEO hook: {s_logs[-500:]}"

            # Measure frames: Page B frames delta is 0, Page A frames delta >= 40
            statsA_p1_start = await pageA.evaluate("window.__getWebRTCStats()")
            statsB_p1_start = await pageB.evaluate("window.__getWebRTCStats()")
            # Fixed 2 s sampling window: the assertion measures frame growth
            # across an interval, not a settled state value.
            await asyncio.sleep(2.0)
            statsA_p1_end = await pageA.evaluate("window.__getWebRTCStats()")
            statsB_p1_end = await pageB.evaluate("window.__getWebRTCStats()")

            delta_A_p1 = (
                statsA_p1_end["video"]["framesDecoded"]
                - statsA_p1_start["video"]["framesDecoded"]
            )
            delta_B_p1 = (
                statsB_p1_end["video"]["framesDecoded"]
                - statsB_p1_start["video"]["framesDecoded"]
            )

            assert delta_B_p1 == 0, f"Page B delta must be 0, got {delta_B_p1}"
            assert delta_A_p1 >= 40, f"Page A frames must be >= 40, got {delta_A_p1}"

            # Wait for Gateway visibility endpoint update (within heartbeat interval)
            p1_vis = await poll_until(
                get_visibility,
                lambda vis: vis.get("unpaused_video_consumers") == 1,
                timeout=15.0,
                interval=0.5,
                description="one unpaused video consumer",
            )

            assert p1_vis["unpaused_video_consumers"] == 1
            assert p1_vis["capture_running"] is True
            assert p1_vis["has_foreground_viewers"] is True
            evidence["phase1_one_background"] = {
                "pageA_2s_frames": delta_A_p1,
                "pageB_2s_frames": delta_B_p1,
                "visibility_endpoint": p1_vis,
            }

            # --- Phase 2: All background (both Page A and Page B hidden) ---
            await pageA.evaluate("""() => {
                Object.defineProperty(
                    document, 'visibilityState',
                    {configurable: true, get: () => 'hidden'}
                );
                Object.defineProperty(
                    document, 'hidden', {configurable: true, get: () => true}
                );
                document.dispatchEvent(new Event('visibilitychange'));
            }""")
            await wait_until(
                lambda: any("sent STOP_VIDEO" in line for line in consoleA),
                timeout=5.0,
                interval=0.05,
                description="Page A STOP_VIDEO console log",
            )
            assert any("sent STOP_VIDEO" in line for line in consoleA), (
                f"Page A must log STOP_VIDEO: {consoleA[-10:]}"
            )

            # Measure frames over 2 seconds: both pages frame deltas are 0
            statsA_p2_start = await pageA.evaluate("window.__getWebRTCStats()")
            statsB_p2_start = await pageB.evaluate("window.__getWebRTCStats()")
            # Fixed 2 s sampling window: frame growth is measured across an
            # interval, not a settled state value.
            await asyncio.sleep(2.0)
            statsA_p2_end = await pageA.evaluate("window.__getWebRTCStats()")
            statsB_p2_end = await pageB.evaluate("window.__getWebRTCStats()")

            delta_A_p2 = (
                statsA_p2_end["video"]["framesDecoded"]
                - statsA_p2_start["video"]["framesDecoded"]
            )
            delta_B_p2 = (
                statsB_p2_end["video"]["framesDecoded"]
                - statsB_p2_start["video"]["framesDecoded"]
            )

            assert delta_A_p2 == 0, f"Page A frames must be 0, got {delta_A_p2}"
            assert delta_B_p2 == 0, f"Page B frames must be 0, got {delta_B_p2}"

            # Wait for Gateway visibility endpoint update
            p2_vis = await poll_until(
                get_visibility,
                lambda vis: vis.get("unpaused_video_consumers") == 0,
                timeout=15.0,
                interval=0.5,
                description="zero unpaused video consumers",
            )

            assert p2_vis["unpaused_video_consumers"] == 0
            assert p2_vis["capture_running"] is False
            assert p2_vis["has_foreground_viewers"] is False

            # Verify Stream container logged capture pause
            s_logs_p2 = stream_box.logs().decode("utf-8")
            assert (
                "pause_screen_capture" in s_logs_p2
                or "Capture paused" in s_logs_p2
                or "stopped" in s_logs_p2
            ), f"Stream logs missing capture pause: {s_logs_p2[-500:]}"

            evidence["phase2_all_background"] = {
                "pageA_2s_frames": delta_A_p2,
                "pageB_2s_frames": delta_B_p2,
                "visibility_endpoint": p2_vis,
            }

            # --- Phase 3: Resume visibility on Page A ---
            before_resume_keyframes = statsA_p2_end["video"]["keyFramesDecoded"]
            logs_before_p3 = len(stream_box.logs().decode("utf-8"))
            await pageA.evaluate("""() => {
                Object.defineProperty(
                    document, 'visibilityState',
                    {configurable: true, get: () => 'visible'}
                );
                Object.defineProperty(
                    document, 'hidden', {configurable: true, get: () => false}
                );
                document.dispatchEvent(new Event('visibilitychange'));
            }""")
            await wait_until(
                lambda: any("sent START_VIDEO" in line for line in consoleA),
                timeout=5.0,
                interval=0.05,
                description="Page A START_VIDEO console log",
            )

            assert any("sent START_VIDEO" in line for line in consoleA), (
                f"Page A must log START_VIDEO: {consoleA[-10:]}"
            )

            # Wait for frame growth on Page A
            statsA_p3 = await poll_until(
                lambda: pageA.evaluate("window.__getWebRTCStats()"),
                lambda stats: (
                    stats["video"]["framesDecoded"]
                    > statsA_p2_end["video"]["framesDecoded"]
                    and stats["video"]["keyFramesDecoded"] > before_resume_keyframes
                ),
                timeout=15.0,
                interval=0.3,
                description="Page A decoding frames after resume",
            )

            assert statsA_p3 is not None, "Page A failed to resume decoding frames"

            # Stream logs show set_framerate(8.0) first, then resume
            s_logs_p3_all = await poll_until(
                read_stream_logs,
                lambda text: (
                    any(
                        "Hooked handle_video_consumer_active: peer=" in line
                        and "active=True" in line
                        for line in text[logs_before_p3:].splitlines()
                    )
                    and "set_framerate(8.0) first, then resume"
                    in text[logs_before_p3:]
                ),
                timeout=5.0,
                interval=0.1,
                description="Stream START_VIDEO hook and resume log",
            )
            s_logs_p3 = s_logs_p3_all[logs_before_p3:]
            assert any(
                "Hooked handle_video_consumer_active: peer=" in line
                and "active=True" in line
                for line in s_logs_p3.splitlines()
            ), f"Stream logs missing START_VIDEO hook: {s_logs_p3[-500:]}"
            assert "set_framerate(8.0) first, then resume" in s_logs_p3, (
                f"Stream logs missing resume log: {s_logs_p3[-500:]}"
            )

            # Gateway visibility endpoint updates back to 1
            p3_vis = await poll_until(
                get_visibility,
                lambda vis: vis.get("unpaused_video_consumers") == 1,
                timeout=15.0,
                interval=0.5,
                description="one unpaused video consumer after resume",
            )

            assert p3_vis["unpaused_video_consumers"] == 1
            assert p3_vis["capture_running"] is True
            assert p3_vis["has_foreground_viewers"] is True

            evidence["phase3_resume_foreground"] = {
                "pageA_recovered_keyframes": statsA_p3["video"]["keyFramesDecoded"],
                "visibility_endpoint": p3_vis,
            }

            # --- Phase 4: Disconnect Page B ---
            # Page B was already hidden, so its disconnect must leave Page A's
            # foreground stream untouched.
            await pageB.close()

            # Page A continues unaffected
            statsA_p4_start = await pageA.evaluate("window.__getWebRTCStats()")
            # Fixed 1.5 s sampling window: frames must grow across the interval.
            await asyncio.sleep(1.5)
            statsA_p4_end = await pageA.evaluate("window.__getWebRTCStats()")
            assert (
                statsA_p4_end["video"]["framesDecoded"]
                > statsA_p4_start["video"]["framesDecoded"]
            )

            # --- Phase 5: Negative control - injecting cbrowser activity frames ---
            await pageA.evaluate("""() => {
                const ws = window.__last_ws;
                if (!ws || ws.readyState !== WebSocket.OPEN) {
                    throw new Error("activity sentinel channel is not open");
                }
                ws.send(JSON.stringify({
                    cbrowser: "activity",
                    visible: true,
                    active: true
                }));
            }""")
            # Fixed 1 s settle window for a negative assertion: the absence of
            # visibility_update log lines must hold over an interval.
            await asyncio.sleep(1.0)

            gw_logs_end = harness.gateway_container.logs().decode("utf-8")
            stream_logs_end = stream_box.logs().decode("utf-8")
            assert "visibility_update" not in gw_logs_end
            assert "visibility_update" not in stream_logs_end

            vis_negative = await get_visibility()
            assert vis_negative["unpaused_video_consumers"] == 1, (
                "Activity frame injection must not alter visibility state"
            )

            evidence["phase5_negative_injection"] = {
                "visibility_endpoint_unchanged": vis_negative,
                "no_visibility_update_in_logs": True,
            }

            save_evidence(
                "ac007_visibility_evidence", evidence, target_dir=tmp_path / "evidence"
            )

            await browser.close()

    finally:
        await harness.cleanup()
