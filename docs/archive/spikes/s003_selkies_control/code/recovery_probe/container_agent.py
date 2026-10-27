import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import websockets

def log(msg):
    print(f"[{time.strftime('%X')}][AGENT] {msg}", flush=True)

class BrowserAgent:
    def __init__(self, run_dir, profile_id, runtime_instance_id):
        self.run_dir = run_dir
        self.profile_id = profile_id
        self.runtime_instance_id = runtime_instance_id
        self.uds_path = os.path.join(run_dir, "agent.sock")
        self.events_file = os.path.join(run_dir, "events.jsonl")
        self.cdp_port = 59227
        self.browser_proc = None
        self.browser_ws_url = None
        self.server = None
        self.exit_task = None

    async def run(self):
        log(f"Starting Browser Agent for {self.profile_id} (instance={self.runtime_instance_id})")
        # 1. Launch Xvfb
        display = ":99"
        xvfb_cmd = ["Xvfb", display, "-screen", "0", "1280x720x24"]
        log(f"Launching Xvfb on {display}...")
        xvfb_proc = subprocess.Popen(xvfb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.environ["DISPLAY"] = display

        # 2. Launch CloakBrowser binary
        from cloakbrowser.download import ensure_binary
        chrome_bin = ensure_binary()
        log(f"Using CloakBrowser binary: {chrome_bin}")

        # Isolated user data dir inside container
        user_data_dir = "/app_scratch/chrome_user_data"
        os.makedirs(user_data_dir, exist_ok=True)
        chrome_cmd = [
            chrome_bin,
            f"--remote-debugging-port={self.cdp_port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--no-sandbox",
            "about:blank",
        ]
        log(f"Launching browser: {' '.join(chrome_cmd[:4])}...")
        self.browser_proc = subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Start background monitor task
        self.exit_task = asyncio.create_task(self._wait_browser_exit())

        # Wait for CDP
        for _ in range(60):
            await asyncio.sleep(0.2)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.cdp_port}/json/version", timeout=1) as resp:
                    data = json.loads(resp.read().decode())
                    self.browser_ws_url = data.get("webSocketDebuggerUrl")
                    if self.browser_ws_url:
                        break
            except Exception:
                pass

        if not self.browser_ws_url:
            log("ERROR: Failed to connect to Chrome CDP")
            sys.exit(1)

        log(f"Browser CDP ready: {self.browser_ws_url}")

        # Start UDS server
        if os.path.exists(self.uds_path):
            os.remove(self.uds_path)
        self.server = await asyncio.start_unix_server(self._handle_client, path=self.uds_path)
        log(f"Agent UDS listening at {self.uds_path}")

        # AWAIT browser process exit and event persistence completely!
        log("Agent waiting for browser process exit and persistence task...")
        await self.exit_task
        log("Exit persistence task completed. Shutting down Agent server...")

        if self.server:
            self.server.close()
            await self.server.wait_closed()
        xvfb_proc.terminate()
        try:
            xvfb_proc.wait(timeout=2)
        except Exception:
            xvfb_proc.kill()
        log("Agent shutdown complete.")

    async def _handle_client(self, reader, writer):
        log("Supervisor connected via UDS")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                req = json.loads(line.decode().strip())
                cmd = req.get("cmd")
                cid = req.get("id", 1)

                if cmd == "close_browser":
                    log("Received close_browser RPC. Triggering CDP Browser.close...")
                    try:
                        async with websockets.connect(self.browser_ws_url) as ws:
                            await ws.send(json.dumps({"id": 9999, "method": "Browser.close"}))
                            try:
                                resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
                                log(f"Browser.close CDP response: {resp}")
                            except Exception:
                                pass
                        writer.write((json.dumps({"id": cid, "status": "ok"}) + "\n").encode())
                        await writer.drain()
                    except Exception as e:
                        log(f"Error during Browser.close: {e}")
                        writer.write((json.dumps({"id": cid, "status": "error", "error": str(e)}) + "\n").encode())
                        await writer.drain()
                elif cmd == "ping":
                    writer.write((json.dumps({"id": cid, "status": "pong", "runtime_instance_id": self.runtime_instance_id}) + "\n").encode())
                    await writer.drain()
                else:
                    writer.write((json.dumps({"id": cid, "error": "unknown_cmd"}) + "\n").encode())
                    await writer.drain()
        except Exception as e:
            log(f"Client handler error: {e}")
        finally:
            writer.close()

    async def _wait_browser_exit(self):
        loop = asyncio.get_running_loop()
        exit_code = await loop.run_in_executor(None, self.browser_proc.wait)
        log(f"Detected browser process exit, returncode={exit_code}")
        event = {
            "event_id": f"evt_exit_{int(time.time()*1000)}",
            "profile_id": self.profile_id,
            "runtime_instance_id": self.runtime_instance_id,
            "exit_code": exit_code,
            "exit_reason": "browser_closed" if exit_code == 0 else "process_crash",
            "timestamp": time.time(),
        }
        # ATOMIC WRITE: append to tmp, fsync, replace
        # If events_file exists, read existing lines first
        existing_lines = []
        if os.path.exists(self.events_file):
            with open(self.events_file, "r", encoding="utf-8") as f:
                existing_lines = [l.strip() for l in f if l.strip()]

        existing_lines.append(json.dumps(event))

        tmp_path = self.events_file + f".tmp.{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            for l in existing_lines:
                f.write(l + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.events_file)
        log(f"Persisted exit event atomically: {event['event_id']} (code={exit_code})")

if __name__ == "__main__":
    r_dir = sys.argv[1]
    p_id = sys.argv[2]
    inst_id = sys.argv[3]
    asyncio.run(BrowserAgent(r_dir, p_id, inst_id).run())
