#!/usr/bin/env python3
"""Run Chrome with CDP to evaluate window.isSecureContext and navigator.locks."""

import json
import os
import subprocess
import time
import urllib.request

LAN_IP = "192.168.31.76"
PORT = 54324

CADDYFILE = f"""
{{
    admin off
    auto_https disable_redirects
    default_sni {LAN_IP}
}}

https://{LAN_IP}:{PORT} {{
    tls internal
    header Content-Type "text/html; charset=utf-8"
    respond <<HTML
<!DOCTYPE html>
<html>
<head><title>Secure Context Probe</title></head>
<body>
<h1>Probe Page</h1>
</body>
</html>
HTML 200
}}
"""

def setup_caddy():
    os.makedirs("/tmp/s017_caddy", exist_ok=True)
    with open("/tmp/s017_caddy/Caddyfile", "w") as f:
        f.write(CADDYFILE)
    subprocess.run("docker rm -f s017-caddy-probe 2>/dev/null", shell=True)
    subprocess.run(f"docker run -d --name s017-caddy-probe -p 0.0.0.0:{PORT}:{PORT} -v /tmp/s017_caddy/Caddyfile:/etc/caddy/Caddyfile caddy:2-alpine", shell=True, check=True)
    time.sleep(2)

def evaluate_js_in_chrome():
    chrome_bin = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    cdp_port = 54325
    url = f"https://{LAN_IP}:{PORT}"

    cmd = [
        chrome_bin,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--ignore-certificate-errors",
        "--proxy-server=direct://",
        "--proxy-bypass-list=*",
        f"--remote-debugging-port={cdp_port}",
        url
    ]
    env = os.environ.copy()
    for k in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
        env.pop(k, None)

    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    try:
        # Get targets from CDP
        req = urllib.request.Request(f"http://127.0.0.1:{cdp_port}/json")
        with urllib.request.urlopen(req, timeout=3) as resp:
            targets = json.loads(resp.read().decode('utf-8'))

        ws_url = None
        for t in targets:
            if t.get("type") == "page":
                ws_url = t.get("webSocketDebuggerUrl")
                break

        print("Found target page WebSocket:", ws_url)
        # We can evaluate via CDP HTTP /json/version or websocket
        import asyncio
        import websockets

        async def run_eval():
            async with websockets.connect(ws_url) as ws:
                expr = """({
                    isSecureContext: window.isSecureContext,
                    hasLocks: typeof navigator.locks !== 'undefined',
                    hasRTCPeerConnection: typeof RTCPeerConnection !== 'undefined',
                    hasCryptoSubtle: typeof crypto !== 'undefined' && typeof crypto.subtle !== 'undefined',
                    protocol: window.location.protocol,
                    origin: window.location.origin
                })"""
                msg = {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True}
                }
                await ws.send(json.dumps(msg))
                resp = await ws.recv()
                data = json.loads(resp)
                return data.get("result", {}).get("result", {}).get("value")

        val = asyncio.run(run_eval())
        return val
    finally:
        proc.terminate()
        proc.wait(timeout=3)
        subprocess.run("docker rm -f s017-caddy-probe 2>/dev/null", shell=True)

def main():
    setup_caddy()
    val = evaluate_js_in_chrome()
    print("\n[+] CDP Evaluation Result:")
    print(json.dumps(val, indent=2))
    with open("docs/spikes/s017_lan_access_and_edge_rebuild/code/result_secure_context.json", "w") as f:
        json.dump(val, f, indent=2)

if __name__ == "__main__":
    main()
