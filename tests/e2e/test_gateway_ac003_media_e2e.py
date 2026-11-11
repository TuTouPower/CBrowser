"""E2E verification of AC-003: Dual Chrome WebRTC, input, gateway recovery."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import docker
import pytest
from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT
from gateway_probe.browser_oracle import browser_eval
from gateway_probe.evidence import save_evidence
from gateway_probe.topology import GatewayTopologyHarness
from playwright.async_api import async_playwright
from wait import poll_until, wait_for_log

pytestmark = [pytest.mark.serial, pytest.mark.e2e_images('CBROWSER_API_TEST_IMAGE', 'CBROWSER_CADDY_TEST_IMAGE', 'CBROWSER_GATEWAY_IMAGE', 'CBROWSER_RUNTIME_TEST_IMAGE', 'CBROWSER_STREAM_TEST_IMAGE', 'CBROWSER_SUPERVISOR_TEST_IMAGE')]


@pytest.mark.asyncio
async def test_ac003_dual_chrome_media_inputs_and_gateway_recovery_v2(
    tmp_path: Path,
) -> None:
    harness = GatewayTopologyHarness(tmp_path)
    evidence: dict = {}
    try:
        await harness.start()

        # 1. Start profile and load remote motion/audio canvas in Browser container
        profile = await harness.create_and_start_profile("ac003_profile")
        profile_id = profile["profile_id"]
        browser_cname = profile["browser_container"]
        stream_cname = profile["stream_container"]

        # Navigate remote browser to media_page.html and retrieve initial identity
        initial_remote = await asyncio.to_thread(browser_eval, browser_cname, "true")
        assert initial_remote["identity"]["pid"], "Missing browser PID"
        initial_pid = initial_remote["identity"]["pid"]
        initial_ticks = initial_remote["identity"]["start_ticks"]
        target_id = initial_remote["target_id"]
        evidence["initial_browser_identity"] = {
            "container": browser_cname,
            "pid": initial_pid,
            "start_ticks": initial_ticks,
        }

        async def evaluate_remote(expression: str) -> dict:
            return await asyncio.to_thread(
                browser_eval, browser_cname, expression, target_id
            )

        # 2. Launch two Chrome pages in headful browser context
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

            # Console log capture
            consoleA: list[str] = []
            consoleB: list[str] = []
            pageA = await context.new_page()
            pageA.on("console", lambda m: consoleA.append(f"[{m.type}] {m.text}"))
            pageA.on("pageerror", lambda e: consoleA.append(f"[error] {e}"))
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

            # Open stream in Page A and Page B
            stream_url = f"{harness.origin}/?profile_id={profile_id}#primary"
            await pageA.goto(stream_url, wait_until="domcontentloaded")

            pageB = await context.new_page()
            pageB.on("console", lambda m: consoleB.append(f"[{m.type}] {m.text}"))
            pageB.on("pageerror", lambda e: consoleB.append(f"[error] {e}"))
            await pageB.goto(stream_url, wait_until="domcontentloaded")

            # Wait for both pages to negotiate and decode WebRTC media
            async def collect_diag(err_msg: str) -> None:
                client = docker.from_env()
                diag_data = {
                    "error": err_msg,
                    "consoleA": consoleA[-30:],
                    "consoleB": consoleB[-30:],
                    "statsA": await pageA.evaluate(
                        "window.__getWebRTCStats ? window.__getWebRTCStats() : null"
                    ),
                    "pcStateA": await pageA.evaluate(
                        "window.__activePC ? {"
                        "connState: window.__activePC.connectionState, "
                        "iceState: window.__activePC.iceConnectionState, "
                        "gatherState: window.__activePC.iceGatheringState, "
                        "sigState: window.__activePC.signalingState} : null"
                    ),
                    "statsB": await pageB.evaluate(
                        "window.__getWebRTCStats ? window.__getWebRTCStats() : null"
                    ),
                    "pcStateB": await pageB.evaluate(
                        "window.__activePC ? {"
                        "connState: window.__activePC.connectionState, "
                        "iceState: window.__activePC.iceConnectionState, "
                        "gatherState: window.__activePC.iceGatheringState, "
                        "sigState: window.__activePC.signalingState} : null"
                    ),
                }
                for c_role, c_name in [
                    ("stream", stream_cname),
                    ("browser", browser_cname),
                    ("gateway", harness.gateway_container.name),
                    ("supervisor", harness.supervisor_container.name),
                    ("caddy", harness.caddy_container.name),
                ]:
                    try:
                        box = client.containers.get(c_name)
                        diag_data[f"{c_role}_logs"] = box.logs(tail=50).decode("utf-8")
                    except (
                        Exception  # noqa: BLE001 - failure diagnosis container log dump
                    ) as ex:
                        err_type = type(ex).__name__
                        diag_data[f"{c_role}_logs"] = f"Failed to get logs: {err_type}"
                save_evidence(
                    "ac003_failure_diag", diag_data, target_dir=tmp_path / "evidence"
                )

            async def wait_for_decode(page, name: str, timeout: float = 25.0):
                deadline = asyncio.get_running_loop().time() + timeout
                while asyncio.get_running_loop().time() < deadline:
                    stats = await page.evaluate(
                        "window.__getWebRTCStats ? window.__getWebRTCStats() : null"
                    )
                    if (
                        stats
                        and stats.get("video")
                        and stats["video"].get("framesDecoded", 0) > 0
                        and stats.get("pair")
                        and stats["pair"].get("remoteAddress")
                    ):
                        return stats
                    await asyncio.sleep(0.3)
                err_msg = f"Page {name} failed to decode video frames in {timeout}s"
                await collect_diag(err_msg)
                raise TimeoutError(err_msg)

            statsA1 = await wait_for_decode(pageA, "Page A")
            statsB1 = await wait_for_decode(pageB, "Page B")

            # Fixed 2 s sampling window: frame growth is measured across an
            # interval, which cannot be replaced by polling for a settled value.
            await asyncio.sleep(2.0)
            statsA2 = await pageA.evaluate("window.__getWebRTCStats()")
            statsB2 = await pageB.evaluate("window.__getWebRTCStats()")

            delta_frames_A = (
                statsA2["video"]["framesDecoded"] - statsA1["video"]["framesDecoded"]
            )
            delta_frames_B = (
                statsB2["video"]["framesDecoded"] - statsB1["video"]["framesDecoded"]
            )
            assert delta_frames_A > 0, f"Page A frames must grow: {delta_frames_A}"
            assert delta_frames_B > 0, f"Page B frames must grow: {delta_frames_B}"

            # Verify non-zero audio energy or audio bytes
            audio_A = statsA2["audio"]
            audio_B = statsB2["audio"]
            assert audio_A["totalAudioEnergy"] > 0 or audio_A["bytesReceived"] > 0, (
                f"Page A non-zero audio required: {audio_A}"
            )
            assert audio_B["totalAudioEnergy"] > 0 or audio_B["bytesReceived"] > 0, (
                f"Page B non-zero audio required: {audio_B}"
            )

            # Verify distinct client_tab_id
            tab_id_A = statsA2["tab_id"]
            tab_id_B = statsB2["tab_id"]
            assert tab_id_A and tab_id_B, "Both pages must have client_tab_id"
            assert tab_id_A != tab_id_B, (
                f"Tab IDs must be distinct: {tab_id_A} == {tab_id_B}"
            )

            # Verify selected candidate pair is NOT Gateway address
            remote_A = statsA2["pair"]["remoteAddress"]
            remote_port_A = statsA2["pair"]["remotePort"]
            assert remote_A != harness.gateway_ip, (
                f"Selected remote candidate must not be Gateway IP {harness.gateway_ip}"
            )
            assert remote_port_A != DEFAULT_GATEWAY_PORT, (
                f"Selected remote port must not be Gateway port {DEFAULT_GATEWAY_PORT}"
            )

            evidence["dual_page_media"] = {
                "pageA_tab_id": tab_id_A,
                "pageB_tab_id": tab_id_B,
                "pageA_frames_growth": delta_frames_A,
                "pageB_frames_growth": delta_frames_B,
                "pageA_audio": audio_A,
                "pageB_audio": audio_B,
                "selected_candidate_pair_A": statsA2["pair"],
                "selected_candidate_pair_B": statsB2["pair"],
            }

            # 3. Remote input typing: both pages type into remote input (no lock)
            async def prepare_remote_input():
                await evaluate_remote("""(() => {
                    const input = document.getElementById('probe_input');
                    if (input) {
                        input.value = '';
                        window.remoteEvents = [];
                        input.focus();
                    }
                    return true;
                })()""")

            async def remote_value():
                res = await evaluate_remote(
                    "document.getElementById('probe_input') ? "
                    "document.getElementById('probe_input').value : null"
                )
                return res.get("value")

            # First: single-page positive control (page A only)
            await prepare_remote_input()
            await pageA.locator("#overlayInput").focus()
            await pageA.keyboard.press("Digit1")
            single_val = None
            try:
                single_val = await poll_until(
                    remote_value,
                    lambda value: value == "1",
                    timeout=2.5,
                    interval=0.1,
                    description="first-page remote input",
                )
            except TimeoutError:
                single_val = await remote_value()
            if single_val != "1":
                diag_rem = await evaluate_remote(
                    "({active: document.activeElement ? "
                    "document.activeElement.id : null, "
                    "events: window.remoteEvents, "
                    "focused: document.hasFocus()})"
                )
                active_A = await pageA.evaluate(
                    "document.activeElement ? document.activeElement.id : null"
                )
                sentA = await pageA.evaluate("window.__sentDataChannelMessages")
                stream_box = harness.docker_client.containers.get(stream_cname)
                s_logs = stream_box.logs(tail=30).decode("utf-8")
                raise AssertionError(
                    f"First-page typing failed: val={single_val}, "
                    f"diag_rem={diag_rem}, active_A={active_A}, "
                    f"sentA={sentA[-5:] if sentA else None}, stream_logs={s_logs}"
                )
            assert single_val == "1", "First page single typing failed"

            # Second: concurrent typing from both pages (both reach same input)
            await prepare_remote_input()
            await pageA.locator("#overlayInput").focus()
            await pageA.keyboard.press("Digit1")
            await pageB.locator("#overlayInput").focus()
            await pageB.keyboard.press("Digit2")
            concurrent_val = None
            try:
                concurrent_val = await poll_until(
                    remote_value,
                    lambda value: value == "12",
                    timeout=2.5,
                    interval=0.1,
                    description="concurrent remote input from both pages",
                )
            except TimeoutError:
                concurrent_val = await remote_value()
            if concurrent_val != "12":
                diag_rem = await evaluate_remote(
                    "({active: document.activeElement ? "
                    "document.activeElement.id : null, "
                    "events: window.remoteEvents, "
                    "focused: document.hasFocus()})"
                )
                active_A = await pageA.evaluate(
                    "document.activeElement ? document.activeElement.id : null"
                )
                active_B = await pageB.evaluate(
                    "document.activeElement ? document.activeElement.id : null"
                )
                sentA = await pageA.evaluate("window.__sentDataChannelMessages")
                sentB = await pageB.evaluate("window.__sentDataChannelMessages")
                stream_box = harness.docker_client.containers.get(stream_cname)
                s_logs = stream_box.logs(tail=30).decode("utf-8")
                raise AssertionError(
                    f"Concurrent typing failed: val={concurrent_val}, "
                    f"diag_rem={diag_rem}, active_A={active_A}, active_B={active_B}, "
                    f"sentA={sentA[-5:] if sentA else None}, "
                    f"sentB={sentB[-5:] if sentB else None}, stream_logs={s_logs}"
                )
            assert concurrent_val == "12", "Both pages must reach remote input"
            evidence["concurrent_inputs"] = {"remote_value": concurrent_val}

            # 4. Close Page A, verify Page B frames continue growing
            await pageA.close()
            before_close_B = await pageB.evaluate("window.__getWebRTCStats()")
            # Fixed 2 s sampling window: the assertion is that frames keep
            # arriving across an interval, not that a state value settles.
            await asyncio.sleep(2.0)
            after_close_B = await pageB.evaluate("window.__getWebRTCStats()")
            post_close_delta = (
                after_close_B["video"]["framesDecoded"]
                - before_close_B["video"]["framesDecoded"]
            )
            assert post_close_delta > 0, (
                f"Page B frames must grow after Page A closed: {post_close_delta}"
            )
            evidence["page_b_after_page_a_close"] = {
                "frames_growth_2s": post_close_delta
            }

            # 5. Gateway SIGKILL -> verify browser PID/starttime unchanged
            client = docker.from_env()
            gw_box = harness.gateway_container
            stream_box = harness.docker_client.containers.get(stream_cname)

            async def read_stream_logs() -> str:
                return await asyncio.to_thread(
                    lambda: stream_box.logs().decode("utf-8")
                )

            stream_log_offset = len(await read_stream_logs())
            gw_box.kill(signal="KILL")

            # Check Browser container running & process identity intact
            b_box = client.containers.get(browser_cname)
            assert b_box.status == "running", "Browser container must remain running"

            after_kill_remote = await evaluate_remote("true")
            assert after_kill_remote["identity"]["pid"] == initial_pid, (
                f"Browser PID changed: {initial_pid} != "
                f"{after_kill_remote['identity']['pid']}"
            )
            assert after_kill_remote["identity"]["start_ticks"] == initial_ticks, (
                f"Browser start_ticks changed: {initial_ticks} != "
                f"{after_kill_remote['identity']['start_ticks']}"
            )
            evidence["browser_after_gateway_kill"] = {
                "container_status": b_box.status,
                "pid": after_kill_remote["identity"]["pid"],
                "start_ticks": after_kill_remote["identity"]["start_ticks"],
            }

            # Wait for Stream Agent to observe Gateway disconnect and enter backoff
            await wait_for_log(
                read_stream_logs,
                "backoff",
                timeout=10.0,
                interval=0.2,
                offset=stream_log_offset,
                description="Stream Agent backoff after Gateway kill",
            )

            # Restart Gateway container
            gw_box.restart()

            # Wait for Stream Agent to re-register (appears at least twice in logs)
            try:
                reconnect_logs = await poll_until(
                    read_stream_logs,
                    lambda logs: logs[stream_log_offset:].count(
                        "StreamAgent registered with Gateway"
                    ) >= 1,
                    timeout=30.0,
                    interval=0.5,
                    description="Stream Agent re-registration with restarted Gateway",
                )
            except TimeoutError:
                gw_logs_after = gw_box.logs(tail=40).decode("utf-8")
                s_logs_after = stream_box.logs(tail=40).decode("utf-8")
                raise AssertionError(
                    f"Stream Agent did not re-register with restarted Gateway.\n"
                    f"Gateway logs:\n{gw_logs_after}\nStream logs:\n{s_logs_after}"
                ) from None
            reconnect_logs = reconnect_logs[stream_log_offset:]
            # Extract reconnect / backoff lines as evidence
            backoff_lines = [
                line
                for line in reconnect_logs.splitlines()
                if "backoff" in line
                or "Reconnecting" in line
                or "StreamAgent registered with Gateway" in line
            ]
            assert any("backoff" in line for line in backoff_lines), (
                "Backoff lines must exist in stream log"
            )
            evidence["stream_agent_backoff_recovery"] = backoff_lines

            # Reload Page B, verify it reconnects and continues decoding
            await pageB.reload(wait_until="domcontentloaded")
            recovered_stats = await wait_for_decode(
                pageB, "Page B Recovered", timeout=25.0
            )
            # Fixed 1.5 s sampling window: decoded frames must grow across the
            # interval after recovery.
            await asyncio.sleep(1.5)
            recovered_stats_2 = await pageB.evaluate("window.__getWebRTCStats()")
            rec_delta = (
                recovered_stats_2["video"]["framesDecoded"]
                - recovered_stats["video"]["framesDecoded"]
            )
            assert rec_delta > 0, (
                f"Page B must decode frames after Gateway recovery: {rec_delta}"
            )
            evidence["page_b_recovered_media"] = {
                "frames_growth": rec_delta,
                "pair": recovered_stats_2["pair"],
            }

            await browser.close()

        save_evidence(
            "ac003_media_evidence", evidence, target_dir=tmp_path / "evidence"
        )

    finally:
        try:
            if sys.exc_info()[0] is not None and harness.supervisor_container is not None:
                from scripts.redact_evidence import redact

                try:
                    logs = await asyncio.wait_for(
                        asyncio.to_thread(harness.supervisor_container.logs, tail=300),
                        timeout=30,
                    )
                    (tmp_path / "supervisor_failure.log").write_text(
                        redact(logs.decode("utf-8", "replace")), encoding="utf-8"
                    )
                except Exception:  # noqa: BLE001 - diagnostics are best-effort and must not mask the original failure.
                    pass
        finally:
            await harness.cleanup()
