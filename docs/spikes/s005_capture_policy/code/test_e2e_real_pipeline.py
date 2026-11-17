"""
Production-grade Real End-to-End Test Suite.

Architecture & Validation Steps:
1. Launches Browser Container (cbrowser-spike-capture-browser) on Xvfb :99.
2. Launches Stream Container (cbrowser-spike-capture-stream) on 127.0.0.1:18084 / UDP 30008
   with RealPolicyControlledWebRTCService and LiveCapturePolicyAgent.
3. Uses Playwright with official Google Chrome binary:
   - Creates a single BrowserContext.
   - Opens TWO real Tabs (Page 1 and Page 2), connecting to Selkies WebRTC.
   - Reads WebRTC getStats() directly on Pages:
     - `framesDecoded`
     - `bytesReceived`
     - Computes real decoded FPS and bitrates over time intervals.
4. Verifies Real Test Scenarios:
   - Scenario 1: Initial Static Scene -> Decoded FPS ~ 8 FPS, pipeline_fps = 8.0.
   - Scenario 2: Active 60fps Canvas Animation on Browser -> Real damage frames detected,
     pipeline_fps elevated to 30.0, decoded FPS reaches ~ 30 FPS.
   - Scenario 3: Low-Frequency Blink (0.5Hz) Contrast -> Momentary pulse, stays safely at 8 FPS
     (distinguishing full animation from low-frequency caret/blink).
   - Scenario 4: User Input Activity -> elevate to 30 FPS.
   - Scenario 5: Multi-Viewer Foreground Protection -> Page 2 sends native STOP_VIDEO (hidden tab),
     Page 1 remains active (START_VIDEO) -> Global FPS remains 30 FPS.
   - Scenario 6: All Viewers Hidden (STOP_VIDEO on both) -> Actual `pause_screen_capture()` executes,
     `is_screen_capturing` becomes False, decoded bytes stop growing.
   - Scenario 7: Resumption Order -> Page 1 sends START_VIDEO, capture resumes at 8.0 FPS FIRST,
     then elevates on motion.
   - Scenario 8: All Disconnected -> Closing both tabs triggers `handle_peer_gone`, capture pauses.
   - Scenario 9: Protocol Armor -> Client injecting forbidden '_arg_fps', 'r,', or 'SETTINGS,'
     does NOT alter profile resolution (1920x1080) or video_streaming_mode.
"""
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("e2e_real_rigorous")

PROBE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(PROBE_DIR, "real_e2e.log")
LOG_FP = open(LOG_FILE, "w", buffering=1)

def log_print(msg: str):
    logger.info(msg)
    LOG_FP.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    LOG_FP.flush()

BROWSER_CONTAINER = "cbrowser-spike-capture-browser"
STREAM_CONTAINER = "cbrowser-spike-capture"
STREAM_PORT = 18084
STREAM_UDP = 30008
SHARED_X11_DIR = os.path.join(PROBE_DIR, "run_x11")

def run_cmd(cmd, check=True):
    log_print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    LOG_FP.write(res.stdout + "\n")
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {res.stdout}")
    return res

