#!/usr/bin/env python3
"""Round 2 targeted spike checks for s022: GeoIP echo TLS, WebRTC policies, QUIC force, DNS:53, IPv6."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from run_spike_s022 import (
    AUTH_PASS,
    AUTH_USER,
    BROWSER_IMAGE,
    CODE_DIR,
    ENC_PASS,
    ENC_USER,
    NET_NAME,
    PROXY_IP,
    SHARED_DIR,
    SUBNET,
    TARGET_IP,
    _rm_container,
    _rm_network,
    _run,
    _wait_for_jsonl_event,
    run_one_scenario,
)


def main() -> None:
    if SHARED_DIR.exists():
        shutil.rmtree(SHARED_DIR)
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    (SHARED_DIR / "certs").mkdir(parents=True, exist_ok=True)

    _rm_container("probe-s022-target")
    _rm_container("probe-s022-proxy")
    _rm_network(NET_NAME)

    try:
        _run(["docker", "network", "create", "--driver", "bridge", "--subnet", SUBNET, NET_NAME])
        _run([
            "docker", "run", "-d",
            "--name", "probe-s022-target",
            "--network", NET_NAME,
            "--ip", TARGET_IP,
            "--user", "0:0",
            "--entrypoint", "python3",
            "-v", f"{CODE_DIR}:/s022_code:ro",
            "-v", f"{SHARED_DIR}:/s022_shared:rw",
            BROWSER_IMAGE,
            "/s022_code/in_container_services.py",
            "--bind-ip", TARGET_IP,
            "--role", "target",
            "--extra-ip", PROXY_IP,
            "--dns-port", "53",
            "--log-file", "/s022_shared/target.jsonl",
            "--cert-dir", "/s022_shared/certs",
            "--echo-ip", "8.8.8.8",
        ])
        _wait_for_jsonl_event(SHARED_DIR / "target.jsonl", "all_services_ready")

        _run([
            "docker", "run", "-d",
            "--name", "probe-s022-proxy",
            "--network", NET_NAME,
            "--ip", PROXY_IP,
            "--entrypoint", "python3",
            "-v", f"{CODE_DIR}:/s022_code:ro",
            "-v", f"{SHARED_DIR}:/s022_shared:rw",
            BROWSER_IMAGE,
            "/s022_code/in_container_services.py",
            "--bind-ip", PROXY_IP,
            "--role", "proxy",
            "--target-ip", TARGET_IP,
            "--reuse-certs",
            "--log-file", "/s022_shared/proxy.jsonl",
            "--cert-dir", "/s022_shared/certs",
            "--auth-user", AUTH_USER,
            "--auth-pass", AUTH_PASS,
            "--echo-ip", "8.8.8.8",
        ])
        _wait_for_jsonl_event(SHARED_DIR / "proxy.jsonl", "all_services_ready")

        ca = "/s022_shared/certs/ca.crt"
        t_http = f"http://{TARGET_IP}:8080/"
        t_https = f"https://{TARGET_IP}:8443/"
        t_webrtc = f"http://{TARGET_IP}:8080/webrtc"
        t_dns_http = "http://dns-test.s022.invalid:8080/"
        t_dns_https = "https://dns-test.s022.invalid:8443/"

        scenarios: list[tuple[dict[str, Any], bool, list[str], list[str], str | None]] = [
            # R1: SDK http + geoip=True (unset) with fixed KeyUsage CA
            (
                {
                    "name": "r2_sdk_http_geoip_unset",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": True,
                    "geoip_timeout_seconds": 5.0,
                    "ca_cert": ca,
                    "urls": [t_http],
                },
                True, [f"{PROXY_IP}:18080"], ["127.0.0.11:53"], None,
            ),
            # R2: SDK http + geoip=True + explicit locale ja-JP (should keep ja-JP, infer tz from 8.8.8.8)
            (
                {
                    "name": "r2_sdk_http_geoip_locale_only",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": True,
                    "locale": "ja-JP",
                    "geoip_timeout_seconds": 5.0,
                    "ca_cert": ca,
                    "urls": [t_http],
                },
                True, [f"{PROXY_IP}:18080"], ["127.0.0.11:53"], None,
            ),
            # R3: SDK socks5 valid auth + geoip=True (tests socksio + GeoIP + special-char auth + target nav)
            (
                {
                    "name": "r2_socks5_auth_geoip",
                    "proxy": f"socks5://{ENC_USER}:{ENC_PASS}@{PROXY_IP}:11081",
                    "geoip": True,
                    "geoip_timeout_seconds": 5.0,
                    "ca_cert": ca,
                    "urls": [t_http, t_https],
                },
                True, [f"{PROXY_IP}:11081"], ["127.0.0.11:53"], None,
            ),
            # R4: WebRTC with http:// proxy + --force-webrtc-ip-handling-policy=disable_non_proxied_udp (OPEN netns!)
            (
                {
                    "name": "r2_webrtc_http_disable_non_proxied_udp",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": False,
                    "extra_args": [
                        "--fingerprint-webrtc-ip=8.8.8.8",
                        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                    ],
                    "ca_cert": ca,
                    "webrtc_url": t_webrtc,
                    "ice_servers": [{"urls": f"stun:{TARGET_IP}:3478"}],
                },
                False, [], [], None,
            ),
            # R5: WebRTC with socks5:// proxy + Preferences webrtc.ip_handling_policy=disable_non_proxied_udp (OPEN netns!)
            (
                {
                    "name": "r2_webrtc_socks5_pref_disable_non_proxied_udp",
                    "proxy": f"socks5://{PROXY_IP}:11080",
                    "geoip": False,
                    "extra_args": ["--fingerprint-webrtc-ip=8.8.8.8"],
                    "preferences": {"webrtc": {"ip_handling_policy": "disable_non_proxied_udp"}},
                    "ca_cert": ca,
                    "webrtc_url": t_webrtc,
                    "ice_servers": [{"urls": f"stun:{TARGET_IP}:3478"}],
                },
                False, [], [], None,
            ),
            # R6: WebRTC STUN hostname resolution via Docker DNS (--dns TARGET_IP)
            (
                {
                    "name": "r2_webrtc_stun_hostname_dns",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": False,
                    "extra_args": ["--fingerprint-webrtc-ip=8.8.8.8"],
                    "ca_cert": ca,
                    "webrtc_url": t_webrtc,
                    "ice_servers": [{"urls": "stun:stun-host.s022.invalid:3478"}],
                },
                False, [], [], TARGET_IP,
            ),
            # R7: QUIC forced via --origin-to-force-quic-on with socks5 (OPEN netns)
            (
                {
                    "name": "r2_quic_force_socks5_open",
                    "proxy": f"socks5://{PROXY_IP}:11080",
                    "geoip": False,
                    "extra_args": [
                        "--enable-quic",
                        f"--origin-to-force-quic-on={TARGET_IP}:8443",
                    ],
                    "ca_cert": ca,
                    "urls": [t_https],
                },
                False, [], [], None,
            ),
            # R8: QUIC forced via --origin-to-force-quic-on with http proxy (OPEN netns)
            (
                {
                    "name": "r2_quic_force_http_open",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": False,
                    "extra_args": [
                        "--enable-quic",
                        f"--origin-to-force-quic-on={TARGET_IP}:8443",
                    ],
                    "ca_cert": ca,
                    "urls": [t_https],
                },
                False, [], [], None,
            ),
            # R9: DNS with --dns TARGET_IP for domain URL via http:// proxy (checks if local DNS is queried at all)
            (
                {
                    "name": "r2_dns_http_with_dns_server",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": False,
                    "ca_cert": ca,
                    "urls": [t_dns_http, t_dns_https],
                },
                False, [], [], TARGET_IP,
            ),
        ]

        results = []
        for spec, strict, atcp, audp, dns_ip in scenarios:
            res = run_one_scenario(
                spec,
                strict_policy=strict,
                allowed_tcp=atcp,
                allowed_udp=audp,
                dns_ip=dns_ip,
            )
            results.append(res)
            b = res["browser"]
            print(f"=== {res['name']} ===")
            print("  launch_ok:", b.get("launch_ok"), "err:", b.get("error"))
            print("  fp_flags:", b.get("chrome_fingerprint_flags"))
            print("  js_env:", b.get("js_env"))
            print("  webrtc:", b.get("webrtc"))
            print("  pkt:", res["packet_summary"])
            print("  target_events:", [(e.get("kind"), e.get("client_ip") or e.get("src_ip"), e.get("transport"), e.get("qname")) for e in res["target_events"]])
            print("  proxy_events:", [(e.get("kind"), e.get("cmd") or e.get("method"), e.get("atyp"), e.get("dst_host") or e.get("target")) for e in res["proxy_events"]])

        (SHARED_DIR / "summary_round2.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    finally:
        _rm_container("probe-s022-proxy")
        _rm_container("probe-s022-target")
        _rm_network(NET_NAME)


if __name__ == "__main__":
    main()
