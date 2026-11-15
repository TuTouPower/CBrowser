#!/usr/bin/env python3
"""Round 3 spike verification for s022: strict WebRTC/QUIC, offline GeoIP, probe isolation, IPv6."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from run_spike_s022 import (
    AUTH_PASS,
    AUTH_USER,
    BROWSER_IMAGE,
    CODE_DIR,
    ENGINE_CACHE,
    NET_NAME,
    PROXY_IP,
    SHARED_DIR,
    SUBNET,
    SUPERVISOR_IMAGE,
    TARGET_IP,
    _rm_container,
    _rm_network,
    _run,
    _wait_for_jsonl_event,
    run_one_scenario,
)

PROBE_IMAGE = "cbrowser-final-probe:latest"
POLICY_IMAGE = SUPERVISOR_IMAGE
IPV6_NET = "cbrowser-s022-v6"


def run_probe_isolation_check(ca_path: str) -> dict[str, Any]:
    """Compare probe container direct-bypass behavior under browser role vs strict DROP."""
    out: dict[str, Any] = {}
    for mode in ("current_browser_role", "strict_proxy_only"):
        cname = f"probe-s022-probe-{mode}"
        _rm_container(cname)
        helper_cmd = (
            "python3 -c \""
            "import json, urllib.request, urllib.error;"
            "r = {};"
            "try: r['proxy'] = urllib.request.urlopen("
            "urllib.request.ProxyHandler({'http': f'http://172.29.42.20:18080'})"
            ").status if False else None\n"
            "except Exception as e: r['proxy'] = str(e)\n"
            "\""
        )
        # Keep container alive to install policy BEFORE running egress requests
        _run([
            "docker", "run", "-d",
            "--name", cname,
            "--network", NET_NAME,
            "--ip", "172.29.42.31",
            "--entrypoint", "sleep",
            PROBE_IMAGE,
            "60",
        ])
        try:
            spec = {
                "role": "browser" if mode == "current_browser_role" else "probe_strict_sim",
                "allowed_tcp": [["172.29.42.20", 18080]],
                "allowed_udp": [],
            }
            if mode == "current_browser_role":
                # Current production network_policy.py emits OUTPUT -j ACCEPT for role=browser
                _run([
                    "docker", "run", "--rm",
                    "--net", f"container:{cname}",
                    "--cap-drop=ALL", "--cap-add=NET_ADMIN",
                    "--user", "0:0",
                    "--entrypoint", "python3",
                    POLICY_IMAGE,
                    "-m", "cbrowser.supervisor.network_policy",
                    json.dumps(spec),
                ])
            else:
                # Strict DROP with ONLY 172.29.42.20:18080 allowed
                script = (
                    "import subprocess;"
                    "rules='''*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT DROP [0:0]\n"
                    "-A OUTPUT -o lo -j ACCEPT\n"
                    "-A OUTPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT\n"
                    "-A OUTPUT -p tcp -d 172.29.42.20 --dport 18080 -j ACCEPT\n"
                    "-A OUTPUT -j DROP\nCOMMIT\n''';"
                    "subprocess.run(['iptables-restore'], input=rules, text=True, check=True)"
                )
                _run([
                    "docker", "run", "--rm",
                    "--net", f"container:{cname}",
                    "--cap-drop=ALL", "--cap-add=NET_ADMIN",
                    "--user", "0:0",
                    "--entrypoint", "python3",
                    POLICY_IMAGE,
                    "-c", script,
                ])

            probe_py = (
                "import json, urllib.request;"
                "res = {};"
                "op_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({'http': 'http://172.29.42.20:18080'}));"
                "op_direct = urllib.request.build_opener(urllib.request.ProxyHandler({}));"
                "\ntry:\n  res['proxied'] = op_proxy.open('http://172.29.42.10:8080/', timeout=2).read().decode()\nexcept Exception as e:\n  res['proxied_err'] = repr(e)\n"
                "\ntry:\n  res['direct_bypass'] = op_direct.open('http://172.29.42.10:8080/', timeout=2).read().decode()\nexcept Exception as e:\n  res['direct_bypass_err'] = repr(e)\n"
                "\nprint(json.dumps(res))"
            )
            exec_res = _run(["docker", "exec", cname, "python3", "-c", probe_py], check=False)
            out[mode] = json.loads(exec_res.stdout.strip()) if exec_res.returncode == 0 else {
                "rc": exec_res.returncode, "stderr": exec_res.stderr
            }
        finally:
            _rm_container(cname)
    return out


def run_ipv6_checks() -> dict[str, Any]:
    """Verify IPv6 proxy navigation and netfilter behavior in IPv6-enabled bridge."""
    _rm_container("probe-s022-v6svc")
    _rm_container("probe-s022-v6browser")
    _rm_network(IPV6_NET)
    results: dict[str, Any] = {}
    try:
        net_create = _run([
            "docker", "network", "create",
            "--driver", "bridge",
            "--ipv6",
            "--subnet", "172.29.43.0/24",
            "--subnet", "fd00:22::/64",
            IPV6_NET,
        ], check=False)
        if net_create.returncode != 0:
            return {"ipv6_network_unsupported": net_create.stderr.strip()}

        # Verify current NetworkPolicySpec IPv6 handling directly
        np_check = _run([
            "docker", "run", "--rm", "--entrypoint", "python3", POLICY_IMAGE,
            "-c",
            "from cbrowser.supervisor.network_policy import NetworkPolicySpec, render_iptables_rules, render_ip6tables_rules; "
            "s = NetworkPolicySpec(role='browser', allowed_tcp=[('fd00:22::20', 18080)]); "
            "print('V4:', render_iptables_rules(s).splitlines()); "
            "print('V6:', render_ip6tables_rules(s).splitlines())",
        ], check=False)
        results["current_network_policy_with_ipv6_tuple"] = {
            "rc": np_check.returncode,
            "stdout": np_check.stdout,
            "stderr": np_check.stderr,
        }

        svc_code = r"""