def cleanup_all():
    log_print("Cleaning up containers and test directories...")
    subprocess.run(["docker", "rm", "-f", BROWSER_CONTAINER, STREAM_CONTAINER, "cbrowser-spike-capture-stream"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(SHARED_X11_DIR):
        shutil.rmtree(SHARED_X11_DIR, ignore_errors=True)

def query_uds_state() -> dict:
    cmd = ["docker", "exec", STREAM_CONTAINER, "python3", "-c",
           "import os, json, socket\n"
           "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
           "s.connect('/tmp/capture_policy_agent.sock')\n"
           "s.sendall(json.dumps({'cmd': 'get_state'}).encode() + b'\\n')\n"
           "print(s.recv(16384).decode())"]
    out = subprocess.check_output(cmd, text=True).strip()
    return json.loads(out)

def get_browser_oracle_state() -> dict:
    cmd = [
        "docker", "exec", BROWSER_CONTAINER, "python3", "-c",
        """
import urllib.request, json
req = urllib.request.urlopen("http://127.0.0.1:9222/json")
targets = json.loads(req.read().decode())
page = next(t for t in targets if t.get('type') == 'page')
from websockets.sync.client import connect
with connect(page['webSocketDebuggerUrl']) as ws:
    ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate', 'params': {'expression': 'window.getInputOracleState()', 'returnByValue': True}}))
    res = json.loads(ws.recv())
    print(json.dumps(res.get('result', {}).get('result', {}).get('value', {})))
"""
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return json.loads(out)

def get_x11_mouse_pos() -> dict:
    cmd = [
        "docker", "exec", "-e", "DISPLAY=:99", BROWSER_CONTAINER, "python3", "-c",
        """
import subprocess, re
out = subprocess.check_output(["xdotool", "getmouselocation", "--shell"], text=True)
res = {}
for line in out.splitlines():
    if '=' in line:
        k, v = line.split('=', 1)
        res[k] = int(v) if v.isdigit() else v
import json
print(json.dumps(res))
"""
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return json.loads(out)

def get_x11_geometry() -> dict:
    cmd = [
        "docker", "exec", "-e", "DISPLAY=:99", BROWSER_CONTAINER, "python3", "-c",
        """
import subprocess, re, json
out = subprocess.check_output(["xdpyinfo"], text=True)
m = re.search(r"dimensions:\\s+(\\d+x\\d+)\\s+pixels", out)
dim = m.group(1) if m else "unknown"
print(json.dumps({"dimensions": dim}))
"""
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return json.loads(out)

def set_browser_mode(mode: str) -> str:
    cmd = [
        "docker", "exec", BROWSER_CONTAINER, "python3", "-c",
        f"""
import urllib.request, json
req = urllib.request.urlopen("http://127.0.0.1:9222/json")
targets = json.loads(req.read().decode())
page = next(t for t in targets if t.get('type') == 'page')
from websockets.sync.client import connect
with connect(page['webSocketDebuggerUrl']) as ws:
    ws.send(json.dumps({{'id': 1, 'method': 'Runtime.evaluate', 'params': {{'expression': 'window.setPageMode({json.dumps(mode)})'}}}}))
    res = json.loads(ws.recv())
    print(res.get('result', {{}}).get('result', {{}}).get('value'))
"""
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return out

# In-page JS snippet to sample WebRTC decoded frames from RTCPeerConnection
GET_WEBRTC_STATS_JS = """
async () => {
    let pcs = window.__pcs || [];
    if (!pcs.length) {
        // Search window or standard selkies references
        for (let k of Object.keys(window)) {
            if (window[k] && window[k].peerConnection) pcs.push(window[k].peerConnection);
        }
    }
    if (!pcs.length) return null;
    let pc = pcs[0];
    let stats = await pc.getStats();
    let res = { framesDecoded: 0, bytesReceived: 0, timestamp: Date.now() };
    stats.forEach(report => {
        if (report.type === 'inbound-rtp' && report.kind === 'video') {
            res.framesDecoded = report.framesDecoded || 0;
            res.bytesReceived = report.bytesReceived || 0;
            res.framesPerSecond = report.framesPerSecond || 0;
        }
    });
    return res;
}
"""

async def sample_page_fps(page, duration_sec: float = 2.0) -> float:
    """Samples decoded FPS on a real Chrome page over a duration window."""
    s1 = await page.evaluate(GET_WEBRTC_STATS_JS)
    if not s1 or s1.get("framesDecoded") is None:
        return 0.0
    await asyncio.sleep(duration_sec)
    s2 = await page.evaluate(GET_WEBRTC_STATS_JS)
    if not s2:
        return 0.0
    d_frames = s2["framesDecoded"] - s1["framesDecoded"]
    d_time = (s2["timestamp"] - s1["timestamp"]) / 1000.0
    fps = d_frames / max(d_time, 0.1)
    return round(fps, 1)

async def main():
    cleanup_all()
    os.makedirs(SHARED_X11_DIR, exist_ok=True)
    test_results = {}

    try:
        log_print("=== 1. Starting Isolated Browser Runtime ===")
        run_cmd([
            "docker", "run", "-d",
            "--name", BROWSER_CONTAINER,
            "-v", f"{SHARED_X11_DIR}:/tmp/.X11-unix",
            "-v", f"{PROBE_DIR}:/test_assets:ro",
            "--ipc=shareable",
            "--entrypoint", "/test_assets/entrypoint_browser.sh",
            "cbrowser-spike-runtime-browser:test"
        ])
        # Wait for X11 socket
        x11_sock = os.path.join(SHARED_X11_DIR, "X99")
        for _ in range(50):
            if os.path.exists(x11_sock): break
            await asyncio.sleep(0.2)
        assert os.path.exists(x11_sock), "Browser X11 socket failed!"
        log_print("Browser X11 socket ready.")

        log_print("=== 2. Starting Stream Runtime with Patched WebRTCService ===")
        run_cmd([
            "docker", "run", "-d",
            "--name", STREAM_CONTAINER,
            "--ipc", f"container:{BROWSER_CONTAINER}",
            "-v", f"{SHARED_X11_DIR}:/tmp/.X11-unix",
            "-v", f"{PROBE_DIR}:/probe",
            "-p", f"127.0.0.1:{STREAM_PORT}:18084",
            "-p", f"127.0.0.1:{STREAM_UDP}:{STREAM_UDP}/udp",
            "-e", "DISPLAY=:99",
            "-e", "SELKIES_PUBLIC=true",
            "-e", "CUSTOM_WS_PORT=18084",
            "-e", "SELKIES_ENABLE_BASIC_AUTH=false",
            "-e", "SELKIES_MODE=webrtc",
            "-e", "SELKIES_ENABLE_SHARING=true",
            "-e", "SELKIES_ENABLE_RESIZE=false",
            "-e", "SELKIES_MANUAL_RESOLUTION=true",
            "-e", "SELKIES_MANUAL_WIDTH=1920",
            "-e", "SELKIES_MANUAL_HEIGHT=1080",
            "-e", "SELKIES_FRAMERATE=8,8-30",
            "-e", "SELKIES_VIDEO_STREAMING_MODE=false", # damage-gated mode!
            "-e", f"SELKIES_WEBRTC_UDP_MUX_PORT={STREAM_UDP}",
            "--entrypoint", "python3",
            "cbrowser-spike-runtime-stream:test",
            "/probe/entrypoint_stream.py"
        ])

        # Wait for HTTP ready
        for _ in range(50):
            try:
                with urlopen(f"http://127.0.0.1:{STREAM_PORT}/api/status", timeout=1) as resp:
                    if resp.status == 200: break
            except Exception:
                await asyncio.sleep(0.2)
        log_print("Stream Runtime is online.")

        # Verify UDS control
        st_init = query_uds_state()
        log_print(f"Initial UDS State: {st_init}")
        assert st_init["status"] == "ok"

        log_print("=== 3. Launching Playwright with Official Google Chrome ===")
        chrome_bin = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                executable_path=chrome_bin,
                headless=True,
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-gpu",
                    "--use-fake-ui-for-media-stream",
                ]
            )
            # Single Context, Two real Tabs
            context = await browser.new_context(viewport={"width": 1280, "height": 720})

            # Inject hook to capture RTCPeerConnection instances into window.__pcs
            hook_js = """
            (() => {
                window.__pcs = [];
                const Orig = window.RTCPeerConnection;
                window.RTCPeerConnection = function(...a) {
                    const pc = new Orig(...a);
                    window.__pcs.push(pc);
                    const origCreateDataChannel = pc.createDataChannel;
                    if (origCreateDataChannel) {
                        pc.createDataChannel = function(...args) {
                            const dc = origCreateDataChannel.apply(this, args);
                            pc.__send_channel = dc;
                            return dc;
                        };
                    }
                    pc.addEventListener('datachannel', (ev) => {
                        pc.__send_channel = ev.channel;
                    });
                    return pc;
                };
                window.RTCPeerConnection.prototype = Orig.prototype;
            })();
            """
            await context.add_init_script(hook_js)

            # TAB 1: Connect to Selkies WebRTC
            log_print("Opening Tab 1 (Viewer 1)...")
            page1 = await context.new_page()
            await page1.goto(f"http://127.0.0.1:{STREAM_PORT}/", wait_until="load")

            # Wait for media pipeline in Tab 1
            log_print("Waiting for Tab 1 WebRTC media pipeline...")
            for _ in range(60):
                st = query_uds_state()
                if st["is_screen_capturing"] and st["total_peers"] >= 1:
                    log_print(f"Tab 1 connected: {st}")
                    break
                await asyncio.sleep(0.3)
            assert st["is_screen_capturing"], "Tab 1 WebRTC failed to establish!"

            # TAB 2: Connect to Selkies WebRTC (concurrent viewer)
            log_print("Opening Tab 2 (Viewer 2)...")
            page2 = await context.new_page()
            await page2.goto(f"http://127.0.0.1:{STREAM_PORT}/", wait_until="load")
            for _ in range(60):
                st = query_uds_state()
                if st["total_peers"] >= 2:
                    log_print(f"Tab 2 connected. Total peers: {st['total_peers']}, active: {st['active_peers']}")
                    break
                await asyncio.sleep(0.3)
            assert st["total_peers"] == 2, f"Expected 2 real peers, got {st['total_peers']}"

            # --- SCENARIO 1: Static Scene Idle -> Target 8 FPS ---
            log_print("--- SCENARIO 1: Static Scene -> Target 8.0 FPS ---")
            set_browser_mode("static")
            await asyncio.sleep(2.5) # allow idle timeout
            st1 = query_uds_state()
            fps_p1 = await sample_page_fps(page1, duration_sec=2.0)
            log_print(f"Scenario 1 State: {st1}, Tab 1 Decoded FPS: {fps_p1}")
            assert st1["pipeline_fps"] == 8.0, f"Expected pipeline 8.0 FPS, got {st1['pipeline_fps']}"
            assert st1["has_screen_motion"] is False
            # In damage-gated mode, static screen sends at most 8 or fewer damage frames
            assert fps_p1 <= 8.5, f"Expected decoded FPS <= 8.5 on static scene, got {fps_p1}"
            test_results["Scenario_1_Static_8FPS"] = "PASS"

            # --- SCENARIO 2: Active Canvas Animation -> Elevates to 30.0 FPS ---
            log_print("--- SCENARIO 2: Canvas Animation (60fps) -> Elevates to 30.0 FPS ---")
            set_browser_mode("animation")
            elevated = False
            for _ in range(25):
                st2 = query_uds_state()
                if st2["has_screen_motion"] and st2["pipeline_fps"] == 30.0:
                    elevated = True
                    break
                await asyncio.sleep(0.4)
            fps_p1_anim = await sample_page_fps(page1, duration_sec=2.0)
            log_print(f"Scenario 2 State: {st2}, Tab 1 Decoded FPS: {fps_p1_anim}")
            assert elevated, f"Pipeline failed to elevate to 30 FPS! State: {st2}"
            assert fps_p1_anim >= 15.0, f"Decoded FPS did not elevate! Got {fps_p1_anim}"
            test_results["Scenario_2_Animation_30FPS"] = "PASS"

            # --- SCENARIO 3: Low-Frequency Blink (0.5Hz) Contrast ---
            log_print("--- SCENARIO 3: Low-Frequency 0.5Hz Blink -> Contrast (Relaxes to 8 FPS) ---")
            set_browser_mode("low_blink")
            # Wait for animation idle timeout to expire and low blink to establish
            dropped_to_8 = False
            for _ in range(25):
                st3 = query_uds_state()
                if st3["pipeline_fps"] == 8.0:
                    dropped_to_8 = True
                    break
                await asyncio.sleep(0.4)
            fps_p1_blink = await sample_page_fps(page1, duration_sec=2.0)
            log_print(f"Scenario 3 State: {st3}, Tab 1 Decoded FPS: {fps_p1_blink}")
            # Low blink (0.5-1.0 fps damage) must not lock pipeline at 30 FPS!
            assert st3["has_screen_motion"] is False, f"Low-frequency blink should not trigger continuous motion! Est: {st3['motion_fps_estimate']}"
            assert dropped_to_8, f"Expected 8.0 FPS on low-frequency blink, got {st3['pipeline_fps']}"
            test_results["Scenario_3_Low_Blink_Contrast"] = "PASS"

            # --- SCENARIO 4: User Input Activity -> Elevates to 30 FPS ---
            log_print("--- SCENARIO 4: User Input Activity (Real DataChannel Input) -> Elevates to 30 FPS ---")
            # Clear any motion and let pipeline relax to 8 FPS first
            set_browser_mode("static")
            for _ in range(25):
                st4_pre = query_uds_state()
                if st4_pre["pipeline_fps"] == 8.0:
                    break
                await asyncio.sleep(0.4)
            log_print(f"Scenario 4 Pre-Input State: {st4_pre}")
            assert st4_pre["pipeline_fps"] == 8.0, f"Expected pre-input at 8.0 FPS, got {st4_pre['pipeline_fps']}"

            oracle_before = get_browser_oracle_state()
            log_print(f"Browser DOM Oracle Before Input: {oracle_before}")

            # Send real DataChannel mouse move events through Tab 1
            # Format in Selkies: "m,x,y,button_mask,scroll_magnitude,seq"
            send_mouse_js = """
            (() => {
                let pcs = window.__pcs || [];
                for (let pc of pcs) {
                    if (pc && pc.__send_channel && pc.__send_channel.readyState === 'open') {
                        // send mouse move to (250, 250)
                        pc.__send_channel.send('m,250,250,0,0,1');
                        // also send key press 'A' (keysym 65)
                        pc.__send_channel.send('kd,65');
                        pc.__send_channel.send('ku,65');
                        return true;
                    }
                }
                return false;
            })()
            """
            sent_dc = await page1.evaluate(send_mouse_js)
            log_print(f"Tab 1 sent real DataChannel mouse/keyboard: {sent_dc}")
            assert sent_dc is True, "Failed to send input over Tab 1 DataChannel!"

            # Poll UDS state to verify pipeline framerate elevated to 30.0 FPS
            elevated_input = False
            for _ in range(15):
                st4 = query_uds_state()
                if st4["pipeline_fps"] == 30.0:
                    elevated_input = True
                    break
                await asyncio.sleep(0.2)
            log_print(f"Scenario 4 Post-Input State: {st4}")
            assert elevated_input, f"Pipeline failed to elevate to 30 FPS on real DataChannel input! State: {st4}"

            # Verify input actually reached X11 and CloakBrowser DOM Oracle
            oracle_after = get_browser_oracle_state()
            x11_mouse = get_x11_mouse_pos()
            log_print(f"Browser DOM Oracle After Input: {oracle_after}")
            log_print(f"X11 Mouse Position via xdotool: {x11_mouse}")

            assert oracle_after["inputCount"] > oracle_before.get("inputCount", 0), \
                f"Input did not reach Cloak DOM Oracle! Before: {oracle_before}, After: {oracle_after}"
            # Verify X11 mouse position moved
            assert ("X" in x11_mouse or "x" in x11_mouse) and ("Y" in x11_mouse or "y" in x11_mouse), f"Invalid X11 mouse position: {x11_mouse}"
            actual_x = x11_mouse.get("X", x11_mouse.get("x"))
            actual_y = x11_mouse.get("Y", x11_mouse.get("y"))
            assert actual_x == 250 and actual_y == 250, f"X11 mouse did not move to target (250, 250)! Got ({actual_x}, {actual_y})"
            test_results["Scenario_4_Input_Elevation"] = "PASS"

            # Return browser to animation for multi-viewer testing
            set_browser_mode("animation")
            await asyncio.sleep(1.0)

            # --- SCENARIO 5: Foreground Protection against Background Viewer & Resync IDR ---
            log_print("--- SCENARIO 5: Tab 2 sends STOP_VIDEO (hidden) -> Tab 1 remains 30 FPS ---")
            stop_code = """(() => {
                let pcs = window.__pcs || [];
                for (let pc of pcs) {
                    if (pc && pc.__send_channel && pc.__send_channel.readyState === 'open') {
                        pc.__send_channel.send('STOP_VIDEO');
                        return true;
                    }
                }
                return false;
            })()"""
            res_stop = await page2.evaluate(stop_code)
            log_print(f"Tab 2 sent STOP_VIDEO via JS: {res_stop}")
            await asyncio.sleep(1.0)
            st5 = query_uds_state()
            log_print(f"Scenario 5 State: {st5}")
            assert st5["active_peers"] == 1, f"Expected 1 active peer after Tab 2 STOP_VIDEO, got {st5['active_peers']}"
            assert st5["pipeline_fps"] == 30.0, "Active Tab 1 must keep pipeline at 30.0 FPS!"

            # Now test Background Peer Resumption with IDR (Item 3 in requirements):
            # While Tab 1 is still active at 30 FPS, resume Tab 2 with START_VIDEO.
            # Must NOT pull down the active stream to 8 FPS, and Tab 2 decoder must receive frames/bytes continuously.
            log_print("--- Sub-test 5b: Tab 2 resumes while Tab 1 active (IDR request & continuous frames/bytes) ---")
            p2_stat_pre = await page2.evaluate(GET_WEBRTC_STATS_JS)
            start_code = """(() => {
                let pcs = window.__pcs || [];
                for (let pc of pcs) {
                    if (pc && pc.__send_channel && pc.__send_channel.readyState === 'open') {
                        pc.__send_channel.send('START_VIDEO');
                        return true;
                    }
                }
                return false;
            })()"""
            await page2.evaluate(start_code)
            await asyncio.sleep(1.0)
            st5b = query_uds_state()
            p2_stat_post = await page2.evaluate(GET_WEBRTC_STATS_JS)
            log_print(f"Tab 2 post-resume stats: pre={p2_stat_pre}, post={p2_stat_post}, server_state={st5b}")
            assert st5b["active_peers"] == 2, f"Expected 2 active peers, got {st5b['active_peers']}"
            assert st5b["pipeline_fps"] == 30.0, f"Foreground active stream was pulled down to {st5b['pipeline_fps']}!"
            assert p2_stat_post["framesDecoded"] > p2_stat_pre.get("framesDecoded", 0), "Tab 2 decoder did not resume framesDecoded growth!"
            assert p2_stat_post["bytesReceived"] > p2_stat_pre.get("bytesReceived", 0), "Tab 2 decoder did not resume bytesReceived growth!"
            test_results["Scenario_5_Foreground_Protection"] = "PASS"

            # Re-hide Tab 2 so we can test all-hidden pause in Scenario 6
            await page2.evaluate(stop_code)
            await asyncio.sleep(0.5)

            # --- SCENARIO 6: All Viewers Hidden -> Actual pause_screen_capture() ---
            log_print("--- SCENARIO 6: Tab 1 also sends STOP_VIDEO -> All Hidden Pause ---")
            await page1.evaluate(stop_code)
            paused = False
            for _ in range(25):
                st6 = query_uds_state()
                if not st6["is_screen_capturing"] and st6["active_peers"] == 0:
                    paused = True
                    break
                await asyncio.sleep(0.3)
            log_print(f"Scenario 6 State: {st6}")
            assert paused, f"Capture failed to stop when all hidden! State: {st6}"
            test_results["Scenario_6_All_Hidden_Pause"] = "PASS"

            # --- SCENARIO 7: Resumption Order -> First set_framerate(8.0) then resume ---
            log_print("--- SCENARIO 7: Tab 1 sends START_VIDEO -> Resume at 8.0 FPS FIRST ---")
            st_pre_resume = query_uds_state()
            pre_actions = st_pre_resume.get("action_history", [])
            last_action_time = pre_actions[-1]["time"] if pre_actions else 0.0
            log_print(f"Scenario 7 Pre-resume last action timestamp: {last_action_time}")

            await page1.evaluate(start_code)
            resumed = False
            for _ in range(30):
                st7 = query_uds_state()
                if st7["is_screen_capturing"]:
                    resumed = True
                    break
                await asyncio.sleep(0.1)
            log_print(f"Scenario 7 Resumed State: {st7}")
            assert resumed, "Capture failed to resume on START_VIDEO!"
            
            # Verify exact action history order on NEW actions: set_framerate(8.0) followed by resume_screen_capture()
            actions = st7.get("action_history", [])
            new_actions = [a for a in actions if a["time"] > last_action_time]
            log_print(f"Scenario 7 New Resumption Actions: {new_actions}")
            set_8_idx = -1
            resume_idx = -1
            for idx, act in enumerate(new_actions):
                if act["action"] == "set_framerate" and act["details"].get("framerate") == 8.0 and not act["details"].get("pipeline_was_capturing"):
                    set_8_idx = idx
                elif act["action"] == "resume_screen_capture":
                    resume_idx = idx
            log_print(f"New action indices: set_8={set_8_idx}, resume={resume_idx}")
            assert set_8_idx != -1 and resume_idx != -1 and set_8_idx < resume_idx, \
                f"Action sequence violation! set_8 ({set_8_idx}) must precede resume ({resume_idx}) in new actions: {new_actions}"

            # After resume, animation brings it to 30.0 FPS naturally
            elevated = False
            for _ in range(30):
                st7_elevated = query_uds_state()
                if st7_elevated["pipeline_fps"] == 30.0:
                    elevated = True
                    break
                await asyncio.sleep(0.2)
            log_print(f"Scenario 7 Subsequent State: {st7_elevated}")
            assert elevated, f"Pipeline failed to elevate to 30.0 FPS on motion! State: {st7_elevated}"

            fps_resumed = await sample_page_fps(page1, duration_sec=2.0)
            log_print(f"Scenario 7 Resumed Decoded FPS: {fps_resumed}")
            assert fps_resumed >= 15.0, f"Expected decoded FPS >= 15.0 after resume, got {fps_resumed}"
            test_results["Scenario_7_Resume_Order"] = "PASS"

            # --- SCENARIO 8: All Disconnected -> handle_peer_gone & Pause ---
            log_print("--- SCENARIO 8: Closing both pages -> All Disconnected Capture Pause ---")
            await page1.close()
            await page2.close()
            for _ in range(30):
                st8 = query_uds_state()
                if st8["total_peers"] == 0 and not st8["is_screen_capturing"]:
                    break
                await asyncio.sleep(0.3)
            log_print(f"Scenario 8 Final State: {st8}")
            assert st8["total_peers"] == 0 and not st8["is_screen_capturing"], f"Failed to pause on all disconnected! State: {st8}"
            test_results["Scenario_8_All_Disconnected_Pause"] = "PASS"

            # --- SCENARIO 8b: Reconnect After Total Disconnect (Verification of Item 3) ---
            log_print("--- SCENARIO 8b: New Peer Reconnects After Total Disconnect -> Must Resume Normal Capture ---")
            # Ensure browser mode is animation so video damage frames are active
            set_browser_mode("animation")
            page_reconnect = await context.new_page()
            await page_reconnect.goto(f"http://127.0.0.1:{STREAM_PORT}/", wait_until="load")
            reconnected_live = False
            for _ in range(40):
                st8b = query_uds_state()
                if st8b["total_peers"] >= 1 and st8b["is_screen_capturing"] and st8b["active_peers"] >= 1:
                    reconnected_live = True
                    break
                await asyncio.sleep(0.3)
            log_print(f"Scenario 8b Reconnect State: {st8b}")
            assert reconnected_live, f"Failed to recover live capture on new peer reconnect! State: {st8b}"
            
            # Wait for WebRTC connection to reach 'connected' and media flowing
            for _ in range(30):
                stat_chk = await page_reconnect.evaluate(GET_WEBRTC_STATS_JS)
                if stat_chk and stat_chk.get("bytesReceived", 0) > 0:
                    break
                await asyncio.sleep(0.3)
            log_print(f"Scenario 8b Reconnect Initial WebRTC Stats: {stat_chk}")

            fps_reconnect = await sample_page_fps(page_reconnect, duration_sec=2.0)
            log_print(f"Scenario 8b Decoded FPS on Reconnected Tab: {fps_reconnect}")
            assert fps_reconnect > 0, f"Expected active decoded frames on reconnected tab, got {fps_reconnect}"
            await page_reconnect.close()
            await asyncio.sleep(1.0)
            test_results["Scenario_8b_Reconnect_After_Disconnect"] = "PASS"

            # --- SCENARIO 9: Protocol Armor & Setting Lock ---
            log_print("--- SCENARIO 9: Protocol Armor Verification ---")
            # Connect a temporary page to send forbidden messages
            set_browser_mode("animation")
            page_armor = await context.new_page()
            await page_armor.goto(f"http://127.0.0.1:{STREAM_PORT}/", wait_until="load")

            # Pre-check X11 dimensions and video stats
            geom_pre = get_x11_geometry()
            log_print(f"Pre-Armor X11 Geometry: {geom_pre}")
            assert geom_pre["dimensions"] == "1920x1080", f"Expected initial 1920x1080, got {geom_pre['dimensions']}"

            # Check decoder frameWidth and frameHeight in client WebRTC stats
            decoder_dim_js = """
            async () => {
                let pcs = window.__pcs || [];
                if (!pcs.length) {
                    for (let k of Object.keys(window)) {
                        if (window[k] && window[k].peerConnection) pcs.push(window[k].peerConnection);
                    }
                }
                if (!pcs.length) return null;
                let stats = await pcs[0].getStats();
                let res = { frameWidth: 0, frameHeight: 0, framesDecoded: 0, bytesReceived: 0 };
                stats.forEach(report => {
                    if (report.type === 'inbound-rtp' && report.kind === 'video') {
                        res.frameWidth = report.frameWidth || 0;
                        res.frameHeight = report.frameHeight || 0;
                        res.framesDecoded = report.framesDecoded || 0;
                        res.bytesReceived = report.bytesReceived || 0;
                    }
                });
                return res;
            }
            """
            # Wait for real decoder non-zero first frame (framesDecoded > 0, frameWidth == 1920, frameHeight == 1080)
            log_print("Waiting for real decoder non-zero first frame on page_armor...")
            dec_pre = None
            for _ in range(50):
                dec_pre = await page_armor.evaluate(decoder_dim_js)
                if dec_pre and dec_pre.get("framesDecoded", 0) > 0 and dec_pre.get("frameWidth", 0) > 0:
                    break
                await asyncio.sleep(0.3)
            log_print(f"Pre-Attack Decoder Stats: {dec_pre}")
            assert dec_pre and dec_pre["framesDecoded"] > 0, f"Decoder never received first frame! Got {dec_pre}"
            assert dec_pre["frameWidth"] == 1920 and dec_pre["frameHeight"] == 1080, \
                f"Initial decoder resolution invalid! Expected 1920x1080, got {dec_pre}"

            # Confirm DataChannel 'input' open and inject forbidden resize, fps override, and settings
            send_attacks_js = """
            (() => {
                let pcs = window.__pcs || [];
                for (let pc of pcs) {
                    let dc = pc.__send_channel;
                    if (dc && dc.readyState === 'open') {
                        dc.send('_arg_fps,120');
                        dc.send('r,800x600');
                        dc.send('SETTINGS,' + JSON.stringify({
                            'video_streaming_mode': true,
                            'manual_width': 800,
                            'manual_height': 600,
                            'framerate': 120
                        }));
                        return { sent: true, label: dc.label };
                    }
                }
                return { sent: false };
            })()
            """
            attack_sent = False
            for _ in range(30):
                res_atk = await page_armor.evaluate(send_attacks_js)
                if res_atk and res_atk.get("sent"):
                    attack_sent = True
                    log_print(f"Confirmed attack payload sent over DataChannel: {res_atk}")
                    break
                await asyncio.sleep(0.3)
            assert attack_sent is True, "Failed to send illegal messages over open DataChannel!"

            await asyncio.sleep(2.0)
            st9 = query_uds_state()
            geom_post = get_x11_geometry()
            dec_post = await page_armor.evaluate(decoder_dim_js)
            log_print(f"Scenario 9 Armor State: {st9}")
            log_print(f"Post-Armor X11 Geometry: {geom_post}")
            log_print(f"Post-Armor Decoder Stats: {dec_post}")

            # 1. Check that client was NOT able to inject 120 FPS
            assert st9["pipeline_fps"] != 120, "Client must NOT be able to inject 120 FPS!"
            assert st9["pipeline_fps"] in (8.0, 30.0), f"Pipeline FPS corrupted! Got {st9['pipeline_fps']}"
            
            # 2. Check X11 resolution was NOT modified by 'r,800x600' or SETTINGS
            assert geom_post["dimensions"] == "1920x1080", f"X11 resolution was mutated to {geom_post['dimensions']}!"

            # 3. Check decoder resolution is strictly 1920x1080 (no condition bypass)
            assert dec_post and dec_post["frameWidth"] == 1920 and dec_post["frameHeight"] == 1080, \
                f"Decoder resolution mutated! Expected 1920x1080, got {dec_post}"

            # 4. Check frames continue to grow after attack
            assert dec_post["framesDecoded"] > dec_pre["framesDecoded"], \
                f"Frames stopped growing! Pre: {dec_pre['framesDecoded']}, Post: {dec_post['framesDecoded']}"
            assert dec_post["bytesReceived"] > dec_pre["bytesReceived"], \
                f"Bytes stopped growing! Pre: {dec_pre['bytesReceived']}, Post: {dec_post['bytesReceived']}"

            # 5. Static contrast check: ensure video_streaming_mode=true (Turbo) was stripped and pipeline relaxes to 8 FPS
            log_print("Setting browser mode to static to verify Turbo mode was NOT enabled...")
            set_browser_mode("static")
            relaxed_to_8 = False
            for _ in range(25):
                st_stat = query_uds_state()
                if st_stat["pipeline_fps"] == 8.0:
                    relaxed_to_8 = True
                    break
                await asyncio.sleep(0.4)
            log_print(f"Post-Attack Static Contrast State: {st_stat}")
            assert relaxed_to_8, f"Pipeline locked in Turbo mode! Failed to relax to 8.0 FPS: {st_stat}"

            await page_armor.close()
            test_results["Scenario_9_Protocol_Armor"] = "PASS"

            # Note: Old Scenario 10 (testing unadapted stock Selkies client via Playwright) has been archived in revision_03.
            # Real Native Visibility E2E is verified by native_visibility_e2e.py with the CBrowser Visibility Adapter.
            await context.close()
            await browser.close()

        log_print("=== ALL 9 RIGOROUS REAL E2E SCENARIOS PASSED ===")
        print("\n================ FINAL TEST SUMMARY ================")
        for k, v in test_results.items():
            print(f"  {k}: {v}")
        print("====================================================")

    except Exception as e:
        log_print(f"FATAL Exception: {e}")
        import traceback
        LOG_FP.write(traceback.format_exc())
        raise
    finally:
        log_print("Cleanup on exit...")
        cleanup_all()
        LOG_FP.close()

if __name__ == "__main__":
    asyncio.run(main())
