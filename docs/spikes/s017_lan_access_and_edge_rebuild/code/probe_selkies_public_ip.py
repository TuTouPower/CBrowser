#!/usr/bin/env python3
"""Probe 4: Test Selkies 2.2.1 parameter parsing and public-ip flag behavior."""

import subprocess
import json

def test_selkies_help():
    # Run python3 -m cbrowser.stream_agent.agent --help inside stream runtime image
    cmd = "docker run --rm cbrowser-stream_runtime044:latest python3 -m cbrowser.stream_agent.agent --help"
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    has_public_ip = "--webrtc-public-ip" in res.stdout
    has_ice_lite = "--webrtc-ice-lite" in res.stdout
    print(f"Selkies 2.2.1 flag support: --webrtc-public-ip={has_public_ip}, --webrtc-ice-lite={has_ice_lite}")

    result = {
        "has_public_ip": has_public_ip,
        "has_ice_lite": has_ice_lite,
        "stdout_snippet": [line for line in res.stdout.splitlines() if "public-ip" in line or "ice-lite" in line]
    }
    with open("docs/spikes/s017_lan_access_and_edge_rebuild/code/result_selkies_public_ip.json", "w") as f:
        json.dump(result, f, indent=2)

if __name__ == "__main__":
    test_selkies_help()
