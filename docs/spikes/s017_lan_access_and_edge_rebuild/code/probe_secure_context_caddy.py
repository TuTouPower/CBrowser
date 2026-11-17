#!/usr/bin/env python3
"""Probe 3 with Caddy: Chrome Secure Context (isSecureContext, Web Locks, WebRTC)
under LAN HTTPS with Caddy internal self-signed certificate.
"""

import json
import os
import subprocess
import time

LAN_IP = "192.168.31.76"
PORT = 54324

CADDYFILE = f"""
{{
    admin off
    auto_https disable_redirects
}}

https://{LAN_IP}:{PORT} {{
    tls internal
    respond <<HTML
<!DOCTYPE html>
<html>
<head><title>Secure Context Probe</title></head>
<body>
<div id="result">Testing...</div>
<script>
const result = {{{{
    isSecureContext: window.isSecureContext,
    hasLocks: typeof navigator.locks !== 'undefined',
    hasRTCPeerConnection: typeof RTCPeerConnection !== 'undefined',
    hasCryptoSubtle: typeof crypto !== 'undefined' && typeof crypto.subtle !== 'undefined',
    protocol: window.location.protocol,
    origin: window.location.origin
}}}};
document.getElementById('result').innerText = JSON.stringify(result);
console.log("PROBE_RESULT:" + JSON.stringify(result));
</script>
</body>
</html>
HTML 200
}}
"""

def run_cmd(cmd, check=True):
    return subprocess.run(cmd, shell=True, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def cleanup():
    run_cmd("docker rm -f s017-caddy-probe 2>/dev/null", check=False)

def main():
    cleanup()
    caddy_dir = "/tmp/s017_caddy"
    os.makedirs(caddy_dir, exist_ok=True)
    with open(f"{caddy_dir}/Caddyfile", "w") as f:
        f.write(CADDYFILE)

    print(f"[1] Starting Caddy container on {LAN_IP}:{PORT}...")
    run_cmd(f"docker run -d --name s017-caddy-probe -p 0.0.0.0:{PORT}:{PORT} -v {caddy_dir}/Caddyfile:/etc/caddy/Caddyfile caddy:2-alpine")
    time.sleep(2)

    chrome_bin = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    url = f"https://{LAN_IP}:{PORT}"

    print(f"[2] Running Chrome headless with --ignore-certificate-errors against {url}...")
    cmd = [
        chrome_bin,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--ignore-certificate-errors",
        "--proxy-server=direct://",
        "--proxy-bypass-list=*",
        "--dump-dom",
        url
    ]
    env = os.environ.copy()
    for k in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
        env.pop(k, None)

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10, env=env)
    print("DOM output snippet:", res.stdout[:300] if res.stdout else "EMPTY")

    probe_data = None
    if '<div id="result">' in res.stdout:
        part = res.stdout.split('<div id="result">')[1].split('</div>')[0]
        try:
            probe_data = json.loads(part)
        except Exception:
            probe_data = {"raw": part}

    print("\n=== Chrome Secure Context Result ===")
    print(json.dumps(probe_data, indent=2))

    out_path = "docs/spikes/s017_lan_access_and_edge_rebuild/code/result_secure_context.json"
    with open(out_path, "w") as f:
        json.dump(probe_data, f, indent=2)
    print(f"[+] Saved to {out_path}")

    cleanup()

if __name__ == "__main__":
    main()