import http.server, json, socket, threading, time
from urllib.parse import urlparse

class V6Server(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6

class TargetH(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"ok": True, "client_ip": self.client_address[0]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass

class ProxyH(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path)
        host = p.hostname
        port = p.port or 80
        up = socket.create_connection((host, port), timeout=5)
        path = p.path or "/"
        up.sendall(f"GET {path} HTTP/1.1\r\nHost: {p.netloc}\r\nConnection: close\r\n\r\n".encode())
        resp = b""
        while True:
            c = up.recv(4096)
            if not c: break
            resp += c
        up.close()
        self.connection.sendall(resp)
    def log_message(self, *a): pass

t = V6Server(("::", 8080), TargetH)
px = V6Server(("::", 18080), ProxyH)
threading.Thread(target=t.serve_forever, daemon=True).start()
threading.Thread(target=px.serve_forever, daemon=True).start()
print("V6_READY", flush=True)
while True: time.sleep(1)
"""
        _run([
            "docker", "run", "-d",
            "--name", "probe-s022-v6svc",
            "--network", IPV6_NET,
            "--ip", "172.29.43.10",
            "--ip6", "fd00:22::10",
            "--entrypoint", "python3",
            BROWSER_IMAGE,
            "-c", svc_code,
        ])
        time.sleep(1.5)

        b_code = r"""
import asyncio, json
from cloakbrowser import launch_persistent_context_async

async def main():
    out = {}
    for label, p_url, nav in [
        ("v6_proxy_to_v6_target", "http://[fd00:22::10]:18080", "http://[fd00:22::10]:8080/"),
        ("v6_proxy_to_v4_target", "http://[fd00:22::10]:18080", "http://172.29.43.10:8080/"),
    ]:
        ud = f"/tmp/v6prof_{label}"
        try:
            ctx = await launch_persistent_context_async(
                user_data_dir=ud, headless=True, geoip=False, proxy=p_url,
                args=["--no-sandbox", "--disable-gpu"],
            )
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            resp = await page.goto(nav, wait_until="domcontentloaded", timeout=10000)
            body = await page.inner_text("body")
            await ctx.close()
            out[label] = {"ok": True, "status": resp.status if resp else None, "body": body}
        except Exception as e:
            out[label] = {"ok": False, "err": f"{type(e).__name__}: {e}"}
    print("V6_RES:" + json.dumps(out))

asyncio.run(main())
"""
        _run([
            "docker", "run", "-d",
            "--name", "probe-s022-v6browser",
            "--network", IPV6_NET,
            "--ip", "172.29.43.30",
            "--ip6", "fd00:22::30",
            "--user", "1000:1000",
            "-v", f"{ENGINE_CACHE}:/data/engine-cache:ro",
            "--entrypoint", "sleep",
            BROWSER_IMAGE,
            "120",
        ])
        # Apply strict ip6tables OUTPUT -j DROP allowing ONLY fd00:22::10:18080 and DROP v4 OUTPUT
        strict_v6 = (
            "import subprocess;"
            "v4='''*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT DROP [0:0]\n"
            "-A OUTPUT -o lo -j ACCEPT\n-A OUTPUT -j DROP\nCOMMIT\n''';"
            "v6='''*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT DROP [0:0]\n"
            "-A OUTPUT -o lo -j ACCEPT\n"
            "-A OUTPUT -p ipv6-icmp -j ACCEPT\n"
            "-A OUTPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT\n"
            "-A OUTPUT -p tcp -d fd00:22::10 --dport 18080 -j ACCEPT\n"
            "-A OUTPUT -j DROP\nCOMMIT\n''';"
            "subprocess.run(['iptables-restore'], input=v4, text=True, check=True);"
            "subprocess.run(['ip6tables-restore'], input=v6, text=True, check=True)"
        )
        _run([
            "docker", "run", "--rm",
            "--net", "container:probe-s022-v6browser",
            "--cap-drop=ALL", "--cap-add=NET_ADMIN",
            "--user", "0:0", "--entrypoint", "python3",
            POLICY_IMAGE, "-c", strict_v6,
        ])
        b_exec = _run([
            "docker", "exec",
            "-e", "CLOAKBROWSER_AUTO_UPDATE=false",
            "-e", "CLOAKBROWSER_CACHE_DIR=/data/engine-cache",
            "-e", "CLOAKBROWSER_VERSION=146.0.7680.177.3",
            "-e", "HOME=/tmp",
            "probe-s022-v6browser",
            "python3", "-c", b_code,
        ], check=False)
        results["v6_browser_strict"] = {
            "rc": b_exec.returncode,
            "stdout": b_exec.stdout,
            "stderr": b_exec.stderr[-500:] if b_exec.stderr else "",
        }
        return results
    finally:
        _rm_container("probe-s022-v6browser")
        _rm_container("probe-s022-v6svc")
        _rm_network(IPV6_NET)


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
            # No --echo-ip here! Requests for api.ipify.org go to target on port 443 unless dead
        ])
        _wait_for_jsonl_event(SHARED_DIR / "proxy.jsonl", "all_services_ready")

        ca = "/s022_shared/certs/ca.crt"
        t_http = f"http://{TARGET_IP}:8080/"
        t_https = f"https://{TARGET_IP}:8443/"
        t_webrtc = f"http://{TARGET_IP}:8080/webrtc"

        scenarios = [
            # R3-1: WebRTC STUN hostname + strict OUTPUT -j DROP WITHOUT 127.0.0.11:53
            (
                {
                    "name": "r3_webrtc_stun_strict_no_dns",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": False,
                    "extra_args": [
                        "--fingerprint-webrtc-ip=8.8.8.8",
                        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                    ],
                    "ca_cert": ca,
                    "webrtc_url": t_webrtc,
                    "ice_servers": [{"urls": "stun:stun-host.s022.invalid:3478"}],
                },
                True, [f"{PROXY_IP}:18080"], [], TARGET_IP,
            ),
            # R3-2: QUIC forced on socks5 with strict TCP-only OUTPUT -j DROP (UDP dropped at OUTPUT)
            (
                {
                    "name": "r3_quic_force_socks5_strict_udp_drop",
                    "proxy": f"socks5://{PROXY_IP}:11080",
                    "geoip": False,
                    "extra_args": [
                        "--enable-quic",
                        f"--origin-to-force-quic-on={TARGET_IP}:8443",
                    ],
                    "ca_cert": ca,
                    "urls": [t_https],
                },
                True, [f"{PROXY_IP}:11080"], [], None,
            ),
            # R3-3: QUIC disabled (--disable-quic) on socks5 + Alt-Svc h3 header + strict OUTPUT -j DROP
            (
                {
                    "name": "r3_quic_disabled_socks5_strict",
                    "proxy": f"socks5://{PROXY_IP}:11080",
                    "geoip": False,
                    "extra_args": ["--disable-quic"],
                    "ca_cert": ca,
                    "urls": [t_https],
                },
                True, [f"{PROXY_IP}:11080"], [], None,
            ),
            # R3-4: Offline GeoIP failure with RFC1918 proxy IP (without --echo-ip intercept on target?
            # Target HAS no internet IP, wait: here we override proxy on unused port or let proxy fail on port 18082)
            # We test RFC1918 fallback when api.ipify.org is blocked / times out!
            # We pass proxy=http://172.29.42.20:18080 WITHOUT ca_cert so httpx TLS verify to target fails -> _resolve_exit_ip returns None -> fallback _resolve_proxy_ip(172.29.42.20) -> GeoLite2 lookup on RFC1918!
            (
                {
                    "name": "r3_offline_geoip_rfc1918_crash_check",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": True,
                    "geoip_timeout_seconds": 2.0,
                    "urls": [t_http],
                },
                True, [f"{PROXY_IP}:18080"], [], None,
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
            print("  nav:", b.get("nav_results"))
            print("  webrtc:", b.get("webrtc"))
            print("  pkt:", res["packet_summary"])
            print("  target_events:", [(e.get("kind"), e.get("qname") or e.get("path")) for e in res["target_events"]])
            print("  proxy_events:", [(e.get("kind"), e.get("cmd") or e.get("method"), e.get("dst_host") or e.get("target")) for e in res["proxy_events"]])

        probe_res = run_probe_isolation_check(ca)
        print("=== probe_isolation ===")
        print(json.dumps(probe_res, indent=2))

        v6_res = run_ipv6_checks()
        print("=== ipv6_checks ===")
        print(json.dumps(v6_res, indent=2))

        (SHARED_DIR / "summary_round3.json").write_text(
            json.dumps({"scenarios": results, "probe": probe_res, "ipv6": v6_res}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    finally:
        _rm_container("probe-s022-proxy")
        _rm_container("probe-s022-target")
        _rm_network(NET_NAME)


if __name__ == "__main__":
    main()
