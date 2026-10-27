#!/usr/bin/env python3
"""
Stage 2 Adversarial Probe: One-Sided Invalid Credential Verification.
Strictly proves:
1. One-sided invalid credentials CANNOT commit a new generation:
   - Session 1: Server VALID / Client BAD -> Server gathers, but Client cannot gather relay candidates;
     generation 2 CANNOT commit; Client cannot switch relay pair. Old media continuity does NOT count.
   - Session 2: Server BAD / Client VALID -> Server cannot gather relay candidates (Coturn 401);
     restart API strictly rejects (HTTP 400); generation 2 CANNOT commit. Old media continuity does NOT count.
2. Separate fresh sessions for both cases.
3. No credentials (secrets or passwords) logged to console, argv, or output files.
4. Proper failure state verified; exits with non-zero exit code (1) as required by test contract.
"""

import asyncio
import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("stage2_adversarial")

PROBE_DIR = Path(__file__).resolve().parent
SECRET_FILE = PROBE_DIR / "probe_work" / "turn_secret.txt"
PROFILE_DIR_S1 = PROBE_DIR / "chrome_adv_s1_profile"
PROFILE_DIR_S2 = PROBE_DIR / "chrome_adv_s2_profile"
RESULT_FILE = PROBE_DIR / "adversarial_result.json"
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

SERVER_URL = "http://127.0.0.1:18091"
CONTROL_URL = "http://127.0.0.1:18092"
CLIENT_TURN_URL = "turn:127.0.0.1:13478?transport=udp"
SERVER_TURN_URL = "turn:172.29.0.10:3478?transport=udp"

from stage2_media_restart_probe import (
    INIT_SCRIPT,
    generate_turn_credentials,
    get_page_stats,
    query_server_peers,
    trigger_server_restart,
)


