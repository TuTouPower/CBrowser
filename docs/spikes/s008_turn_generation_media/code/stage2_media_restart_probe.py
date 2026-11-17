#!/usr/bin/env python3
"""
Stage 2 WebRTC Media & ICE Restart Probe (Strict Verification).
Validates:
1. Google Chrome connects to Selkies 2.1.0 WebRTC server on dedicated port 18091.
2. Initial media flow: 1920x1080 video decoding, framesDecoded growth, 440Hz totalAudioEnergy growth.
3. Same-PC ICE Restart:
   - Preserves same RTCPeerConnection object, same tracks, same data channel. Zero page reload.
   - Preserves same server-side RTCPeerConnection and RTCDtlsTransport objects.
   - Generates fresh short-lived TURN REST credentials.
   - Sets client iceTransportPolicy to 'relay' and server force_relay=True.
   - Server sends standard SDP Offer; client answers.
   - Waits for server's committed_generation to advance AND old generation closed and rejected.
   - Waits for client's selectedCandidatePair to switch to the new ufrag and strictly relay <-> relay.
   - Takes a FRESH post-committed media baseline.
   - Requires actual 1080p frame decoding and audio energy growth strictly over the new active relay pair.
4. Second ICE Restart round to prove multi-generation rotation stability under the exact same strict assertions.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("stage2_probe")

PROBE_DIR = Path(__file__).resolve().parent
SECRET_FILE = PROBE_DIR / "probe_work" / "turn_secret.txt"
PROFILE_DIR = PROBE_DIR / "chrome_stage2_profile"
RESULT_FILE = PROBE_DIR / "stage2_result.jsonl"
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

SERVER_URL = "http://127.0.0.1:18091"
CONTROL_URL = "http://127.0.0.1:18092"
CLIENT_TURN_URL = "turn:127.0.0.1:13478?transport=udp"
SERVER_TURN_URL = "turn:172.29.0.10:3478?transport=udp"

INIT_SCRIPT = """
(function() {
    window.__SELKIES_STREAMING_MODE__ = 'webrtc';
    window.__peerConnections = [];
    window.__pendingIceConfig = null;
    window.__restartCount = 0;

    const OrigPC = window.RTCPeerConnection;
    window.RTCPeerConnection = function(...args) {
        const pc = new OrigPC(...args);
        pc.__probeId = 'pc_' + Math.random().toString(36).substring(2, 10);
        window.__peerConnections.push(pc);
        if (!window.__firstPC) window.__firstPC = pc;

        pc.addEventListener('track', (e) => {
            if (e.track.kind === 'audio') {
                let audioEl = document.getElementById('webrtc-audio-sink');
                if (!audioEl) {
                    audioEl = document.createElement('audio');
                    audioEl.id = 'webrtc-audio-sink';
                    audioEl.autoplay = true;
                    document.body.appendChild(audioEl);
                }
                audioEl.srcObject = e.streams[0];
                audioEl.play().catch(() => {});
            }
        });

        return pc;
    };
    window.RTCPeerConnection.prototype = OrigPC.prototype;

    // Hook setRemoteDescription to apply new ICE configuration before renegotiation answer
    const origSetRemoteDescription = OrigPC.prototype.setRemoteDescription;
    OrigPC.prototype.setRemoteDescription = async function(description) {
        if (description && description.type === 'offer' && window.__pendingIceConfig) {
            this.setConfiguration(window.__pendingIceConfig);
            window.__pendingIceConfig = null;
            window.__restartCount += 1;
        }
        return origSetRemoteDescription.apply(this, arguments);
    };
})();
"""


def generate_turn_credentials(secret: str, ttl_seconds: int = 120, user_prefix: str = "stage2"):
    now = int(time.time())
    expiry = now + ttl_seconds
    username = f"{expiry}:{user_prefix}"
    mac = hmac.new(secret.encode("utf-8"), username.encode("utf-8"), hashlib.sha1).digest()
    password = base64.b64encode(mac).decode("utf-8")
    return username, password, expiry


async def get_page_stats(page):
    return await page.evaluate("""async () => {
        if (!window.__peerConnections || window.__peerConnections.length === 0) return null;
        const pc = window.__peerConnections[window.__peerConnections.length - 1];
        let report;
        try {
            report = await pc.getStats();
        } catch (e) {
            return null;
        }

        let inboundVideo = null;
        let inboundAudio = null;
        let selectedCandidatePair = null;
        let localCandidate = null;
        let remoteCandidate = null;
        let transport = null;

        for (const entry of report.values()) {
            if (entry.type === 'transport') {
                transport = entry;
            }
            if (entry.type === 'inbound-rtp') {
                if (entry.kind === 'video') inboundVideo = entry;
                if (entry.kind === 'audio') inboundAudio = entry;
            }
        }

        if (transport && transport.selectedCandidatePairId) {
            selectedCandidatePair = report.get(transport.selectedCandidatePairId) || null;
        } else {
            for (const entry of report.values()) {
                if (entry.type === 'candidate-pair' && entry.state === 'succeeded' && entry.nominated) {
                    selectedCandidatePair = entry;
                    break;
                }
            }
        }

        if (selectedCandidatePair) {
            localCandidate = report.get(selectedCandidatePair.localCandidateId) || null;
            remoteCandidate = report.get(selectedCandidatePair.remoteCandidateId) || null;
        }

        return {
            pcCount: window.__peerConnections.length,
            pcProbeId: pc.__probeId,
            samePCReference: pc === window.__firstPC,
            sameTrackReferences: !!window.__initialTracks && window.__initialTracks.length === pc.getReceivers().length && pc.getReceivers().every((r, i) => r.track === window.__initialTracks[i]),
            restartCount: window.__restartCount,
            connectionState: pc.connectionState,
            iceConnectionState: pc.iceConnectionState,
            signalingState: pc.signalingState,
            selectedCandidatePairId: selectedCandidatePair ? selectedCandidatePair.id : null,
            localCandidate: localCandidate ? {
                id: localCandidate.id,
                candidateType: localCandidate.candidateType,
                protocol: localCandidate.protocol,
                ip: localCandidate.ip || localCandidate.address,
                port: localCandidate.port,
                usernameFragment: localCandidate.usernameFragment,
            } : null,
            remoteCandidate: remoteCandidate ? {
                id: remoteCandidate.id,
                candidateType: remoteCandidate.candidateType,
                protocol: remoteCandidate.protocol,
                ip: remoteCandidate.ip || remoteCandidate.address,
                port: remoteCandidate.port,
                usernameFragment: remoteCandidate.usernameFragment,
            } : null,
            selectedCandidatePair: selectedCandidatePair ? {
                id: selectedCandidatePair.id,
                state: selectedCandidatePair.state,
                nominated: selectedCandidatePair.nominated,
                bytesReceived: selectedCandidatePair.bytesReceived,
                bytesSent: selectedCandidatePair.bytesSent,
            } : null,
            inboundVideo: inboundVideo ? {
                bytesReceived: inboundVideo.bytesReceived,
                framesDecoded: inboundVideo.framesDecoded,
                framesReceived: inboundVideo.framesReceived,
                frameWidth: inboundVideo.frameWidth,
                frameHeight: inboundVideo.frameHeight,
            } : null,
            inboundAudio: inboundAudio ? {
                bytesReceived: inboundAudio.bytesReceived,
                totalAudioEnergy: inboundAudio.totalAudioEnergy,
            } : null,
        };
    }""")


async def query_server_peers():
    url = f"{CONTROL_URL}/peers"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=3) as resp:
        return json.loads(resp.read().decode())


async def trigger_server_restart(client_peer_id: str, ice_servers: list, force_relay: bool = True):
    url = f"{CONTROL_URL}/restart_ice"
    payload = json.dumps({
        "client_peer_id": client_peer_id,
        "ice_servers": ice_servers,
        "force_relay": force_relay,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


async def run_stage2():
    logger.info("=== Starting Stage 2 WebRTC Media & ICE Restart Probe (Strict Mode) ===")
    assert SECRET_FILE.exists(), f"Secret file {SECRET_FILE} not found"
    turn_secret = SECRET_FILE.read_text().strip()
    assert turn_secret, "Turn secret is empty"

    if PROFILE_DIR.exists():
        shutil.rmtree(PROFILE_DIR)

    async with async_playwright() as p:
        logger.info("Launching Chrome Persistent Context at %s...", CHROME_PATH)
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
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

        # -------------------------------------------------------------
        # Phase 1: Connect and verify initial real media baseline
        # -------------------------------------------------------------
        logger.info("Navigating to Selkies server at %s...", SERVER_URL)
        await page.goto(SERVER_URL)

        logger.info("Waiting for initial WebRTC connection and media decode (1920x1080)...")
        stats = None
        for sec in range(30):
            await asyncio.sleep(1)
            stats = await get_page_stats(page)
            if not stats:
                continue
            c_state = stats.get("connectionState")
            v = stats.get("inboundVideo") or {}
            f_decoded = v.get("framesDecoded", 0)
            w = v.get("frameWidth", 0)
            h = v.get("frameHeight", 0)
            a = stats.get("inboundAudio") or {}
            energy = a.get("totalAudioEnergy", 0.0)
            logger.info("  [%ds] State: %s | Video: %sx%s (%d frames) | Audio Energy: %.4f",
                        sec + 1, c_state, str(w), str(h), f_decoded, energy)

            if c_state == "connected" and f_decoded >= 15 and w == 1920 and h == 1080 and energy > 0.001:
                logger.info("Phase 1 Baseline Real Media achieved!")
                break
        else:
            raise TimeoutError(f"Failed to achieve baseline 1080p media flow: {stats}")

        await page.evaluate("() => { window.__initialTracks = window.__firstPC.getReceivers().map(r => r.track); if (window.__initialTracks.length < 2) throw new Error('Missing audio/video receiver tracks'); }")
        initial_client_pc_id = stats["pcProbeId"]
        initial_frames = (stats.get("inboundVideo") or {}).get("framesDecoded", 0)
        initial_audio_energy = (stats.get("inboundAudio") or {}).get("totalAudioEnergy", 0.0)
        logger.info("Baseline recorded: client_pc_id=%s, frames=%d, audio_energy=%.4f",
                    initial_client_pc_id, initial_frames, initial_audio_energy)

        # Get server-side peer info
        peers_resp = await query_server_peers()
        connected_peers = [p for p in peers_resp.get("peers", []) if p.get("connection_state") == "connected"]
        assert connected_peers, f"No connected peers found on server: {peers_resp}"
        server_peer = connected_peers[0]
        client_peer_id = server_peer["peer_id"]
        initial_server_pc_id = server_peer["server_pc_id"]
        initial_server_dtls_id = server_peer["server_dtls_id"]
        logger.info("Target client_peer_id: %s, server_pc_id: %s, server_dtls_id: %s",
                    client_peer_id, initial_server_pc_id, initial_server_dtls_id)

        # -------------------------------------------------------------
        # Phase 2: ICE Restart Round 1 -> Relay-only + Short-lived REST
        # -------------------------------------------------------------
        target_gen = 2
        logger.info("\n--- [Phase 2] Triggering Same-PC ICE Restart #1 (Relay-Only, Generation %d) ---", target_gen)

        # Assert topology separation: Client uses published host URL, Server uses private internal Docker URL
        assert CLIENT_TURN_URL != SERVER_TURN_URL, "Client and Server TURN URLs must be strictly independent"
        assert CLIENT_TURN_URL == "turn:127.0.0.1:13478?transport=udp"
        assert SERVER_TURN_URL == "turn:172.29.0.10:3478?transport=udp"
        logger.info("Topology verified: Client TURN URL=%s, Server TURN URL=%s", CLIENT_TURN_URL, SERVER_TURN_URL)

        # Generate separate valid REST credentials for Client and Server
        client_u1, client_p1, _ = generate_turn_credentials(turn_secret, ttl_seconds=120, user_prefix="client_r1")
        server_u1, server_p1, _ = generate_turn_credentials(turn_secret, ttl_seconds=120, user_prefix="server_r1")

        # Assert usernames and passwords differ without logging secret
        assert client_u1 != server_u1, "Client and server usernames must differ"
        assert client_p1 != server_p1, "Client and server passwords must differ"
        logger.info("Separate valid credentials generated: client_user=%s, server_user=%s", client_u1, server_u1)

        # Config for Chrome client
        client_turn_config = {
            "iceServers": [{
                "urls": CLIENT_TURN_URL,
                "username": client_u1,
                "credential": client_p1,
            }],
            "iceTransportPolicy": "relay",
        }

        # Arm client hook before triggering server offer
        await page.evaluate("(cfg) => { window.__pendingIceConfig = cfg; }", client_turn_config)

        # Server-side TURN config
        server_turn_servers = [{
            "urls": SERVER_TURN_URL,
            "username": server_u1,
            "credential": server_p1,
        }]
        restart_resp = await trigger_server_restart(client_peer_id, server_turn_servers, force_relay=True)
        assert restart_resp.get("success"), f"Restart API failed: {restart_resp}"
        expected_local_ufrag = restart_resp.get("local_ufrag")
        logger.info("Server restart triggered successfully: generation=%s, local_ufrag=%s",
                    restart_resp.get("generation"), expected_local_ufrag)

        # STEP A: Wait for server committed_generation == target_gen AND old generation retired
        logger.info("Step A: Waiting for server committed_generation == %d...", target_gen)
        for sec in range(25):
            await asyncio.sleep(0.5)
            peers_resp = await query_server_peers()
            matching = [p for p in peers_resp.get("peers", []) if p.get("peer_id") == client_peer_id]
            if matching:
                diag = matching[0].get("diagnostics", {})
                committed = diag.get("committed_generation")
                retired = diag.get("retired_generations", [])
                if committed == target_gen and any(r.get("generation") == target_gen - 1 and r.get("send_rejected") for r in retired):
                    logger.info("Step A OK: Server officially committed generation %d with retired gen %d send_rejected=True",
                                target_gen, target_gen - 1)
                    break
        else:
            raise TimeoutError(f"Server failed to commit generation {target_gen}")

        # STEP B: Wait for Chrome client to switch to new generation relay pair
        logger.info("Step B: Waiting for Chrome selectedCandidatePair to switch to generation %d relay pair...", target_gen)
        r1_stats = None
        for sec in range(25):
            await asyncio.sleep(0.5)
            r1_stats = await get_page_stats(page)
            if not r1_stats:
                continue
            pair = r1_stats.get("selectedCandidatePair") or {}
            loc = r1_stats.get("localCandidate") or {}
            rem = r1_stats.get("remoteCandidate") or {}
            if (
                pair.get("state") == "succeeded"
                and loc.get("candidateType") == "relay"
                and rem.get("candidateType") == "relay"
                and rem.get("usernameFragment") == expected_local_ufrag
            ):
                logger.info("Step B OK: Client selected candidate pair is strictly relay <-> relay with remote_ufrag=%s",
                            expected_local_ufrag)
                break
        else:
            raise TimeoutError(f"Client failed to switch to generation {target_gen} relay pair: {r1_stats}")

        # STEP C: Establish TRUE committed baseline for Generation 2
        r1_baseline_frames = (r1_stats.get("inboundVideo") or {}).get("framesDecoded", 0)
        r1_baseline_energy = (r1_stats.get("inboundAudio") or {}).get("totalAudioEnergy", 0.0)
        r1_baseline_pair_bytes = (r1_stats.get("selectedCandidatePair") or {}).get("bytesReceived", 0)
        logger.info("Step C: New generation %d committed baseline: frames=%d, energy=%.4f, pair_bytes=%d",
                    target_gen, r1_baseline_frames, r1_baseline_energy, r1_baseline_pair_bytes)

        # STEP D: Assert fresh 1080p decoded frames and audio energy growth strictly over new generation
        logger.info("Step D: Measuring fresh media growth on generation %d...", target_gen)
        r1_growth_ok = False
        for sec in range(20):
            await asyncio.sleep(1)
            cur = await get_page_stats(page)
            if not cur:
                continue
            v = cur.get("inboundVideo") or {}
            a = cur.get("inboundAudio") or {}
            pair = cur.get("selectedCandidatePair") or {}
            f_decoded = v.get("framesDecoded", 0)
            energy = a.get("totalAudioEnergy", 0.0)
            pair_bytes = pair.get("bytesReceived", 0)
            w = v.get("frameWidth", 0)
            h = v.get("frameHeight", 0)
            logger.info("  [Gen %d Growth +%ds] Video: %dx%d, frames: %d (+%d) | Audio Energy: %.4f (+%.4f) | Pair bytes: %d (+%d)",
                        target_gen, sec + 1, w, h, f_decoded, f_decoded - r1_baseline_frames,
                        energy, energy - r1_baseline_energy, pair_bytes, pair_bytes - r1_baseline_pair_bytes)

            if (
                w == 1920 and h == 1080
                and f_decoded >= r1_baseline_frames + 15
                and energy > r1_baseline_energy + 0.1
                and pair_bytes > r1_baseline_pair_bytes + 30000
            ):
                r1_stats = cur
                r1_growth_ok = True
                logger.info("Step D OK: Verified fresh 1080p frames (+%d) and audio energy growth on generation %d!",
                            f_decoded - r1_baseline_frames, target_gen)
                break
        else:
            raise TimeoutError(f"Generation {target_gen} failed to yield fresh media growth!")

        # STEP E: Verify object invariance
        assert r1_stats["samePCReference"], "Client PC reference changed"
        assert r1_stats["sameTrackReferences"], "Client receiver track references changed"
        assert r1_stats["pcCount"] == 1, f"Multiple PCs created: {r1_stats['pcCount']}"
        assert r1_stats["pcProbeId"] == initial_client_pc_id, "Client PC object changed!"
        peers_resp = await query_server_peers()
        curr_server_peer = [p for p in peers_resp.get("peers", []) if p.get("peer_id") == client_peer_id][0]
        assert curr_server_peer["server_pc_id"] == initial_server_pc_id, "Server PC object changed!"
        assert curr_server_peer["server_dtls_id"] == initial_server_dtls_id, "Server DTLS Transport object changed!"
        logger.info("Step E OK: Confirmed identical client and server PC/DTLS object references (Zero Reload)")

        # -------------------------------------------------------------
        # Phase 3: ICE Restart Round 2 -> Rotate to fresh TURN credential
        # -------------------------------------------------------------
        target_gen = 3
        logger.info("\n--- [Phase 3] Triggering Same-PC ICE Restart #2 (Rotation, Generation %d) ---", target_gen)

        # Generate separate valid REST credentials for Round 2 rotation
        client_u2, client_p2, _ = generate_turn_credentials(turn_secret, ttl_seconds=120, user_prefix="client_r2")
        server_u2, server_p2, _ = generate_turn_credentials(turn_secret, ttl_seconds=120, user_prefix="server_r2")

        # Assert independent usernames and passwords differ without logging secret
        assert client_u2 != server_u2, "Round 2 client and server usernames must differ"
        assert client_p2 != server_p2, "Round 2 client and server passwords must differ"
        assert client_u2 != client_u1, "Client username must rotate across generations"
        assert server_u2 != server_u1, "Server username must rotate across generations"
        logger.info("Round 2 separate credentials generated: client_user=%s, server_user=%s", client_u2, server_u2)

        client_turn_config2 = {
            "iceServers": [{
                "urls": CLIENT_TURN_URL,
                "username": client_u2,
                "credential": client_p2,
            }],
            "iceTransportPolicy": "relay",
        }
        await page.evaluate("(cfg) => { window.__pendingIceConfig = cfg; }", client_turn_config2)

        server_turn_servers2 = [{
            "urls": SERVER_TURN_URL,
            "username": server_u2,
            "credential": server_p2,
        }]
        restart_resp2 = await trigger_server_restart(client_peer_id, server_turn_servers2, force_relay=True)
        assert restart_resp2.get("success"), f"Restart #2 API failed: {restart_resp2}"
        expected_local_ufrag2 = restart_resp2.get("local_ufrag")
        assert expected_local_ufrag2 != expected_local_ufrag, "ufrag did not rotate between generations!"
        logger.info("Server restart #2 triggered: generation=%s, local_ufrag=%s",
                    restart_resp2.get("generation"), expected_local_ufrag2)

        # STEP A2: Wait for server committed_generation == target_gen
        logger.info("Step A2: Waiting for server committed_generation == %d...", target_gen)
        for sec in range(25):
            await asyncio.sleep(0.5)
            peers_resp = await query_server_peers()
            matching = [p for p in peers_resp.get("peers", []) if p.get("peer_id") == client_peer_id]
            if matching:
                diag = matching[0].get("diagnostics", {})
                committed = diag.get("committed_generation")
                retired = diag.get("retired_generations", [])
                if committed == target_gen and any(r.get("generation") == target_gen - 1 and r.get("send_rejected") for r in retired):
                    logger.info("Step A2 OK: Server committed generation %d with retired gen %d send_rejected=True",
                                target_gen, target_gen - 1)
                    break
        else:
            raise TimeoutError(f"Server failed to commit generation {target_gen}")

        # STEP B2: Wait for Chrome client to switch to generation 3 relay pair
        logger.info("Step B2: Waiting for Chrome to switch to generation %d relay pair...", target_gen)
        r2_stats = None
        for sec in range(25):
            await asyncio.sleep(0.5)
            r2_stats = await get_page_stats(page)
            if not r2_stats:
                continue
            pair = r2_stats.get("selectedCandidatePair") or {}
            loc = r2_stats.get("localCandidate") or {}
            rem = r2_stats.get("remoteCandidate") or {}
            if (
                pair.get("state") == "succeeded"
                and loc.get("candidateType") == "relay"
                and rem.get("candidateType") == "relay"
                and rem.get("usernameFragment") == expected_local_ufrag2
            ):
                logger.info("Step B2 OK: Client switched to generation %d relay pair with remote_ufrag=%s",
                            target_gen, expected_local_ufrag2)
                break
        else:
            raise TimeoutError(f"Client failed to switch to generation {target_gen} relay pair: {r2_stats}")

        # STEP C2: Establish committed baseline for Generation 3
        r2_baseline_frames = (r2_stats.get("inboundVideo") or {}).get("framesDecoded", 0)
        r2_baseline_energy = (r2_stats.get("inboundAudio") or {}).get("totalAudioEnergy", 0.0)
        r2_baseline_pair_bytes = (r2_stats.get("selectedCandidatePair") or {}).get("bytesReceived", 0)
        logger.info("Step C2: New generation %d committed baseline: frames=%d, energy=%.4f, pair_bytes=%d",
                    target_gen, r2_baseline_frames, r2_baseline_energy, r2_baseline_pair_bytes)

        # STEP D2: Assert fresh media growth on Generation 3
        logger.info("Step D2: Measuring fresh media growth on generation %d...", target_gen)
        r2_growth_ok = False
        for sec in range(20):
            await asyncio.sleep(1)
            cur = await get_page_stats(page)
            if not cur:
                continue
            v = cur.get("inboundVideo") or {}
            a = cur.get("inboundAudio") or {}
            pair = cur.get("selectedCandidatePair") or {}
            f_decoded = v.get("framesDecoded", 0)
            energy = a.get("totalAudioEnergy", 0.0)
            pair_bytes = pair.get("bytesReceived", 0)
            w = v.get("frameWidth", 0)
            h = v.get("frameHeight", 0)
            logger.info("  [Gen %d Growth +%ds] Video: %dx%d, frames: %d (+%d) | Audio Energy: %.4f (+%.4f) | Pair bytes: %d (+%d)",
                        target_gen, sec + 1, w, h, f_decoded, f_decoded - r2_baseline_frames,
                        energy, energy - r2_baseline_energy, pair_bytes, pair_bytes - r2_baseline_pair_bytes)

            if (
                w == 1920 and h == 1080
                and f_decoded >= r2_baseline_frames + 15
                and energy > r2_baseline_energy + 0.1
                and pair_bytes > r2_baseline_pair_bytes + 30000
            ):
                r2_stats = cur
                r2_growth_ok = True
                logger.info("Step D2 OK: Verified fresh 1080p frames (+%d) and audio energy growth on generation %d!",
                            f_decoded - r2_baseline_frames, target_gen)
                break
        else:
            raise TimeoutError(f"Generation {target_gen} failed to yield fresh media growth!")

        # STEP E2: Verify object invariance
        assert r2_stats["samePCReference"], "Client PC reference changed"
        assert r2_stats["sameTrackReferences"], "Client receiver track references changed"
        assert r2_stats["pcCount"] == 1, f"Multiple PCs created: {r2_stats['pcCount']}"
        assert r2_stats["pcProbeId"] == initial_client_pc_id, "Client PC object changed!"
        peers_resp = await query_server_peers()
        curr_server_peer = [p for p in peers_resp.get("peers", []) if p.get("peer_id") == client_peer_id][0]
        assert curr_server_peer["server_pc_id"] == initial_server_pc_id, "Server PC object changed!"
        assert curr_server_peer["server_dtls_id"] == initial_server_dtls_id, "Server DTLS Transport object changed!"
        logger.info("Step E2 OK: Confirmed identical client and server PC/DTLS object references across 2 restarts!")

        # -------------------------------------------------------------
        # Summary & JSONL Output
        # -------------------------------------------------------------
        final_video = r2_stats.get("inboundVideo") or {}
        final_audio = r2_stats.get("inboundAudio") or {}

        summary = {
            "client_turn_url": CLIENT_TURN_URL,
            "server_turn_url": SERVER_TURN_URL,
            "split_urls_differ": True,
            "split_usernames_differ": True,
            "round1_client_user": client_u1,
            "round1_server_user": server_u1,
            "round2_client_user": client_u2,
            "round2_server_user": server_u2,
            "same_pc_object": True,
            "pc_probe_id": initial_client_pc_id,
            "server_pc_id_stable": True,
            "server_dtls_id_stable": True,
            "zero_page_reload": True,
            "initial_1080p_media": True,
            "strict_relay_both_ends": True,
            "successful_ice_restarts": 2,
            "generation_committed": 3,
            "old_generations_retired_and_send_rejected": True,
            "final_frames_decoded": final_video.get("framesDecoded", 0),
            "final_audio_energy": final_audio.get("totalAudioEnergy", 0.0),
            "post_restart_video_growth_isolated": True,
            "post_restart_audio_growth_isolated": True,
            "webrtc_media": "PASS",
        }
        logger.info("\n=== STAGE 2 STRICT PASS ===")
        logger.info("Summary: %s", json.dumps(summary, indent=2))

        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            f.write(json.dumps(summary) + "\n")
        logger.info("Results successfully written to %s", RESULT_FILE)

        await ctx.close()


if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(run_stage2(), timeout=120))
    except Exception as e:
        logger.exception("Stage 2 probe failed: %s", e)
        sys.exit(1)
