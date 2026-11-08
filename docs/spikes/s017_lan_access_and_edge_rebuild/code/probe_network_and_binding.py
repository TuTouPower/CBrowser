#!/usr/bin/env python3
"""Probe 1 & 2: Port binding isolation (127.0.0.1 vs 0.0.0.0) under OrbStack,
client remote IP visibility, and non-loopback client simulation.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

LAN_IP = "192.168.31.76"
PORT_LOOPBACK = 54321
PORT_ALL = 54322

SERVER_SCRIPT = """
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        payload = {
            'client_address': self.client_address[0],
            'client_port': self.client_address[1],
            'headers': dict(self.headers),
        }
        self.wfile.write(json.dumps(payload).encode('utf-8'))
    def log_message(self, format, *args):
        pass

httpd = HTTPServer(('0.0.0.0', 8080), Handler)
httpd.serve_forever()
"""

def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def cleanup():
    run_cmd("docker rm -f s017-probe-loopback s017-probe-all s017-probe-client 2>/dev/null")

def test_url(url, timeout=2):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return {"status": resp.status, "data": data}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": type(e).__name__}

def main():
    cleanup()
    results = {}

    print(f"[1] Starting test containers: loopback on {PORT_LOOPBACK}, all on {PORT_ALL}...")
    # Start container with 127.0.0.1 binding
    cmd1 = f"docker run -d --name s017-probe-loopback -p 127.0.0.1:{PORT_LOOPBACK}:8080 python:3.12-alpine python3 -c \"{SERVER_SCRIPT}\""
    res1 = run_cmd(cmd1)
    if res1.returncode != 0:
        print("Failed to start loopback container:", res1.stderr)
        sys.exit(1)

    # Start container with 0.0.0.0 binding
    cmd2 = f"docker run -d --name s017-probe-all -p 0.0.0.0:{PORT_ALL}:8080 python:3.12-alpine python3 -c \"{SERVER_SCRIPT}\""
    res2 = run_cmd(cmd2)
    if res2.returncode != 0:
        print("Failed to start all-interface container:", res2.stderr)
        sys.exit(1)

    time.sleep(2)

    print("[2] Testing host access to 127.0.0.1 binding...")
    res_loopback_local = test_url(f"http://127.0.0.1:{PORT_LOOPBACK}")
    res_loopback_lan = test_url(f"http://{LAN_IP}:{PORT_LOOPBACK}")
    print(f"  -> 127.0.0.1:{PORT_LOOPBACK}: {res_loopback_local.get('status')}")
    print(f"  -> {LAN_IP}:{PORT_LOOPBACK}: {res_loopback_lan.get('status')} ({res_loopback_lan.get('error')})")

    print("[3] Testing host access to 0.0.0.0 binding...")
    res_all_local = test_url(f"http://127.0.0.1:{PORT_ALL}")
    res_all_lan = test_url(f"http://{LAN_IP}:{PORT_ALL}")
    print(f"  -> 127.0.0.1:{PORT_ALL}: {res_all_local.get('status')} client={res_all_local.get('data', {}).get('client_address')}")
    print(f"  -> {LAN_IP}:{PORT_ALL}: {res_all_lan.get('status')} client={res_all_lan.get('data', {}).get('client_address')}")

    print("[4] Testing non-loopback client simulation from inside a docker container...")
    # Client container on default bridge network accessing host via LAN_IP and host.docker.internal
    probe_client_cmd = f"docker run --rm curlimages/curl:latest -s http://{LAN_IP}:{PORT_ALL}"
    res_client_lan = run_cmd(probe_client_cmd)
    client_lan_data = json.loads(res_client_lan.stdout) if res_client_lan.returncode == 0 else {"error": res_client_lan.stderr}

    probe_client_loopback_cmd = f"docker run --rm curlimages/curl:latest -s --connect-timeout 2 http://{LAN_IP}:{PORT_LOOPBACK}"
    res_client_loopback = run_cmd(probe_client_loopback_cmd)

    print(f"  -> Container client to {LAN_IP}:{PORT_ALL}: code={res_client_lan.returncode} client_seen={client_lan_data.get('client_address')}")
    print(f"  -> Container client to {LAN_IP}:{PORT_LOOPBACK}: code={res_client_loopback.returncode} (expected failure)")

    summary = {
        "loopback_binding": {
            "local_access": res_loopback_local,
            "lan_ip_access": res_loopback_lan,
        },
        "all_interfaces_binding": {
            "local_access": res_all_local,
            "lan_ip_access": res_all_lan,
        },
        "docker_container_client": {
            "access_lan_port_all": client_lan_data,
            "access_lan_port_loopback_returncode": res_client_loopback.returncode,
        }
    }

    out_path = "docs/spikes/s017_lan_access_and_edge_rebuild/code/result_network_binding.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"[+] Saved results to {out_path}")

    cleanup()

if __name__ == "__main__":
    main()