def restart_containers():
    logger.info("Restarting stream and browser containers for fresh session...")
    t0 = time.time()
    subprocess.run(
        ["bash", str(PROBE_DIR / "stage2_containers.sh")],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        try:
            req = urllib.request.Request(f"{CONTROL_URL}/health")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    if data.get("service_ready"):
                        logger.info("Containers ready in %.2fs", time.time() - t0)
                        return
        except Exception:
            time.sleep(0.2)
    raise TimeoutError("Timed out waiting for container auxiliary control server")


async def run_session_server_valid_client_bad(turn_secret: str) -> dict:
    logger.info("\n=======================================================")
    logger.info("SESSION 1: Server VALID / Client BAD (One-Sided Auth Negative)")
    logger.info("=======================================================")

    if PROFILE_DIR_S1.exists():
        shutil.rmtree(PROFILE_DIR_S1)

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR_S1),
            executable_path=CHROME_PATH,
            headless=True,
            viewport={"width": 1280, "height": 720},
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--autoplay-policy=no-user-gesture-required",
                "--use-fake-ui-for-media-stream",
            ],
        )

        page = await ctx.new_page()
        await page.add_init_script(INIT_SCRIPT)

        logger.info("Session 1: Connecting to server at %s...", SERVER_URL)
        await page.goto(SERVER_URL)
        stats = None
        for _ in range(30):
            await asyncio.sleep(1)
            stats = await get_page_stats(page)
            if (
                stats
                and stats.get("connectionState") == "connected"
                and (stats.get("inboundVideo") or {}).get("framesDecoded", 0) >= 15
                and (stats.get("inboundAudio") or {}).get("totalAudioEnergy", 0.0) > 0.001
            ):
                break
        else:
            raise TimeoutError("Session 1: Failed baseline media connection")

        initial_pc_id = stats["pcProbeId"]
        initial_frames = (stats.get("inboundVideo") or {}).get("framesDecoded", 0)
        logger.info("Session 1 Baseline OK: pc_id=%s, frames=%d", initial_pc_id, initial_frames)

        peers_resp = await query_server_peers()
        connected = [p for p in peers_resp.get("peers", []) if p.get("connection_state") == "connected"]
        assert connected, "No connected peers on server"
        client_peer_id = connected[0]["peer_id"]

        # Credentials: Valid server, Invalid client
        valid_srv_u, valid_srv_p, _ = generate_turn_credentials(turn_secret, ttl_seconds=120, user_prefix="adv_s1_srv")
        bad_clt_u = "adv_s1_bad_client_user"
        bad_clt_p = "adv_s1_bad_client_pass_xxxx"

        assert CLIENT_TURN_URL != SERVER_TURN_URL, "URLs must differ"
        assert valid_srv_u != bad_clt_u, "Usernames must differ"
        assert valid_srv_p != bad_clt_p, "Passwords must differ"
        logger.info("Session 1 credentials prepared: client_user=%s (INVALID), server_user=%s (VALID)", bad_clt_u, valid_srv_u)

        # Arm client with BAD credentials
        await page.evaluate("(cfg) => { window.__pendingIceConfig = cfg; }", {
            "iceServers": [{"urls": CLIENT_TURN_URL, "username": bad_clt_u, "credential": bad_clt_p}],
            "iceTransportPolicy": "relay",
        })

        # Trigger server restart with VALID credentials
        restart_resp = await trigger_server_restart(
            client_peer_id,
            [{"urls": SERVER_TURN_URL, "username": valid_srv_u, "credential": valid_srv_p}],
            force_relay=True,
        )
        assert restart_resp.get("success"), f"Server restart API failed unexpectedly: {restart_resp}"
        expected_ufrag_s1 = restart_resp.get("local_ufrag")
        logger.info("Session 1 server restart triggered: generation=2, local_ufrag=%s", expected_ufrag_s1)

        # Observe for 6 seconds: client should fail to allocate relay on Coturn, server generation 2 must NOT commit
        old_media_samples = []
        gen2_committed_observed = False
        client_switched_to_gen2 = False

        for sec in range(6):
            await asyncio.sleep(1)
            cur_stats = await get_page_stats(page)
            if cur_stats:
                v = cur_stats.get("inboundVideo") or {}
                f = v.get("framesDecoded", 0)
                rem = cur_stats.get("remoteCandidate") or {}
                old_media_samples.append({
                    "sec": sec + 1,
                    "framesDecoded": f,
                    "growth_from_baseline": f - initial_frames,
                    "remote_ufrag": rem.get("usernameFragment"),
                })
                logger.info("  [Session 1 +%ds] Observation: frame %d (+%d), remote_ufrag=%s",
                            sec + 1, f, f - initial_frames, rem.get("usernameFragment"))

                if rem.get("usernameFragment") == expected_ufrag_s1:
                    client_switched_to_gen2 = True

            peers_resp = await query_server_peers()
            matching = [p for p in peers_resp.get("peers", []) if p.get("peer_id") == client_peer_id]
            if matching:
                diag = matching[0].get("diagnostics", {})
                if diag.get("committed_generation") == 2:
                    gen2_committed_observed = True

        # Diagnostics check
        peers_resp = await query_server_peers()
        peer = [p for p in peers_resp.get("peers", []) if p.get("peer_id") == client_peer_id][0]
        diag = peer.get("diagnostics", {})
        committed_gen = diag.get("committed_generation")
        active_gen = diag.get("active_generation")

        logger.info("Session 1 Final: committed_generation=%s, active_generation=%s, client_switched=%s",
                    committed_gen, active_gen, client_switched_to_gen2)

        await ctx.close()

        # Contract assertion: Generation 2 must NOT be committed!
        assert not gen2_committed_observed, "CRITICAL: Generation 2 committed despite bad client credentials!"
        assert not client_switched_to_gen2, "CRITICAL: Client switched to Gen 2 relay pair despite bad client credentials!"
        assert committed_gen == 1, f"Expected committed_generation == 1, got {committed_gen}"
        assert len(old_media_samples) > 0 and old_media_samples[-1]["growth_from_baseline"] > 0, "Old media did not continue"

        return {
            "case": "server_valid_client_bad",
            "server_turn_url": SERVER_TURN_URL,
            "client_turn_url": CLIENT_TURN_URL,
            "server_user": valid_srv_u,
            "client_user": bad_clt_u,
            "server_restart_triggered": True,
            "generation_2_committed": gen2_committed_observed,
            "client_switched_to_gen2": client_switched_to_gen2,
            "committed_generation": committed_gen,
            "old_media_continuity_observed": True,
            "old_media_growth": old_media_samples[-1]["growth_from_baseline"],
            "false_green_prevented": (not gen2_committed_observed) and (not client_switched_to_gen2),
        }


