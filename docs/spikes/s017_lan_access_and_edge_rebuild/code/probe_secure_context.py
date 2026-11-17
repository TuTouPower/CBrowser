#!/usr/bin/env python3
"""Probe 3: Chrome Secure Context (isSecureContext, Web Locks, WebRTC)
under LAN HTTPS with self-signed / untrusted certificate.
"""

import json
import os
import ssl
import subprocess
import sys
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import threading

LAN_IP = "192.168.31.76"
PORT = 54323
CERT_DIR = "/tmp/s017_cert"

HTML_CONTENT = """<!DOCTYPE html>
<html>
<head><title>Secure Context Probe</title></head>
<body>
<div id="result">Testing...</div>
<script>
const result = {
    isSecureContext: window.isSecureContext,
    hasLocks: typeof navigator.locks !== 'undefined',
    hasRTCPeerConnection: typeof RTCPeerConnection !== 'undefined',
    hasCryptoSubtle: typeof crypto !== 'undefined' && typeof crypto.subtle !== 'undefined',
    protocol: window.location.protocol,
    origin: window.location.origin
};
document.getElementById('result').innerText = JSON.stringify(result);
console.log("PROBE_RESULT:" + JSON.stringify(result));
</script>
</body>
</html>
"""

class QuietHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(HTML_CONTENT.encode("utf-8"))))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(HTML_CONTENT.encode("utf-8"))
    def log_message(self, format, *args):
        pass

def generate_cert():
    os.makedirs(CERT_DIR, exist_ok=True)
    key_path = os.path.join(CERT_DIR, "server.key")
    crt_path = os.path.join(CERT_DIR, "server.crt")
    if not os.path.exists(key_path) or not os.path.exists(crt_path):
        cmd = f"openssl req -x509 -newkey rsa:2048 -keyout {key_path} -out {crt_path} -days 1 -nodes -subj '/CN={LAN_IP}'"
        subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return key_path, crt_path

def start_https_server():
    key_path, crt_path = generate_cert()
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), QuietHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=crt_path, keyfile=key_path)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    return httpd

def test_chrome_secure_context():
    # Look for google chrome executable
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    chrome_bin = None
    for p in chrome_paths:
        if os.path.exists(p):
            chrome_bin = p
            break

    if not chrome_bin:
        print("Chrome binary not found on host, trying container...")
        return None

    url = f"https://{LAN_IP}:{PORT}"
    print(f"[+] Probing Chrome headless with --ignore-certificate-errors against {url}...")
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

    return probe_data

def main():
    httpd = start_https_server()
    time.sleep(1)
    try:
        data = test_chrome_secure_context()
        print("Probe Result:", json.dumps(data, indent=2))
        out_path = "docs/spikes/s017_lan_access_and_edge_rebuild/code/result_secure_context.json"
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[+] Saved results to {out_path}")
    finally:
        httpd.shutdown()

if __name__ == "__main__":
    main()
