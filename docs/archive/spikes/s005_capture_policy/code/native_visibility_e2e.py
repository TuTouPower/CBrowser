"""
Production-grade Real Native Chrome Page Visibility End-to-End Suite.

Validates Native Chrome Page Visibility with Thin CBrowser Visibility Adapter:
- Subprocess isolated Google Chrome with own profile in tmp/
- CDP direct communication via websockets
- Two real tabs in the same window (Target.createTarget with newWindow=False)
- Thin CBrowser Visibility Adapter listening to real document.visibilitychange
- Validates:
  1. 2 Real PCs, real doc.hidden corresponds to active_peers == 1
  2. Continuous animation: foreground tab decoded ~30fps, background tab stops (delta=0)
  3. Tab switch: visibility swaps, active_peers stays 1, global pipeline stays 30.0 FPS
  4. Minimize window: both hidden -> active_peers=0 -> capture actual false (pause)
  5. Restore window: active 1 -> server trace audits set_framerate(8.0) before resume -> motion elevates to 30.0 FPS -> decoded growth resumes
  6. Close one tab -> the other continues
  7. Close all tabs -> total_peers=0, capture pauses, internal CloakBrowser does NOT exit
"""
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
import websockets

PROBE_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = os.path.join(PROBE_DIR, "tmp")
os.makedirs(TMP_DIR, exist_ok=True)
os.environ["TMPDIR"] = TMP_DIR
tempfile.tempdir = TMP_DIR