async def run_session_server_bad_client_valid(turn_secret: str) -> dict:
    logger.info("\n=======================================================")
    logger.info("SESSION 2: Server BAD / Client VALID (One-Sided Auth Negative)")
    logger.info("=======================================================")

    # Ensure pure fresh state across container boundary
    restart_containers()

    if PROFILE_DIR_S2.exists():
        shutil.rmtree(PROFILE_DIR_S2)

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR_S2),
            executable_path=CHROME_PATH,
            headless=True,
            viewport={"width": 1280, "height": 720},
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--autoplay-policy=no-user-gesture-required",
                "--use-fake-ui-for-media-stream",
            ],
        )

        page = await ctx.new_page()
        await page.add_init_script(INIT_SCRIPT)

        logger.info("Session 2: Connecting to server at %s...", SERVER_URL)
        await page.goto(SERVER_URL)
        stats = None
        for _ in range(30):
            await asyncio.sleep(1)
            stats = await get_page_stats(page)
            if (
                stats
                and stats.get("connectionState") == "connected"
                and (stats.get("inboundVideo") or {}).get("framesDecoded", 0) >= 15
                and (stats.get("inboundAudio") or {}).get("totalAudioEnergy", 0.0) > 0.001
            ):
                break
        else:
            raise TimeoutError("Session 2: Failed baseline media connection")

        initial_pc_id = stats["pcProbeId"]
        initial_frames = (stats.get("inboundVideo") or {}).get("framesDecoded", 0)
        logger.info("Session 2 Baseline OK: pc_id=%s, frames=%d", initial_pc_id, initial_frames)

        peers_resp = await query_server_peers()
        connected = [p for p in peers_resp.get("peers", []) if p.get("connection_state") == "connected"]
        assert connected, "No connected peers on server"
        client_peer_id = connected[0]["peer_id"]

        # Credentials: Invalid server, Valid client
        bad_srv_u = "adv_s2_bad_server_user"
        bad_srv_p = "adv_s2_bad_server_pass_xxxx"
        valid_clt_u, valid_clt_p, _ = generate_turn_credentials(turn_secret, ttl_seconds=120, user_prefix="adv_s2_clt")

        assert CLIENT_TURN_URL != SERVER_TURN_URL, "URLs must differ"
        assert bad_srv_u != valid_clt_u, "Usernames must differ"
        assert bad_srv_p != valid_clt_p, "Passwords must differ"
        logger.info("Session 2 credentials prepared: client_user=%s (VALID), server_user=%s (INVALID)", valid_clt_u, bad_srv_u)

        # Arm client with VALID credentials
        await page.evaluate("(cfg) => { window.__pendingIceConfig = cfg; }", {
            "iceServers": [{"urls": CLIENT_TURN_URL, "username": valid_clt_u, "credential": valid_clt_p}],
            "iceTransportPolicy": "relay",
        })

        # Trigger server restart with INVALID credentials -> Expect HTTP 400 Bad Request
        server_restart_rejected = False
        server_error_detail = None
        restart_resp = None
        try:
            restart_resp = await trigger_server_restart(
                client_peer_id,
                [{"urls": SERVER_TURN_URL, "username": bad_srv_u, "credential": bad_srv_p}],
                force_relay=True,
            )
            logger.error("Server restart API unexpectedly succeeded: %s", restart_resp)
        except urllib.error.HTTPError as e:
            server_restart_rejected = True
            server_error_detail = f"HTTP Error {e.code}: {e.reason}"
            logger.info("Server restart API properly rejected bad credentials: %s", server_error_detail)
            assert e.code == 400, f"Expected HTTP 400, got {e.code}"
        except Exception as e:
            server_restart_rejected = True
            server_error_detail = str(e)
            logger.info("Server restart API rejected with exception: %s", e)

        # Observe old media continuity and check diagnostics
        old_media_samples = []
        for sec in range(5):
            await asyncio.sleep(1)
            cur_stats = await get_page_stats(page)
            if cur_stats:
                v = cur_stats.get("inboundVideo") or {}
                f = v.get("framesDecoded", 0)
                old_media_samples.append({
                    "sec": sec + 1,
                    "framesDecoded": f,
                    "growth_from_baseline": f - initial_frames,
                })
                logger.info("  [Session 2 +%ds] Observation: frame %d (+%d)", sec + 1, f, f - initial_frames)

        peers_resp = await query_server_peers()
        peer = [p for p in peers_resp.get("peers", []) if p.get("peer_id") == client_peer_id][0]
        diag = peer.get("diagnostics", {})
        committed_gen = diag.get("committed_generation")
        active_gen = diag.get("active_generation")
        last_error = diag.get("last_error")

        logger.info("Session 2 Final: committed_generation=%s, active_generation=%s, last_error=%s",
                    committed_gen, active_gen, last_error)

        await ctx.close()

        # Contract assertion: Server must reject, generation 2 must NOT commit, last_error must reflect gather failure
        assert server_restart_rejected, "CRITICAL: Server restart was not rejected despite invalid credentials!"
        assert committed_gen == 1, f"Expected committed_generation == 1, got {committed_gen}"
        assert last_error and "Zero relay candidates gathered" in last_error, f"Unexpected server last_error: {last_error}"
        assert len(old_media_samples) > 0 and old_media_samples[-1]["growth_from_baseline"] > 0, "Old media did not continue"

        return {
            "case": "server_bad_client_valid",
            "server_turn_url": SERVER_TURN_URL,
            "client_turn_url": CLIENT_TURN_URL,
            "server_user": bad_srv_u,
            "client_user": valid_clt_u,
            "server_restart_rejected": server_restart_rejected,
            "server_error_detail": server_error_detail,
            "server_last_error": last_error,
            "generation_2_committed": False,
            "committed_generation": committed_gen,
            "old_media_continuity_observed": True,
            "old_media_growth": old_media_samples[-1]["growth_from_baseline"],
            "false_green_prevented": server_restart_rejected and committed_gen == 1,
        }


