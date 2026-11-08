"""Real quota chain E2E (t028 AC-003): Supervisor -> Gateway -> Agent ->
Stream -> Chrome, with no link replaced by a callback or a mock.

- Direct quota: the production GatewayControlClient posts to the real
  Gateway container's supervisor quota endpoint; the real Stream Agent
  applies the cap; decoded frames in the real Chrome viewer prove the
  cap, the client cannot escape it by raising FPS or resizing, and the
  1920x1080 layout is preserved.
- Motion/static: the streamed media page stops/starts motion and the
  Agent's capture policy follows (8 fps static / 30 fps motion).
- CPU policy: the production ResourceMonitor/ResourcePolicyService
  samples the real Stream container and delivers through the same real
  Gateway client (fixtures/supervisor_resource_probe/stream_monitor).

Target-environment execution is t032's; this module is the collectable
entry with the assertions.  Run via CBROWSER_RUN_E2E=1 scripts/run_gates.sh.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import docker
import pytest
from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT
from cbrowser.supervisor.gateway_client import GatewayControlClient
from gateway_probe.browser_oracle import browser_eval
from gateway_probe.evidence import save_evidence
from gateway_probe.topology import GatewayTopologyHarness
from playwright.async_api import async_playwright
from wait import poll_until, wait_for_log

pytestmark = pytest.mark.serial

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load_stream_monitor():
    spec = importlib.util.spec_from_file_location(
        "supervisor_stream_monitor",
        FIXTURES / "supervisor_resource_probe" / "stream_monitor.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_supervisor_quota_chain_reaches_real_chrome(
    tmp_path: Path,
) -> None:
    harness = GatewayTopologyHarness(tmp_path)
    proof: dict = {}
    try:
        await harness.start()
        profile = await harness.create_and_start_profile("quota_chain_profile")
        profile_id = profile["profile_id"]
        instance_id = profile["runtime_instance_id"]
        browser_cname = profile["browser_container"]
        stream_cname = profile["stream_container"]

        # Load the motion media page inside the real Browser container.
        remote = await asyncio.to_thread(browser_eval, browser_cname, "true")
        target_id = remote["target_id"]

        async def evaluate_remote(expression: str) -> dict:
            return await asyncio.to_thread(
                browser_eval, browser_cname, expression, target_id
            )

        remote_geometry = (
            await evaluate_remote(
                "({width: window.screen.width, height: window.screen.height})"
            )
        )["value"]
        assert remote_geometry == {"width": 1920, "height": 1080}

        # Production Supervisor->Gateway control client against the real
        # Gateway container (host-published port, supervisor token file).
        gw_ports = harness.gateway_container.attrs["NetworkSettings"]["Ports"]
        gw_port = gw_ports[f"{DEFAULT_GATEWAY_PORT}/tcp"][0]["HostPort"]
        control = GatewayControlClient(
            f"http://127.0.0.1:{gw_port}", harness.key_files["gateway"]
        )

        docker_client = docker.from_env()
        stream_container = docker_client.containers.get(stream_cname)

        async def read_stream_logs() -> str:
            return await asyncio.to_thread(
                lambda: stream_container.logs().decode("utf-8", "replace")
            )

        try:
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
                page = await context.new_page()
                # Track the Selkies input data channel so the client-side
                # escape attempt below can drive the same channel the
                # real viewer uses.
                await page.add_init_script(
                    """(() => {
                        const NativePC = window.RTCPeerConnection;
                        window.RTCPeerConnection = function (...args) {
                            const pc = new NativePC(...args);
                            window.__inputChannels = window.__inputChannels || [];
                            pc.addEventListener('datachannel', (event) => {
                                if (event.channel.label === 'input') {
                                    window.__inputChannels.push(event.channel);
                                }
                            });
                            return pc;
                        };
                        window.RTCPeerConnection.prototype = NativePC.prototype;
                        Object.assign(window.RTCPeerConnection, NativePC);
                    })();"""
                )
                await page.goto(harness.origin, wait_until="domcontentloaded")
                login_status = await page.evaluate(
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
                assert login_status == 200, "Login failed"
                await page.goto(
                    f"{harness.origin}/?profile_id={profile_id}#primary",
                    wait_until="domcontentloaded",
                )

                async def stats() -> dict | None:
                    return await page.evaluate(
                        "window.__getWebRTCStats ? window.__getWebRTCStats() : null"
                    )

                await poll_until(
                    stats,
                    lambda s: bool(s)
                    and bool(s.get("video"))
                    and s["video"].get("framesDecoded", 0) > 0,
                    timeout=30.0,
                    description="viewer decoding frames",
                )

                async def frame_window(seconds: float = 2.0) -> int:
                    before = await stats()
                    await asyncio.sleep(seconds)
                    after = await stats()
                    return (
                        after["video"]["framesDecoded"]
                        - before["video"]["framesDecoded"]
                    )

                proof["baseline_frames_2s"] = await frame_window()
                assert proof["baseline_frames_2s"] > 0

                # --- Direct quota through the real Gateway -------------
                logs_before = await read_stream_logs()
                await control.set_quota(profile_id, instance_id, 15)
                await wait_for_log(
                    read_stream_logs,
                    "Updated framerate to 15 fps",
                    offset=len(logs_before),
                    timeout=30.0,
                )
                proof["capped_frames_2s"] = await frame_window()
                assert 0 < proof["capped_frames_2s"] <= 40

                # Client attempts to escape the cap: raise FPS and
                # resize; decoded frames stay capped and the profile
                # geometry is unchanged.
                sent = await page.evaluate(
                    """() => {
                        const channel = (window.__inputChannels || [])
                            .find(c => c.readyState === 'open');
                        if (!channel) return false;
                        channel.send('_arg_fps,30');
                        channel.send('r,640,480');
                        return true;
                    }"""
                )
                assert sent, "viewer input channel unavailable for escape attempt"
                await asyncio.sleep(0.5)
                proof["client_cannot_escape_cap_frames_2s"] = await frame_window()
                assert 0 < proof["client_cannot_escape_cap_frames_2s"] <= 40
                geometry = (
                    await evaluate_remote(
                        "({width: window.screen.width, height: window.screen.height})"
                    )
                )["value"]
                assert geometry == remote_geometry

                logs_before = await read_stream_logs()
                await control.set_quota(profile_id, instance_id, None)
                await wait_for_log(
                    read_stream_logs,
                    "Updated framerate to 30 fps",
                    offset=len(logs_before),
                    timeout=30.0,
                )
                proof["restored_frames_2s"] = await frame_window()
                assert proof["restored_frames_2s"] > proof["capped_frames_2s"]

                # --- Motion / static capture policy --------------------
                logs_before = await read_stream_logs()
                await evaluate_remote("motionEnabled=false; true")
                await wait_for_log(
                    read_stream_logs,
                    "Updated framerate to 8 fps",
                    offset=len(logs_before),
                    timeout=30.0,
                )
                await evaluate_remote("motionEnabled=true; true")
                await wait_for_log(
                    read_stream_logs,
                    "Updated framerate to 30 fps",
                    offset=len(logs_before),
                    timeout=30.0,
                )
                proof["motion_static_policy"] = "8 fps static / 30 fps motion"

                # --- CPU-triggered policy through the same chain -------
                monitor_module = _load_stream_monitor()
                await monitor_module.verify_stream_cpu_policy(
                    stream_cname,
                    profile_id,
                    instance_id,
                    control,
                    frame_window,
                    tmp_path,
                    ownership_label=("com.cbrowser.prefix", harness.prefix),
                )
                cpu_proof = json.loads(
                    (tmp_path / "supervisor_cpu_stream_proof.json").read_text(
                        encoding="utf-8"
                    )
                )
                # Embed the full sampling windows (counters + decisions),
                # not just their count: the retained evidence must stand
                # on its own after the scratch proof file is cleaned up.
                proof["cpu_policy"] = {
                    "deliveries": cpu_proof["deliveries"],
                    "capped_frames_2s": cpu_proof["capped_frames_2s"],
                    "restored_frames_2s": cpu_proof["restored_frames_2s"],
                    "windows": cpu_proof["windows"],
                }
                await browser.close()
        finally:
            await control.close()
            docker_client.close()
    finally:
        save_evidence("quota_chain_proof", proof, tmp_path)
        await harness.cleanup()
