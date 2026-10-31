"""E2E verification of AC-005: Relay-only WebRTC, TURN credential rotations."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from gateway_probe.browser_oracle import browser_eval
from gateway_probe.evidence import save_evidence
from gateway_probe.topology import GatewayTopologyHarness
from playwright.async_api import async_playwright


@pytest.mark.asyncio
async def test_ac005_relay_only_turn_rotations(tmp_path: Path) -> None:
    is_negative = os.environ.get("CBROWSER_TEST_NEGATIVE_TURN_QUOTA") == "1"

    # Sufficient margin for initial relay connection to establish before first restart:
    # created_at -> t=0
    # Container start & page connect: ~15-20s
    # Initial media decoded: ~20-25s
    # Next generation generated: t=40s
    # ICE restart triggers: t=45s (120s lifetime - 75s lead time)
    # Gen 2 commits: ~t=50s
    # Gen 3 generates at t=80s, triggers at t=85s, commits at ~t=90s
    harness = GatewayTopologyHarness(
        tmp_path,
        webrtc_mode="relay-only",
        credential_lifetime_sec=120.0,
        generation_interval_sec=40.0,
        ice_restart_lead_time_sec=75.0,
    )
    evidence: dict = {}
    try:
        await harness.start()

        # Start profile and remote motion canvas
        profile = await harness.create_and_start_profile("ac005_relay_profile")
        profile_id = profile["profile_id"]
        browser_cname = profile["browser_container"]
        stream_cname = profile["stream_container"]

        initial_remote = await asyncio.to_thread(browser_eval, browser_cname, "true")
        target_id = initial_remote["target_id"]

        async def evaluate_remote(expression: str) -> dict:
            return await asyncio.to_thread(
                browser_eval, browser_cname, expression, target_id
            )

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

            # Establish session cookie
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

            page = await context.new_page()
            url_flags = "webrtc_mode=relay-only"
            if is_negative:
                url_flags += "&negative_turn_reject=1"
            stream_url = (
                f"{harness.origin}/?profile_id={profile_id}&{url_flags}#primary"
            )
            await page.goto(stream_url, wait_until="domcontentloaded")

            # Wait for WebRTC media decoding on initial generation
            stats1 = None
            last_stats = None
            for _ in range(60):
                stats = await page.evaluate(
                    "window.__getWebRTCStats ? window.__getWebRTCStats() : null"
                )
                last_stats = stats
                if (
                    stats
                    and stats.get("video")
                    and stats["video"].get("framesDecoded", 0) > 0
                    and stats.get("connected")
                    and stats.get("pair")
                    and stats["pair"].get("localType") == "relay"
                    and stats["pair"].get("remoteType") == "relay"
                ):
                    stats1 = stats
                    break
                await asyncio.sleep(0.5)

            if stats1 is None:
                pc_info = await page.evaluate("""() => ({
                    pc: window.__activePC ? {
                        conn: window.__activePC.connectionState,
                        ice: window.__activePC.iceConnectionState,
                        cfg: window.__activePC.getConfiguration(),
                    } : null,
                    cfgRtc: window.__latestRtcConfig,
                })""")
                s_box = harness.docker_client.containers.get(stream_cname)
                g_box = harness.gateway_container
                t_box = harness.coturn_container
                raise AssertionError(
                    f"Failed to establish initial connection.\n"
                    f"last_stats={last_stats}\npc_info={pc_info}\n"
                    f"coturn_logs:\n{t_box.logs(tail=20).decode('utf-8')}\n"
                    f"gateway_logs:\n{g_box.logs(tail=20).decode('utf-8')}\n"
                    f"stream_logs:\n{s_box.logs(tail=20).decode('utf-8')}"
                )
            # Save initial object references in page context
            await page.evaluate("""() => {
                window.__rotationPC = window.__activePC;
                window.__rotationCount = window.__pcs ? window.__pcs.length : 1;
                window.__rotationTracks = (
                    window.__activePC.getReceivers().map(r => r.track)
                );
            }""")

            evidence["generation_1"] = {
                "pair": stats1["pair"],
                "frames": stats1["video"]["framesDecoded"],
                "audio": stats1["audio"],
            }

            stream_box = harness.docker_client.containers.get(stream_cname)
            gw_box = harness.gateway_container
            coturn_box = harness.coturn_container

            pair_stats_js = """async () => {
                const pc = window.__rotationPC || window.__activePC;
                if (!pc) return null;
                const report = await pc.getStats();
                const transport = [...report.values()].find(
                    x => x.type === 'transport' && x.selectedCandidatePairId);
                const pair = transport && report.get(transport.selectedCandidatePairId);
                const local = pair && report.get(pair.localCandidateId);
                const remote = pair && report.get(pair.remoteCandidateId);
                return pair ? {
                    localType: local ? local.candidateType : null,
                    remoteType: remote ? remote.candidateType : null,
                    remoteUfrag: remote ? remote.usernameFragment : null,
                    bytesReceived: pair.bytesReceived || 0,
                    remotePort: remote ? remote.port : null,
                    localPort: local ? local.port : null,
                } : null;
            }"""

            # Observe Generation 2 and Generation 3 rotations
            observed_generations: list[dict] = []
            for target_gen in (2, 3):
                # 1. Obtain offer ufrag for target_gen from window.__restartOffers
                offer_ufrag = None
                for _ in range(120):
                    offers = await page.evaluate("window.__restartOffers || []")
                    match = next(
                        (o for o in offers if o.get("generation") == target_gen),
                        None,
                    )
                    if match and match.get("ufrag"):
                        offer_ufrag = match["ufrag"]
                        break
                    await asyncio.sleep(0.5)

                assert offer_ufrag is not None, (
                    f"No restart offer recorded for Gen {target_gen}"
                )

                # 2. Negative mode: Generation 2 must not commit; Gateway backs off
                if is_negative:
                    # Wait for Gateway to log backoff retry
                    backoff_logged = False
                    gw_logs_neg = ""
                    for _ in range(60):
                        gw_logs_neg = gw_box.logs(stdout=True, stderr=True).decode(
                            "utf-8"
                        )
                        if "Scheduled ICE restart backoff" in gw_logs_neg:
                            backoff_logged = True
                            break
                        await asyncio.sleep(0.5)

                    # Check coturn logs for 401 Unauthorized rejection
                    coturn_logs = coturn_box.logs(stdout=True, stderr=True).decode(
                        "utf-8"
                    )
                    turn_rejected = (
                        "401: Unauthorized" in coturn_logs
                        or "error 401" in coturn_logs.lower()
                    )
                    assert turn_rejected, (
                        f"Coturn logs must show rejection: {coturn_logs[-400:]}"
                    )

                    # Verify Gateway did NOT commit Gen 2
                    gw_fence_neg = (
                        f"Generation {target_gen} officially committed for profile"
                        f" {profile_id}"
                    )
                    assert gw_fence_neg not in gw_logs_neg, (
                        "Gateway must not have committed Gen 2 under negative failure"
                    )

                    # Verify Gateway logged backoff retry
                    assert backoff_logged, (
                        "Gateway logs must show backoff retry."
                        f" Tail:\n{gw_logs_neg[-400:]}"
                    )

                    # Verify old media continues streaming on Generation 1
                    stats_neg = await page.evaluate("window.__getWebRTCStats()")
                    assert (
                        stats_neg["video"]["framesDecoded"]
                        > stats1["video"]["framesDecoded"]
                    ), "Old media must still be streaming during backoff"

                    # Fail on purpose so the negative run exits non-zero
                    raise AssertionError(
                        "Negative test failed as expected: Generation 2 could "
                        "not commit due to TURN credential rejection "
                        "and triggered backoff"
                    )

                # 3. Positive mode: Wait for Stream and Gateway fences
                stream_fence = (
                    f"Generation {target_gen} officially committed. "
                    f"Retired generation {target_gen - 1} closed and rejected writes."
                )
                gw_fence = (
                    f"Generation {target_gen} officially committed "
                    f"for profile {profile_id}"
                )

                committed = False
                deadline = asyncio.get_running_loop().time() + 60.0
                while asyncio.get_running_loop().time() < deadline:
                    s_logs = stream_box.logs(stdout=True, stderr=True).decode("utf-8")
                    g_logs = gw_box.logs(stdout=True, stderr=True).decode("utf-8")
                    if stream_fence in s_logs and gw_fence in g_logs:
                        committed = True
                        break
                    await asyncio.sleep(0.5)

                assert committed, (
                    f"Generation {target_gen} failed to commit within timeout.\n"
                    f"Stream logs:\n{stream_box.logs(tail=30).decode('utf-8')}\n"
                    f"Gateway logs:\n{gw_box.logs(tail=30).decode('utf-8')}"
                )

                # 4. Poll Chrome's selected pair: remoteUfrag == offer_ufrag, both relay
                pair = None
                for _ in range(50):
                    p_stat = await page.evaluate(pair_stats_js)
                    if (
                        p_stat
                        and p_stat.get("localType") == "relay"
                        and p_stat.get("remoteType") == "relay"
                        and p_stat.get("remoteUfrag") == offer_ufrag
                    ):
                        pair = p_stat
                        break
                    await asyncio.sleep(0.2)

                if pair is None:
                    dump = await page.evaluate("""async () => {
                        const pc = window.__rotationPC || window.__activePC;
                        const report = await pc.getStats();
                        const pairs = [];
                        const candidates = {};
                        for (const v of report.values()) {
                            if (v.type === 'local-candidate'
                                || v.type === 'remote-candidate') {
                                candidates[v.id] = v;
                            } else if (v.type === 'candidate-pair') {
                                pairs.push(v);
                            }
                        }
                        const transport = [...report.values()]
                            .find(v => v.type === 'transport');
                        return {
                            transport,
                            pairs: pairs.map(p => ({
                                id: p.id,
                                state: p.state,
                                nominated: p.nominated,
                                writable: p.writable,
                                local: candidates[p.localCandidateId],
                                remote: candidates[p.remoteCandidateId],
                            }))
                        };
                    }""")
                    raise AssertionError(
                        f"Generation {target_gen} committed in Stream but Chrome "
                        f"selected pair != offer ufrag {offer_ufrag}.\n"
                        f"last pair={p_stat}\n"
                        f"offer_ufrag={offer_ufrag}\n"
                        f"dump={dump}\n"
                        f"coturn_logs:\n{coturn_box.logs(tail=20).decode('utf-8')}\n"
                        f"stream_logs:\n{stream_box.logs(tail=20).decode('utf-8')}\n"
                        f"gateway_logs:\n{gw_box.logs(tail=20).decode('utf-8')}"
                    )

                # 5. Sample 2 s: video frames, audio energy and pair bytes must grow
                before_media = await page.evaluate("window.__getWebRTCStats()")
                initial_bytes = pair["bytesReceived"]
                await asyncio.sleep(2.0)
                after_media = await page.evaluate("window.__getWebRTCStats()")
                pair_after = await page.evaluate(pair_stats_js)

                delta_f = (
                    after_media["video"]["framesDecoded"]
                    - before_media["video"]["framesDecoded"]
                )
                delta_a = (
                    after_media["audio"]["totalAudioEnergy"]
                    - before_media["audio"]["totalAudioEnergy"]
                )
                delta_bytes = pair_after["bytesReceived"] - initial_bytes

                assert delta_f > 0, (
                    f"Gen {target_gen} must have fresh video frames decoded: {delta_f}"
                )
                assert delta_a > 0, (
                    f"Gen {target_gen} must have fresh audio energy: {delta_a}"
                )
                assert pair_after["remoteUfrag"] == offer_ufrag, (
                    f"Gen {target_gen} remote ufrag changed:"
                    f" {pair_after['remoteUfrag']}"
                )
                assert delta_bytes > 0, (
                    "Gen {target_gen} selected pair bytesReceived must grow:"
                    f" {delta_bytes}"
                )

                # 6. Verify same PC instance, count, and track references
                invariant = await page.evaluate("""() => ({
                    samePC: (window.pc || window.__activePC) === window.__rotationPC,
                    sameCount: (window.__pcs ? window.__pcs.length : 1)
                        === window.__rotationCount,
                    sameTracks: (() => {
                        const pc = window.pc || window.__activePC;
                        const receivers = pc.getReceivers();
                        return receivers.length === window.__rotationTracks.length
                            && receivers.every(
                                (r, i) => r.track === window.__rotationTracks[i]);
                    })()
                })""")
                assert invariant["samePC"], f"PC changed in Gen {target_gen}"
                assert invariant["sameCount"], f"PC count changed in Gen {target_gen}"
                assert invariant["sameTracks"], f"Tracks changed in Gen {target_gen}"

                gen_info = {
                    "generation": target_gen,
                    "offer_ufrag": offer_ufrag,
                    "pair": pair,
                    "pair_after": pair_after,
                    "delta_frames": delta_f,
                    "delta_audio": delta_a,
                    "delta_bytes": delta_bytes,
                    "invariant": invariant,
                }
                observed_generations.append(gen_info)

            evidence["observed_rotations"] = observed_generations
            save_evidence(
                "ac005_relay_evidence", evidence, target_dir=tmp_path / "evidence"
            )

            await browser.close()

    finally:
        await harness.cleanup()


@pytest.mark.asyncio
async def test_ac005_negative_turn_failure_exit_code(tmp_path: Path) -> None:
    """Run the negative mode as its own pytest process; it must exit non-zero."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        __file__,
        "-s",
        "-k",
        "test_ac005_relay_only_turn_rotations",
        "-o",
        f"cache_dir={tmp_path / 'pytest_cache'}",
        f"--basetemp={tmp_path / 'negative_basetemp'}",
    ]
    env = os.environ.copy()
    env["CBROWSER_TEST_NEGATIVE_TURN_QUOTA"] = "1"
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()
    out = (stdout or b"").decode("utf-8") + (stderr or b"").decode("utf-8")
    assert proc.returncode != 0, f"Negative test must exit non-zero. Output:\n{out}"
    assert "Negative test failed as expected" in out, (
        f"Expected failure message not found in output:\n{out}"
    )
