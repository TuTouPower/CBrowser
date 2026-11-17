#!/usr/bin/env python3
"""Run Chrome dump-dom with correct Content-Type to evaluate secure context."""

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
<div id="result">WAITING</div>
<script>
const result = {{
    isSecureContext: window.isSecureContext,
    hasLocks: typeof navigator.locks !== 'undefined',
    hasRTCPeerConnection: typeof RTCPeerConnection !== 'undefined',
    hasCryptoSubtle: typeof crypto !== 'undefined' && typeof crypto.subtle !== 'undefined',
    protocol: window.location.protocol,
    origin: window.location.origin
}};
document.getElementById('result').innerText = JSON.stringify(result);
</script>
</body>
</html>
HTML 200
}}
"""

def setup_caddy():
    os.makedirs("/tmp/s017_caddy", exist_ok=True)
    with open("/tmp/s017_caddy/Caddyfile", "w") as f:
        f.write(CADDYFILE)
    subprocess.run("docker rm -f s017-caddy-probe 2>/dev/null", shell=True, check=False)
    subprocess.run(f"docker run -d --name s017-caddy-probe -p 0.0.0.0:{PORT}:{PORT} -v /tmp/s017_caddy/Caddyfile:/etc/caddy/Caddyfile caddy:2-alpine", shell=True, check=True)
    time.sleep(2)

def evaluate():
    chrome_bin = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    url = f"https://{LAN_IP}:{PORT}"

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
    print("DOM output snippet:\n", res.stdout[:500] if res.stdout else "EMPTY")

    probe_data = None
    if '<div id="result">' in res.stdout:
        part = res.stdout.split('<div id="result">')[1].split('</div>')[0]
        try:
            probe_data = json.loads(part)
        except Exception as e:
            probe_data = {"raw": part, "error": str(e)}

    return probe_data

def main():
    setup_caddy()
    try:
        val = evaluate()
        print("\n[+] Secure Context Result:")
        print(json.dumps(val, indent=2))
        with open("docs/spikes/s017_lan_access_and_edge_rebuild/code/result_secure_context.json", "w") as f:
            json.dump(val, f, indent=2)
    finally:
        subprocess.run("docker rm -f s017-caddy-probe 2>/dev/null", shell=True, check=False)

if __name__ == "__main__":
    main()