LOG_FILE = os.path.join(PROBE_DIR, "native_visibility_e2e.log")
LOG_FP = open(LOG_FILE, "w", buffering=1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("native_vis_e2e")

def log_print(msg: str):
    logger.info(msg)
    LOG_FP.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    LOG_FP.flush()

BROWSER_CONTAINER = "cbrowser-spike-capture-browser"
STREAM_CONTAINER = "cbrowser-spike-capture"
STREAM_PORT = 18084
STREAM_UDP = 30008
SHARED_X11_DIR = os.path.join(PROBE_DIR, "run_x11")
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

def run_cmd(cmd, check=True):
    log_print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    LOG_FP.write(res.stdout + "\n")
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {res.stdout}")
    return res

def cleanup_containers():
    log_print("Cleaning up spike containers and shared X11...")
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

# Thin CBrowser Visibility Adapter to inject into native Chrome pages
CBROWSER_VISIBILITY_ADAPTER_JS = """
(() => {
    window.__SELKIES_STREAMING_MODE__ = 'webrtc';
    window.__pcs = [];
    window.__inputDataChannels = [];

    function notifyVisibility(dc) {
        if (!dc || dc.readyState !== 'open') return;
        const msg = document.hidden ? 'STOP_VIDEO' : 'START_VIDEO';
        try {
            dc.send(msg);
            console.log('[CBrowser Adapter] Sent ' + msg + ' on ' + dc.label + ' (hidden=' + document.hidden + ')');
        } catch (e) {
            console.error('[CBrowser Adapter] Send error on ' + dc.label + ':', e);
        }
    }

    function setupDataChannel(dc) {
        if (!dc) return;
        // Strictly only handle official label === 'input' channel
        if (dc.label !== 'input') {
            console.log('[CBrowser Adapter] Skipping non-input channel label=' + dc.label);
            return;
        }
        if (window.__inputDataChannels.includes(dc)) return;
        window.__inputDataChannels.push(dc);
        window.__activeInputDC = dc;

        const onOpen = () => {
            console.log('[CBrowser Adapter] Input DataChannel open (label=' + dc.label + '), hidden=' + document.hidden);
            notifyVisibility(dc);
        };

        if (dc.readyState === 'open') {
            onOpen();
        } else {
            dc.addEventListener('open', onOpen);
        }
    }

    const OrigPC = window.RTCPeerConnection;
    if (OrigPC) {
        window.RTCPeerConnection = function(...args) {
            const pc = new OrigPC(...args);
            window.__pcs.push(pc);

            const origCreateDataChannel = pc.createDataChannel;
            if (origCreateDataChannel) {
                pc.createDataChannel = function(...dcArgs) {
                    const dc = origCreateDataChannel.apply(this, dcArgs);
                    setupDataChannel(dc);
                    return dc;
                };
            }

            pc.addEventListener('datachannel', (ev) => {
                setupDataChannel(ev.channel);
            });

            return pc;
        };
        window.RTCPeerConnection.prototype = OrigPC.prototype;
    }

    // Real document visibilitychange listener
    document.addEventListener('visibilitychange', () => {
        console.log('[CBrowser Adapter] document.visibilitychange event: hidden=' + document.hidden + ', state=' + document.visibilityState);
        for (const dc of window.__inputDataChannels) {
            notifyVisibility(dc);
        }
    });
})();
"""

GET_TARGET_STATS_JS = """
(async () => {
    let pcs = window.__pcs || [];
    if (!pcs.length) {
        for (let k of Object.keys(window)) {
            if (window[k] && window[k].peerConnection) pcs.push(window[k].peerConnection);
        }
    }
    let res = { framesDecoded: 0, bytesReceived: 0, timestamp: Date.now() };
    for (let pc of pcs) {
        try {
            let stats = await pc.getStats();
            stats.forEach(r => {
                if (r.type === 'inbound-rtp' && r.kind === 'video') {
                    res.framesDecoded = Math.max(res.framesDecoded, r.framesDecoded || 0);
                    res.bytesReceived = Math.max(res.bytesReceived, r.bytesReceived || 0);
                }
            });
        } catch (e) {}
    }
    return res;
})()
"""

async def run_scenario():
    cleanup_containers()
    os.makedirs(SHARED_X11_DIR, exist_ok=True)
    test_results = {}

    native_proc = None
    native_profile = None

    try:
        log_print("=== Step 1: Starting Browser Container ===")
        run_cmd([
            "docker", "run", "-d",
            "--name", BROWSER_CONTAINER,
            "-v", f"{SHARED_X11_DIR}:/tmp/.X11-unix",
            "-v", f"{PROBE_DIR}:/test_assets:ro",
            "--ipc=shareable",
            "--entrypoint", "/test_assets/entrypoint_browser.sh",
            "cbrowser-spike-runtime-browser:test"
        ])
        x11_sock = os.path.join(SHARED_X11_DIR, "X99")
        for _ in range(50):
            if os.path.exists(x11_sock):
                break
            await asyncio.sleep(0.2)
        assert os.path.exists(x11_sock), "Browser X11 socket failed!"
        log_print("Browser X11 socket ready.")

        log_print("=== Step 2: Starting Stream Container with Patched WebRTCService ===")
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
            "-e", "SELKIES_VIDEO_STREAMING_MODE=false",
            "-e", f"SELKIES_WEBRTC_UDP_MUX_PORT={STREAM_UDP}",
            "--entrypoint", "python3",
            "cbrowser-spike-runtime-stream:test",
            "/probe/entrypoint_stream.py"
        ])

        for _ in range(50):
            try:
                with urlopen(f"http://127.0.0.1:{STREAM_PORT}/api/status", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                await asyncio.sleep(0.2)
        log_print("Stream Runtime is online.")

        st_init = query_uds_state()
        log_print(f"Initial UDS State: {st_init}")
        assert st_init["status"] == "ok"

        # Set continuous animation on server desktop
        log_print("Enabling animation mode on CloakBrowser desktop...")
        mode_res = set_browser_mode("animation")
        log_print(f"Browser mode set result: {mode_res}")

        # Launch Native Chrome subprocess
        log_print("=== Step 3: Launching Isolated Native Chrome via Subprocess ===")
        native_profile = tempfile.mkdtemp(prefix="native_vis_profile_", dir=TMP_DIR)
        log_print(f"Native Chrome user data dir: {native_profile}")

        native_proc = subprocess.Popen([
            CHROME_BIN,
            f"--user-data-dir={native_profile}",
            "--remote-debugging-port=0",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--use-fake-ui-for-media-stream",
            "about:blank"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        active_port_file = os.path.join(native_profile, "DevToolsActivePort")
        for _ in range(100):
            if os.path.exists(active_port_file):
                break
            if native_proc.poll() is not None:
                raise RuntimeError("Own Chrome exited before DevToolsActivePort readiness")
            await asyncio.sleep(0.1)
        assert os.path.exists(active_port_file), "Failed to find DevToolsActivePort"

        with open(active_port_file) as apf:
            cdp_port, cdp_path, *_ = apf.read().splitlines()
        log_print(f"Native Chrome CDP active at 127.0.0.1:{cdp_port}{cdp_path}")

        async with websockets.connect(f"ws://127.0.0.1:{cdp_port}{cdp_path}") as ws:
            cdp_number = 0
            async def cdp_send(method, params=None, session=None):
                nonlocal cdp_number
                cdp_number += 1
                req = {"id": cdp_number, "method": method, "params": params or {}}
                if session:
                    req["sessionId"] = session
                await ws.send(json.dumps(req))
                while True:
                    pkt = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                    if pkt.get("id") == cdp_number:
                        if "error" in pkt:
                            raise RuntimeError(f"CDP error in {method}: {pkt['error']}")
                        return pkt.get("result", {})

            async def get_target_stats(sess):
                res = await cdp_send("Runtime.evaluate", {
                    "expression": GET_TARGET_STATS_JS,
                    "awaitPromise": True,
                    "returnByValue": True
                }, sess)
                val = res.get("result", {}).get("value")
                if not val or not isinstance(val, dict):
                    return {"framesDecoded": 0, "bytesReceived": 0, "timestamp": time.time() * 1000}
                return val

            async def get_target_vis(sess):
                res = await cdp_send("Runtime.evaluate", {
                    "expression": "JSON.stringify({hidden: document.hidden, state: document.visibilityState})",
                    "returnByValue": True
                }, sess)
                return json.loads(res.get("result", {}).get("value", "{}"))

            # Use initial page target as Tab 1 and create Tab 2 in the same window (newWindow=False)
            targets_info = (await cdp_send("Target.getTargets"))["targetInfos"]
            init_tab = next(t for t in targets_info if t.get("type") == "page")
            t1_id = init_tab["targetId"]
            s1_id = (await cdp_send("Target.attachToTarget", {"targetId": t1_id, "flatten": True}))["sessionId"]

            log_print("Creating Tab 2 in the same window (newWindow=False)...")
            t2_id = (await cdp_send("Target.createTarget", {"url": "about:blank", "newWindow": False}))["targetId"]
            s2_id = (await cdp_send("Target.attachToTarget", {"targetId": t2_id, "flatten": True}))["sessionId"]

            # Verify both tabs share the same window
            w1 = await cdp_send("Browser.getWindowForTarget", {"targetId": t1_id})
            w2 = await cdp_send("Browser.getWindowForTarget", {"targetId": t2_id})
            log_print(f"Tab 1 Window: {w1['windowId']}, Tab 2 Window: {w2['windowId']}")
            assert w1["windowId"] == w2["windowId"], f"Tabs must be in the same window! {w1['windowId']} vs {w2['windowId']}"

            # Inject CBrowser visibility adapter on both tabs before navigating
            await cdp_send("Page.enable", session=s1_id)
            await cdp_send("Runtime.enable", session=s1_id)
            await cdp_send("Page.addScriptToEvaluateOnNewDocument", {"source": CBROWSER_VISIBILITY_ADAPTER_JS}, session=s1_id)

            await cdp_send("Page.enable", session=s2_id)
            await cdp_send("Runtime.enable", session=s2_id)
            await cdp_send("Page.addScriptToEvaluateOnNewDocument", {"source": CBROWSER_VISIBILITY_ADAPTER_JS}, session=s2_id)

            # Navigate both tabs to Selkies WebRTC
            log_print("Navigating Tab 1 to Selkies page...")
            await cdp_send("Page.navigate", {"url": f"http://127.0.0.1:{STREAM_PORT}/"}, session=s1_id)

            log_print("Navigating Tab 2 to Selkies page...")
            await cdp_send("Page.navigate", {"url": f"http://127.0.0.1:{STREAM_PORT}/"}, session=s2_id)

            # Wait for both WebRTC peer connections to establish
            log_print("Waiting for 2 real WebRTC peer connections on server...")
            for _ in range(60):
                st_conn = query_uds_state()
                if st_conn["total_peers"] >= 2 and st_conn["is_screen_capturing"]:
                    break
                await asyncio.sleep(0.3)
            log_print(f"Connected UDS state: {st_conn}")
            assert st_conn["total_peers"] == 2, f"Expected 2 total peers, got {st_conn['total_peers']}"
            assert st_conn["is_screen_capturing"] is True, "Pipeline failed to start screen capturing"

            # --- VERIFICATION SCENARIO 1: Real doc.hidden corresponds to active_peers == 1 ---
            log_print("--- SCENARIO 1: Activate Tab 2 -> Verify real doc.hidden and active_peers == 1 ---")
            await cdp_send("Target.activateTarget", {"targetId": t2_id})

            # Poll for visibility settling, STOP_VIDEO to propagate, and motion elevation to 30 FPS
            for _ in range(35):
                st1 = query_uds_state()
                v1 = await get_target_vis(s1_id)
                v2 = await get_target_vis(s2_id)
                if (v1.get("hidden") is True and v2.get("hidden") is False and 
                        st1["active_peers"] == 1 and st1.get("pipeline_fps") == 30.0):
                    break
                await asyncio.sleep(0.3)

            log_print(f"Tab 1 Visibility: {v1}, Tab 2 Visibility: {v2}, Server State: {st1}")
            assert v1["hidden"] is True and v1["state"] == "hidden", f"Tab 1 must be hidden! Got {v1}"
            assert v2["hidden"] is False and v2["state"] == "visible", f"Tab 2 must be visible! Got {v2}"
            assert st1["active_peers"] == 1, f"Expected active_peers == 1, got {st1['active_peers']}"
            assert st1["pipeline_fps"] == 30.0, f"Foreground animation must keep pipeline at 30.0 FPS, got {st1['pipeline_fps']}"
            test_results["1_real_doc_hidden_active_peers_1"] = "PASS"

            # --- VERIFICATION SCENARIO 2: Continuous animation decoded growth vs background stopped ---
            log_print("--- SCENARIO 2: Continuous animation: foreground decoded/bytes growing, background stopped ---")
            stat1_a = await get_target_stats(s1_id)
            stat2_a = await get_target_stats(s2_id)
            await asyncio.sleep(2.0)
            stat1_b = await get_target_stats(s1_id)
            stat2_b = await get_target_stats(s2_id)

            t1_delta_frames = stat1_b["framesDecoded"] - stat1_a["framesDecoded"]
            t2_delta_frames = stat2_b["framesDecoded"] - stat2_a["framesDecoded"]
            t2_delta_bytes = stat2_b["bytesReceived"] - stat2_a["bytesReceived"]
            log_print(f"2.0s Decoded Frames: Background Tab 1={t1_delta_frames}, Foreground Tab 2={t2_delta_frames}, T2 Bytes={t2_delta_bytes}")

            assert t1_delta_frames == 0, f"Background tab decoded frames must stop! Got {t1_delta_frames}"
            assert t2_delta_frames >= 30, f"Foreground tab decoded frames must grow at ~30 FPS! Got {t2_delta_frames}"
            assert t2_delta_bytes > 0, f"Foreground tab bytesReceived must grow! Got {t2_delta_bytes}"
            test_results["2_foreground_30fps_background_stopped"] = "PASS"

            # --- VERIFICATION SCENARIO 3: Tab switch, swap foreground/background, pipeline stays 30.0 FPS ---
            log_print("--- SCENARIO 3: Switch tab to Tab 1 -> Swap foreground/background, verify global 30 FPS ---")
            await cdp_send("Target.activateTarget", {"targetId": t1_id})

            for _ in range(30):
                st3 = query_uds_state()
                v1_sw = await get_target_vis(s1_id)
                v2_sw = await get_target_vis(s2_id)
                if v1_sw.get("hidden") is False and v2_sw.get("hidden") is True and st3["active_peers"] == 1:
                    break
                await asyncio.sleep(0.3)

            log_print(f"Switched Visibility: Tab 1={v1_sw}, Tab 2={v2_sw}, Server State: {st3}")
            assert v1_sw["hidden"] is False and v1_sw["state"] == "visible", f"Tab 1 must become visible! Got {v1_sw}"
            assert v2_sw["hidden"] is True and v2_sw["state"] == "hidden", f"Tab 2 must become hidden! Got {v2_sw}"
            assert st3["active_peers"] == 1, f"Expected active_peers == 1 after switch, got {st3['active_peers']}"
            assert st3["pipeline_fps"] == 30.0, f"Pipeline framerate must NOT be pulled down below 30! Got {st3['pipeline_fps']}"

            # Verify stats swapped: Tab 1 now grows at ~30 FPS, Tab 2 stops
            stat1_sw_a = await get_target_stats(s1_id)
            stat2_sw_a = await get_target_stats(s2_id)
            await asyncio.sleep(2.0)
            stat1_sw_b = await get_target_stats(s1_id)
            stat2_sw_b = await get_target_stats(s2_id)

            t1_sw_delta_frames = stat1_sw_b["framesDecoded"] - stat1_sw_a["framesDecoded"]
            t2_sw_delta_frames = stat2_sw_b["framesDecoded"] - stat2_sw_a["framesDecoded"]
            log_print(f"Post-switch 2.0s Decoded Frames: Foreground Tab 1={t1_sw_delta_frames}, Background Tab 2={t2_sw_delta_frames}")
            assert t2_sw_delta_frames == 0, f"New background tab decoded frames must stop! Got {t2_sw_delta_frames}"
            assert t1_sw_delta_frames >= 30, f"New foreground tab decoded frames must grow at ~30 FPS! Got {t1_sw_delta_frames}"
            test_results["3_tab_switch_swap_maintains_global_30fps"] = "PASS"

            # --- VERIFICATION SCENARIO 4: Minimize window (both hidden) -> capture actual pause ---
            log_print("--- SCENARIO 4: Minimize native Chrome window -> Both hidden, capture actual pause ---")
            win_info = await cdp_send("Browser.getWindowForTarget", {"targetId": t1_id})
            win_id = win_info["windowId"]
            await cdp_send("Browser.setWindowBounds", {"windowId": win_id, "bounds": {"windowState": "minimized"}})

            for _ in range(30):
                st4 = query_uds_state()
                v1_min = await get_target_vis(s1_id)
                v2_min = await get_target_vis(s2_id)
                if v1_min.get("hidden") is True and v2_min.get("hidden") is True and st4["active_peers"] == 0 and not st4["is_screen_capturing"]:
                    break
                await asyncio.sleep(0.3)

            log_print(f"Minimized Visibility: Tab 1={v1_min}, Tab 2={v2_min}, Server State: {st4}")
            assert v1_min["hidden"] is True and v1_min["state"] == "hidden"
            assert v2_min["hidden"] is True and v2_min["state"] == "hidden"
            assert st4["active_peers"] == 0, f"Expected 0 active peers when minimized, got {st4['active_peers']}"
            assert st4["is_screen_capturing"] is False, f"Capture must pause when minimized! Got capturing={st4['is_screen_capturing']}"
            test_results["4_minimize_both_hidden_capture_paused"] = "PASS"

            # --- VERIFICATION SCENARIO 5: Restore window (active 1) -> action trace audit: set_8 then resume -> motion 30 ---
            log_print("--- SCENARIO 5: Restore window & Activate Tab 1 -> Trace audits set_8 then resume, motion 30 ---")
            st_pre_restore = query_uds_state()
            pre_restore_actions = st_pre_restore.get("action_history", [])
            last_action_time = pre_restore_actions[-1]["time"] if pre_restore_actions else 0.0
            log_print(f"Scenario 5 Pre-restore last action timestamp: {last_action_time}")

            await cdp_send("Browser.setWindowBounds", {"windowId": win_id, "bounds": {"windowState": "normal"}})
            await asyncio.sleep(0.3)
            await cdp_send("Target.activateTarget", {"targetId": t1_id})

            # Poll for capture resumption
            resumed = False
            for _ in range(30):
                st5 = query_uds_state()
                if st5["is_screen_capturing"]:
                    resumed = True
                    break
                await asyncio.sleep(0.1)

            log_print(f"Resumed State: {st5}")
            assert resumed, "Capture failed to resume after restoring minimized window!"

            # Audit action history strictly on NEW actions from this restoration event
            actions = st5.get("action_history", [])
            new_actions = [a for a in actions if a["time"] > last_action_time]
            log_print(f"Scenario 5 New Resumption Actions: {new_actions}")
            set_8_idx = -1
            resume_idx = -1
            for idx, act in enumerate(new_actions):
                if act["action"] == "set_framerate" and act["details"].get("framerate") == 8.0 and not act["details"].get("pipeline_was_capturing"):
                    set_8_idx = idx
                elif act["action"] == "resume_screen_capture":
                    resume_idx = idx

            log_print(f"New action history audit indices: set_8={set_8_idx}, resume={resume_idx}")
            assert set_8_idx != -1 and resume_idx != -1 and set_8_idx < resume_idx, \
                f"Action sequence violation! set_framerate(8.0) [{set_8_idx}] must strictly precede resume [{resume_idx}] in new actions: {new_actions}"

            # Wait for continuous motion to elevate pipeline to 30.0 FPS
            elevated_motion = False
            for _ in range(30):
                st5_elev = query_uds_state()
                if st5_elev["pipeline_fps"] == 30.0:
                    elevated_motion = True
                    break
                await asyncio.sleep(0.2)

            log_print(f"Elevated Motion State: {st5_elev}")
            assert elevated_motion, f"Pipeline failed to elevate to 30.0 FPS on motion! State: {st5_elev}"

            # Verify Tab 1 decoded frames and bytes resume active growth
            stat1_res_a = await get_target_stats(s1_id)
            await asyncio.sleep(1.5)
            stat1_res_b = await get_target_stats(s1_id)
            delta_res_frames = stat1_res_b["framesDecoded"] - stat1_res_a["framesDecoded"]
            delta_res_bytes = stat1_res_b["bytesReceived"] - stat1_res_a["bytesReceived"]
            log_print(f"Tab 1 Resumed Growth: frames={delta_res_frames}, bytes={delta_res_bytes}")
            assert delta_res_frames >= 20, f"Expected active decoded frames growth after restore! Got {delta_res_frames}"
            assert delta_res_bytes > 0, f"Expected bytes growth after restore! Got {delta_res_bytes}"
            test_results["5_restore_trace_set8_resume_and_motion_30fps"] = "PASS"

            # --- VERIFICATION SCENARIO 6: Close one tab, the other continues ---
            log_print("--- SCENARIO 6: Close Tab 2 -> Tab 1 continues unaffected ---")
            await cdp_send("Target.closeTarget", {"targetId": t2_id})
            for _ in range(25):
                st6 = query_uds_state()
                if st6["total_peers"] == 1:
                    break
                await asyncio.sleep(0.2)

            log_print(f"Tab 2 Closed State: {st6}")
            assert st6["total_peers"] == 1, f"Expected 1 total peer, got {st6['total_peers']}"
            assert st6["active_peers"] == 1, f"Expected 1 active peer, got {st6['active_peers']}"
            assert st6["is_screen_capturing"] is True, "Screen capture must continue for the remaining active tab"
            test_results["6_close_one_tab_other_continues"] = "PASS"

            # --- VERIFICATION SCENARIO 7: Close all tabs -> capture pauses, CloakBrowser does not stop ---
            log_print("--- SCENARIO 7: Close Tab 1 -> All disconnected, capture pauses, CloakBrowser alive ---")
            await cdp_send("Target.closeTarget", {"targetId": t1_id})
            for _ in range(30):
                st7 = query_uds_state()
                if st7["total_peers"] == 0 and not st7["is_screen_capturing"]:
                    break
                await asyncio.sleep(0.2)

            log_print(f"All Tabs Closed State: {st7}")
            assert st7["total_peers"] == 0, f"Expected 0 total peers, got {st7['total_peers']}"
            assert st7["is_screen_capturing"] is False, "Capture must pause when all tabs are closed"

            # Verify CloakBrowser inside BROWSER_CONTAINER is STILL alive and responding to CDP
            browser_check = subprocess.run([
                "docker", "exec", BROWSER_CONTAINER, "python3", "-c",
                "import urllib.request, json\n"
                "req = urllib.request.urlopen('http://127.0.0.1:9222/json')\n"
                "targets = json.loads(req.read().decode())\n"
                "print(len(targets))\n"
            ], stdout=subprocess.PIPE, text=True)
            log_print(f"CloakBrowser container check: exit={browser_check.returncode}, output={browser_check.stdout.strip()}")
            assert browser_check.returncode == 0, "CloakBrowser inside container died when external tabs closed!"
            test_results["7_all_closed_pause_cloakbrowser_alive"] = "PASS"

            # Clean exit for native Chrome
            await cdp_send("Browser.close")

        log_print("=== ALL NATIVE VISIBILITY E2E SCENARIOS PASSED ===")
        print("\n================ FINAL TEST SUMMARY ================")
        for k, v in test_results.items():
            print(f"  {k}: {v}")
        print("====================================================")

    except Exception as e:
        log_print(f"FATAL Exception in test: {e}")
        import traceback
        LOG_FP.write(traceback.format_exc())
        raise
    finally:
        log_print("Finally block cleanup: killing own native Chrome and stopping spike containers...")
        if native_proc is not None and native_proc.poll() is None:
            try:
                native_proc.terminate()
                native_proc.wait(timeout=3)
            except Exception:
                native_proc.kill()
        if native_profile and os.path.exists(native_profile):
            shutil.rmtree(native_profile, ignore_errors=True)
        cleanup_containers()
        LOG_FP.close()

if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(run_scenario(), timeout=120))
        sys.exit(0)
    except Exception as exc:
        print(f"E2E Test Failed: {exc}", file=sys.stderr)
        sys.exit(1)