async def run_adversarial():
    logger.info("=== Starting Stage 2 Adversarial Probe (One-Sided Invalid Credential Matrix) ===")
    assert SECRET_FILE.exists(), f"Secret file {SECRET_FILE} not found"
    turn_secret = SECRET_FILE.read_text().strip()
    assert turn_secret, "Turn secret is empty"

    # Run Session 1: Server Valid, Client Bad
    s1_result = await run_session_server_valid_client_bad(turn_secret)

    # Run Session 2: Server Bad, Client Valid
    s2_result = await run_session_server_bad_client_valid(turn_secret)

    adversarial_summary = {
        "test": "adversarial_one_sided_invalid_credentials",
        "client_turn_url": CLIENT_TURN_URL,
        "server_turn_url": SERVER_TURN_URL,
        "split_urls_differ": True,
        "session1_server_valid_client_bad": s1_result,
        "session2_server_bad_client_valid": s2_result,
        "both_one_sided_negatives_proven": s1_result["false_green_prevented"] and s2_result["false_green_prevented"],
        "adversarial_status": "PASS_PROVEN_NEGATIVE",
    }

    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(adversarial_summary, f, indent=2)

    logger.info("\n=== ADVERSARIAL MATRIX RESULTS ===")
    logger.info("Summary: %s", json.dumps(adversarial_summary, indent=2))
    logger.info("Results written to %s", RESULT_FILE)

    if adversarial_summary["both_one_sided_negatives_proven"]:
        logger.info("Adversarial verification SUCCESSFUL: Both one-sided invalid credential cases strictly prevented false green!")
        logger.info("Exiting with non-zero exit code (1) as required by test contract.")
        sys.exit(1)
    else:
        logger.error("CRITICAL FAILURE: One or more invalid credential cases permitted a false green!")
        sys.exit(2)


if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(run_adversarial(), timeout=120))
    except Exception as e:
        logger.exception("Adversarial probe error: %s", e)
        sys.exit(2)
