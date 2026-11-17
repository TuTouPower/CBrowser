import asyncio
import glob
from datetime import datetime
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import threading
import time
import urllib.request
import websockets

WORKDIR = os.path.abspath(os.path.dirname(__file__))
SCRATCH_DIR = os.path.join(WORKDIR, "exp_cdp_real")
CHROME_BIN = glob.glob("/root/.cloakbrowser/chromium-*/chrome")[0]

def log(msg):
    print(f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] {msg}", flush=True)

class DownloadHttpHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/download-1.txt":
            content = b"REAL_CDP_DOWNLOAD_VERIFICATION_CONTENT_FIRST_11111"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="download-1.txt"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/download-2.txt":
            content = b"REAL_CDP_DOWNLOAD_VERIFICATION_CONTENT_SECOND_22222"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="download-2.txt"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/":
            html = (
                b'<html><body>'
                b'<a id="dl1" href="/download-1.txt" download>Download 1</a>'
                b'<a id="dl2" href="/download-2.txt" download>Download 2</a>'
                b'</body></html>'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

class RealCdpAgentUdsProxy:
    """
    Browser Agent proxy running inside/alongside Browser Runtime.
    - Connects to Chrome CDP loopback WebSocket.
    - Exposes Unix Domain Socket (UDS) for Supervisor / automation.
    - Awaits CDP response on initialization and rearm to guarantee success without error.
    - Tracks client handler tasks and waits for their clean termination during shutdown.
    - Automatically re-arms download capture when an external client disconnects.
    """
    def __init__(self, browser_ws_url: str, uds_path: str, default_download_dir: str):
        self.browser_ws_url = browser_ws_url
        self.uds_path = uds_path
        self.default_download_dir = default_download_dir
        self.server = None
        self.agent_cdp_ws = None
        self.client_tasks = set()
        self.download_events = []
        self._next_cmd_id = 9000
        self.rearm_count = 0
        self.pending_rearm_futures = {}
        self.shutting_down = False

    async def start(self):
        self.agent_cdp_ws = await websockets.connect(self.browser_ws_url, max_size=10*1024*1024)
        asyncio.create_task(self._listen_agent_events())

        # Arm initial download behavior and strictly wait for CDP response
        await self.rearm_download_capture()

        if os.path.exists(self.uds_path):
            os.remove(self.uds_path)
        self.server = await asyncio.start_unix_server(self._client_connected, path=self.uds_path)
        log(f"Agent UDS listening at {self.uds_path}")

    async def rearm_download_capture(self, timeout=5.0):
        if self.shutting_down or not self.agent_cdp_ws:
            return
        self._next_cmd_id += 1
        cid = self._next_cmd_id
        req = {
            "id": cid,
            "method": "Browser.setDownloadBehavior",
            "params": {
                "behavior": "allowAndName",
                "downloadPath": self.default_download_dir,
                "eventsEnabled": True,
            }
        }
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self.pending_rearm_futures[cid] = fut
        await self.agent_cdp_ws.send(json.dumps(req))
        log(f"Agent sent rearm command cid={cid}, awaiting CDP response...")
        resp = await asyncio.wait_for(fut, timeout=timeout)
        if "error" in resp:
            raise RuntimeError(f"CDP error rearming download behavior: {resp['error']}")
        self.rearm_count += 1
        log(f"Agent rearm verified by CDP response: {resp} (rearm_count={self.rearm_count})")

    async def _listen_agent_events(self):
        try:
            async for msg in self.agent_cdp_ws:
                data = json.loads(msg)
                msg_id = data.get("id")
                if msg_id in self.pending_rearm_futures:
                    fut = self.pending_rearm_futures.pop(msg_id)
                    if not fut.done():
                        fut.set_result(data)
                method = data.get("method")
                if method and ("download" in method.lower() or "Download" in method):
                    self.download_events.append(data)
                    log(f"Agent received CDP event: {method} params={data.get('params')}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if not self.shutting_down:
                log(f"Agent event listener error: {e}")

    def _client_connected(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        if self.shutting_down:
            writer.close()
            return
        task = asyncio.create_task(self._handle_client(reader, writer))
        self.client_tasks.add(task)
        task.add_done_callback(self.client_tasks.discard)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        log("Client connected via UDS")
        client_ws = None
        try:
            client_ws = await websockets.connect(self.browser_ws_url, max_size=10*1024*1024)
            
            async def uds_to_ws():
                while True:
                    line = await reader.readline()
                    if not line:
                        break
                    msg = line.decode().strip()
                    if msg:
                        await client_ws.send(msg)

            async def ws_to_uds():
                async for msg in client_ws:
                    writer.write((msg + "\n").encode())
                    await writer.drain()

            done, pending = await asyncio.wait(
                [asyncio.create_task(uds_to_ws()), asyncio.create_task(ws_to_uds())],
                return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
        except Exception as e:
            if not self.shutting_down:
                log(f"Client tunnel error: {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            if client_ws:
                await client_ws.close()
            log("Client disconnected from UDS")
            if not self.shutting_down:
                # AUTOMATIC RECOVERY triggered by client disconnect
                await self.rearm_download_capture()

    async def close(self):
        self.shutting_down = True
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        # Wait for all client tasks to finish clean up
        if self.client_tasks:
            log(f"Waiting for {len(self.client_tasks)} client task(s) to exit...")
            for t in list(self.client_tasks):
                t.cancel()
            await asyncio.gather(*self.client_tasks, return_exceptions=True)
        # Finally close management WS
        if self.agent_cdp_ws:
            await self.agent_cdp_ws.close()
        log("Agent UDS Proxy closed cleanly.")


async def run_experiment():
    if os.path.exists(SCRATCH_DIR):
        shutil.rmtree(SCRATCH_DIR)
    os.makedirs(SCRATCH_DIR, exist_ok=True)

    user_data_dir = os.path.join(SCRATCH_DIR, "chrome_user_data")
    default_download_dir = os.path.join(SCRATCH_DIR, "cbrowser_downloads")
    external_download_dir = os.path.join(SCRATCH_DIR, "external_downloads")
    uds_path = os.path.join(SCRATCH_DIR, "agent.sock")
    os.makedirs(user_data_dir, exist_ok=True)
    os.makedirs(default_download_dir, exist_ok=True)
    os.makedirs(external_download_dir, exist_ok=True)

    # 1. Start local HTTP server
    httpd = socketserver.TCPServer(("127.0.0.1", 0), DownloadHttpHandler)
    http_port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    log(f"[1] Local HTTP server running on http://127.0.0.1:{http_port}")

    # 2. Start Chrome
    chrome_cmd = [
        CHROME_BIN,
        "--headless=new",
        "--no-sandbox",
        "--remote-debugging-port=0",
        f"--user-data-dir={user_data_dir}",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"http://127.0.0.1:{http_port}/",
    ]
    log("[2] Launching Chrome on an automatically allocated CDP port...")
    chrome_proc = subprocess.Popen(chrome_cmd)

    agent_proxy = None
    try:
        # Wait for CDP HTTP endpoint
        browser_ws_url = None
        for _ in range(50):
            await asyncio.sleep(0.2)
            if chrome_proc.poll() is not None:
                raise RuntimeError("Test Chrome exited before CDP became ready")
            try:
                with open(os.path.join(user_data_dir, "DevToolsActivePort")) as active_port:
                    cdp_port = int(active_port.readline())
                with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/version", timeout=1) as resp:
                    data = json.loads(resp.read().decode())
                    browser_ws_url = data.get("webSocketDebuggerUrl")
                    if browser_ws_url:
                        break
            except Exception:
                pass

        if not browser_ws_url:
            raise RuntimeError("Failed to reach Chrome CDP HTTP endpoint")
        log(f"[3] Chrome ready: {browser_ws_url}")

        # 3. Start Browser Agent Proxy
        agent_proxy = RealCdpAgentUdsProxy(browser_ws_url, uds_path, default_download_dir)
        await agent_proxy.start()
        assert agent_proxy.rearm_count == 1

        async def send_cmd(reader, writer, method, params, cid, timeout=5.0):
            req = {"id": cid, "method": method, "params": params}
            writer.write((json.dumps(req) + "\n").encode())
            await writer.drain()
            start = time.time()
            while time.time() - start < timeout:
                line = await asyncio.wait_for(reader.readline(), timeout=timeout)
                if not line:
                    raise EOFError("UDS closed")
                msg = json.loads(line.decode())
                if msg.get("id") == cid:
                    return msg
            raise TimeoutError(f"Timeout waiting for response cid={cid}")

        # 4. Trigger First Download via Supervisor connection over UDS
        log("[4] Supervisor connects to Agent UDS...")
        sup_r, sup_w = await asyncio.open_unix_connection(uds_path)

        targets_resp = await send_cmd(sup_r, sup_w, "Target.getTargets", {}, 10)
        page_target = None
        for t in targets_resp.get("result", {}).get("targetInfos", []):
            if t.get("type") == "page":
                page_target = t
                break
        log(f"[5] Page target found: {page_target.get('targetId')}")

        attach_resp = await send_cmd(sup_r, sup_w, "Target.attachToTarget", {"targetId": page_target["targetId"], "flatten": True}, 11)
        session_id = attach_resp.get("result", {}).get("sessionId")
        log(f"[6] Attached to page sessionId={session_id}")

        # Trigger download 1
        log("[7] Triggering download 1 (dl1)...")
        click_cmd1 = {
            "id": 12,
            "sessionId": session_id,
            "method": "Runtime.evaluate",
            "params": {"expression": "document.getElementById('dl1').click()"}
        }
        sup_w.write((json.dumps(click_cmd1) + "\n").encode())
        await sup_w.drain()

        # Wait for first download completion
        log("[8] Waiting for download 1 completion event...")
        guid1 = None
        for _ in range(30):
            await asyncio.sleep(0.2)
            for ev in agent_proxy.download_events:
                p = ev.get("params", {})
                if ev.get("method") == "Browser.downloadProgress" and p.get("state") == "completed":
                    guid1 = p.get("guid")
                    break
            if guid1:
                break

        assert guid1, "Download 1 did not complete!"
        log(f"[9] Download 1 completed via CDP: guid={guid1}")
        file1 = os.path.join(default_download_dir, guid1)
        assert os.path.exists(file1), f"File {file1} not found!"
        with open(file1, "rb") as f:
            c1 = f.read()
        assert c1 == b"REAL_CDP_DOWNLOAD_VERIFICATION_CONTENT_FIRST_11111"
        log(f"[10] Download 1 verified in default directory: {file1}, content correct.")

        # 5. External Automation Connects & Overrides Download Behavior
        log("[11] External automation connects and overrides downloadPath to external_downloads...")
        ext_r, ext_w = await asyncio.open_unix_connection(uds_path)
        ext_override_resp = await send_cmd(
            ext_r, ext_w,
            "Browser.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": external_download_dir, "eventsEnabled": False},
            99
        )
        log(f"[12] External automation override confirmed: {ext_override_resp}")

        # 6. External Automation Detaches -> Agent automatically re-arms
        log("[13] External automation disconnecting...")
        ext_w.close()
        await ext_w.wait_closed()

        # Wait briefly for Agent re-arm with verified CDP response
        await asyncio.sleep(0.5)
        log(f"[14] Agent rearm_count after disconnect: {agent_proxy.rearm_count}")
        assert agent_proxy.rearm_count >= 2, "Agent failed to auto re-arm!"

        # 7. PROOF OF RECOVERY: Trigger Second Real Download
        log("[15] Triggering download 2 (dl2) to verify download recovery in action...")
        agent_proxy.download_events.clear()
        click_cmd2 = {
            "id": 13,
            "sessionId": session_id,
            "method": "Runtime.evaluate",
            "params": {"expression": "document.getElementById('dl2').click()"}
        }
        sup_w.write((json.dumps(click_cmd2) + "\n").encode())
        await sup_w.drain()

        log("[16] Waiting for download 2 completion event...")
        guid2 = None
        for _ in range(30):
            await asyncio.sleep(0.2)
            for ev in agent_proxy.download_events:
                p = ev.get("params", {})
                if ev.get("method") == "Browser.downloadProgress" and p.get("state") == "completed":
                    guid2 = p.get("guid")
                    break
            if guid2:
                break

        assert guid2, "Download 2 did not complete!"
        assert guid2 != guid1, "Download 2 produced duplicate guid!"
        log(f"[17] Download 2 completed via CDP: guid={guid2}")

        # Verify download 2 landed in default_download_dir with allowAndName (named by guid2)
        file2 = os.path.join(default_download_dir, guid2)
        assert os.path.exists(file2), f"Download 2 file {file2} not found in default_download_dir!"
        with open(file2, "rb") as f:
            c2 = f.read()
        assert c2 == b"REAL_CDP_DOWNLOAD_VERIFICATION_CONTENT_SECOND_22222", "Content mismatch for download 2!"
        log(f"[18] Download 2 successfully verified in default directory: {file2}")

        # STRICT CHECK: Verify external_downloads directory is completely EMPTY!
        ext_files = os.listdir(external_download_dir)
        log(f"[19] Checking external_downloads directory contents: {ext_files}")
        assert len(ext_files) == 0, f"external_downloads is not empty: {ext_files}"
        log("[20] VERIFIED: external_downloads contains 0 files. Recovery is 100% genuine!")

        # Clean supervisor connection
        sup_w.close()
        await sup_w.wait_closed()
        log("ALL REAL CDP & SECOND DOWNLOAD RECOVERY VERIFICATIONS PASSED!")
        return True

    finally:
        if agent_proxy:
            await agent_proxy.close()
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            chrome_proc.kill()
        httpd.shutdown()
        log("[Done] Process cleanup completed.")

async def main():
    # Overall execution timeout: 45 seconds
    try:
        await asyncio.wait_for(run_experiment(), timeout=45.0)
    except TimeoutError:
        log("ERROR: Global experiment timeout exceeded!")
        raise

if __name__ == "__main__":
    asyncio.run(main())
