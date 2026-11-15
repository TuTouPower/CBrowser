#!/usr/bin/env python3
"""Host orchestrator for s022 isolated Docker proxy/SDK/WebRTC/QUIC/DNS spike."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
CODE_DIR = Path(__file__).resolve().parent
SHARED_DIR = REPO_ROOT / ".scratch" / "s022_run"

BROWSER_IMAGE = os.environ.get(
    "CBROWSER_RUNTIME_TEST_IMAGE",
    "sha256:4d619a11851de463076dbc0843fc41d430c1751123b9c2e8590481ccabd182b2",
)
SUPERVISOR_IMAGE = os.environ.get(
    "CBROWSER_SUPERVISOR_TEST_IMAGE",
    "sha256:6bca260584f7b47d3a82dbe58a3299a83f0681ba8983cafc04f0d4b8b69a0057",
)
ENGINE_CACHE = Path(
    os.environ.get(
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        str(REPO_ROOT / "data" / "v2" / "engine-cache"),
    )
)

NET_NAME = "probe-s022-net"
SUBNET = "172.29.42.0/24"
TARGET_IP = "172.29.42.10"
PROXY_IP = "172.29.42.20"
BROWSER_IP = "172.29.42.30"

AUTH_USER = "probeuser"
AUTH_PASS = "p@ss:w=rd%1!/#?"
ENC_USER = urllib.parse.quote(AUTH_USER, safe="")
ENC_PASS = urllib.parse.quote(AUTH_PASS, safe="")


def _run(cmd: list[str], *, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


def _rm_container(name: str) -> None:
    _run(["docker", "rm", "-f", name], check=False, timeout=30)


def _rm_network(name: str) -> None:
    _run(["docker", "network", "rm", name], check=False, timeout=30)


def _wait_for_jsonl_event(path: Path, kind: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("kind") == kind:
                    return
        time.sleep(0.15)
    raise TimeoutError(f"Timed out waiting for {kind} in {path}")


def _read_jsonl_since(path: Path, start_line: int) -> tuple[int, list[dict[str, Any]]]:
    if not path.is_file():
        return start_line, []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[start_line:]:
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return len(lines), out


def run_one_scenario(
    spec: dict[str, Any],
    *,
    strict_policy: bool,
    allowed_tcp: list[str],
    allowed_udp: list[str],
    dns_ip: str | None = None,
    shared_profile_dir: str | None = None,
) -> dict[str, Any]:
    tag = spec["name"]
    browser_name = f"probe-s022-browser-{tag}"
    netns_name = f"probe-s022-netns-{tag}"
    _rm_container(netns_name)
    _rm_container(browser_name)

    spec_file = SHARED_DIR / f"spec_{tag}.json"
    out_file = SHARED_DIR / f"out_{tag}.json"
    pkt_file = SHARED_DIR / f"pkt_{tag}.jsonl"
    stop_file = SHARED_DIR / f"stop_{tag}.flag"
    cnt_file = SHARED_DIR / f"cnt_{tag}.json"
    for p in (out_file, pkt_file, stop_file, cnt_file):
        p.unlink(missing_ok=True)
    if shared_profile_dir:
        spec = {**spec, "user_data_dir": f"/s022_shared/{shared_profile_dir}"}
    spec_file.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    target_log = SHARED_DIR / "target.jsonl"
    proxy_log = SHARED_DIR / "proxy.jsonl"
    t_line = len(target_log.read_text(encoding="utf-8").splitlines()) if target_log.is_file() else 0
    p_line = len(proxy_log.read_text(encoding="utf-8").splitlines()) if proxy_log.is_file() else 0

    try:
        browser_cmd = [
            "docker", "run", "-d",
            "--name", browser_name,
            "--network", NET_NAME,
            "--ip", BROWSER_IP,
            "--shm-size", "512m",
            "--entrypoint", "python3",
            "-v", f"{CODE_DIR}:/s022_code:ro",
            "-v", f"{SHARED_DIR}:/s022_shared:rw",
            "-v", f"{ENGINE_CACHE}:/data/engine-cache:ro",
        ]
        if dns_ip:
            browser_cmd += ["--dns", dns_ip]
        browser_cmd += [BROWSER_IMAGE, "-c", "import time; time.sleep(300)"]
        _run(browser_cmd)

        # Attach netns helper sharing browser container's netns
        _run([
            "docker", "run", "-d",
            "--name", netns_name,
            "--network", f"container:{browser_name}",
            "--cap-add=NET_ADMIN",
            "--cap-add=NET_RAW",
            "--entrypoint", "python3",
            "-v", f"{CODE_DIR}:/s022_code:ro",
            "-v", f"{SHARED_DIR}:/s022_shared:rw",
            SUPERVISOR_IMAGE,
            "-c", "import time; time.sleep(300)",
        ])

        if strict_policy:
            pol_cmd = [
                "docker", "exec", netns_name,
                "python3", "/s022_code/netns_sniffer.py", "install-strict",
                "--tail", "DROP",
            ]
            for item in allowed_tcp:
                pol_cmd += ["--allowed-tcp", item]
            for item in allowed_udp:
                pol_cmd += ["--allowed-udp", item]
            _run(pol_cmd)

        # Start AF_PACKET sniffer in background inside netns
        _run([
            "docker", "exec", "-d", netns_name,
            "python3", "/s022_code/netns_sniffer.py", "capture",
            "--out", f"/s022_shared/pkt_{tag}.jsonl",
            "--stop-file", f"/s022_shared/stop_{tag}.flag",
        ])
        time.sleep(0.3)

        # Execute browser scenario
        proc = _run(
            [
                "docker", "exec", browser_name,
                "python3", "/s022_code/in_container_browser_probe.py",
                "--spec-file", f"/s022_shared/spec_{tag}.json",
                "--out-file", f"/s022_shared/out_{tag}.json",
            ],
            check=False,
            timeout=90,
        )

        stop_file.write_text("1", encoding="utf-8")
        time.sleep(0.4)
        _run([
            "docker", "exec", netns_name,
            "python3", "/s022_code/netns_sniffer.py", "counters",
            "--out", f"/s022_shared/cnt_{tag}.json",
        ], check=False)

        browser_res = (
            json.loads(out_file.read_text(encoding="utf-8"))
            if out_file.is_file()
            else {"launch_ok": False, "exec_rc": proc.returncode, "stderr": proc.stderr[-400:]}
        )
        packets = _read_jsonl_since(pkt_file, 0)[1]
        _, target_events = _read_jsonl_since(target_log, t_line)
        _, proxy_events = _read_jsonl_since(proxy_log, p_line)
        counters = json.loads(cnt_file.read_text(encoding="utf-8")) if cnt_file.is_file() else {}
        return {
            "name": tag,
            "strict_policy": strict_policy,
            "browser": browser_res,
            "target_events": target_events,
            "proxy_events": proxy_events,
            "packet_summary": _summarize_packets(packets),
            "counters": counters,
        }
    finally:
        _rm_container(netns_name)
        _rm_container(browser_name)


def _summarize_packets(packets: list[dict[str, Any]]) -> dict[str, Any]:
    by_dst: dict[str, int] = {}
    dns_queries: list[str] = []
    stun_dsts: list[str] = []
    for p in packets:
        dst = f"{p.get('l4', p.get('proto'))}:{p.get('dst_ip')}:{p.get('dst_port', '')}"
        by_dst[dst] = by_dst.get(dst, 0) + 1
        if p.get("dns_qname"):
            dns_queries.append(p["dns_qname"])
        if p.get("is_stun"):
            stun_dsts.append(f"{p.get('l4')}:{p.get('dst_ip')}:{p.get('dst_port')}")
    return {
        "total": len(packets),
        "by_dst": by_dst,
        "dns_queries": sorted(set(dns_queries)),
        "stun_dsts": sorted(set(stun_dsts)),
    }


def main() -> None:
    if SHARED_DIR.exists():
        shutil.rmtree(SHARED_DIR)
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    (SHARED_DIR / "certs").mkdir(parents=True, exist_ok=True)

    _rm_container("probe-s022-target")
    _rm_container("probe-s022-proxy")
    _rm_network(NET_NAME)

    try:
        _run([
            "docker", "network", "create",
            "--driver", "bridge",
            "--subnet", SUBNET,
            NET_NAME,
        ])

        _run([
            "docker", "run", "-d",
            "--name", "probe-s022-target",
            "--network", NET_NAME,
            "--ip", TARGET_IP,
            "--entrypoint", "python3",
            "-v", f"{CODE_DIR}:/s022_code:ro",
            "-v", f"{SHARED_DIR}:/s022_shared:rw",
            BROWSER_IMAGE,
            "/s022_code/in_container_services.py",
            "--bind-ip", TARGET_IP,
            "--role", "target",
            "--extra-ip", PROXY_IP,
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
            # 1. A/B: Current runner bug (proxy=None + --proxy-server, geoip=True) under strict DROP
            (
                {
                    "name": "ab_manual_cli_geoip_strict",
                    "proxy": None,
                    "extra_args": [f"--proxy-server=http://{PROXY_IP}:18080"],
                    "geoip": True,
                    "geoip_timeout_seconds": 3.0,
                    "ca_cert": ca,
                    "urls": [t_http],
                },
                True, [f"{PROXY_IP}:18080"], ["127.0.0.11:53"], None,
            ),
            # 2. A/B: SDK proxy= with geoip=True (unset tz/locale) under strict DROP
            (
                {
                    "name": "ab_sdk_http_geoip_unset_strict",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": True,
                    "geoip_timeout_seconds": 5.0,
                    "ca_cert": ca,
                    "urls": [t_http, t_https],
                },
                True, [f"{PROXY_IP}:18080"], ["127.0.0.11:53"], None,
            ),
            # 3. GeoIP + explicit locale only
            (
                {
                    "name": "geoip_explicit_locale_only",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": True,
                    "locale": "ja-JP",
                    "geoip_timeout_seconds": 5.0,
                    "ca_cert": ca,
                    "urls": [t_http],
                },
                True, [f"{PROXY_IP}:18080"], ["127.0.0.11:53"], None,
            ),
            # 4. GeoIP + explicit tz & locale both set
            (
                {
                    "name": "geoip_both_explicit",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": True,
                    "timezone": "Asia/Tokyo",
                    "locale": "ja-JP",
                    "geoip_timeout_seconds": 5.0,
                    "ca_cert": ca,
                    "urls": [t_http],
                },
                True, [f"{PROXY_IP}:18080"], ["127.0.0.11:53"], None,
            ),
            # 5. Auth matrix on arm64 146.0.7680.177.3: HTTP valid auth (Playwright proxy dict)
            (
                {
                    "name": "auth_http_valid",
                    "proxy": f"http://{ENC_USER}:{ENC_PASS}@{PROXY_IP}:18081",
                    "geoip": False,
                    "ca_cert": ca,
                    "urls": [t_http, t_https],
                },
                True, [f"{PROXY_IP}:18081"], ["127.0.0.11:53"], None,
            ),
            # 6. HTTP wrong auth
            (
                {
                    "name": "auth_http_wrong",
                    "proxy": f"http://{ENC_USER}:WRONG@{PROXY_IP}:18081",
                    "geoip": False,
                    "ca_cert": ca,
                    "urls": [t_http, t_https],
                },
                True, [f"{PROXY_IP}:18081"], ["127.0.0.11:53"], None,
            ),
            # 7. HTTPS (TLS-to-proxy) no auth
            (
                {
                    "name": "auth_https_noauth",
                    "proxy": f"https://{PROXY_IP}:18443",
                    "geoip": False,
                    "ca_cert": ca,
                    "urls": [t_http, t_https],
                },
                True, [f"{PROXY_IP}:18443"], ["127.0.0.11:53"], None,
            ),
            # 8. HTTPS (TLS-to-proxy) valid auth
            (
                {
                    "name": "auth_https_valid",
                    "proxy": f"https://{ENC_USER}:{ENC_PASS}@{PROXY_IP}:18444",
                    "geoip": False,
                    "ca_cert": ca,
                    "urls": [t_http, t_https],
                },
                True, [f"{PROXY_IP}:18444"], ["127.0.0.11:53"], None,
            ),
            # 9. SOCKS5 valid auth + geoip=True (checks httpx+socksio too!)
            (
                {
                    "name": "auth_socks5_valid_geoip",
                    "proxy": f"socks5://{ENC_USER}:{ENC_PASS}@{PROXY_IP}:11081",
                    "geoip": True,
                    "geoip_timeout_seconds": 5.0,
                    "ca_cert": ca,
                    "urls": [t_http, t_https],
                },
                True, [f"{PROXY_IP}:11081"], ["127.0.0.11:53"], None,
            ),
            # 10. SOCKS5 wrong auth
            (
                {
                    "name": "auth_socks5_wrong",
                    "proxy": f"socks5://{ENC_USER}:WRONG@{PROXY_IP}:11081",
                    "geoip": False,
                    "ca_cert": ca,
                    "urls": [t_http],
                },
                True, [f"{PROXY_IP}:11081"], ["127.0.0.11:53"], None,
            ),
            # 11. WebRTC leak observation (unrestricted policy, geoip=True + --fingerprint-webrtc-ip=8.8.8.8, NO webrtc policy flag)
            (
                {
                    "name": "webrtc_unrestricted_with_spoof_ip",
                    "proxy": f"socks5://{PROXY_IP}:11080",
                    "geoip": False,
                    "extra_args": ["--fingerprint-webrtc-ip=8.8.8.8"],
                    "ca_cert": ca,
                    "webrtc_url": t_webrtc,
                    "ice_servers": [{"urls": f"stun:{TARGET_IP}:3478"}],
                },
                False, [], [], None,
            ),
            # 12. WebRTC with disable_non_proxied_udp (unrestricted policy to observe whether Chrome emits UDP STUN!)
            (
                {
                    "name": "webrtc_disable_non_proxied_udp",
                    "proxy": f"socks5://{PROXY_IP}:11080",
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
            # 13. WebRTC under strict DROP policy + geoip=False + disable_non_proxied_udp
            (
                {
                    "name": "webrtc_strict_drop_geoip_off",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": False,
                    "extra_args": ["--force-webrtc-ip-handling-policy=disable_non_proxied_udp"],
                    "ca_cert": ca,
                    "webrtc_url": t_webrtc,
                    "ice_servers": [{"urls": f"stun:{TARGET_IP}:3478"}],
                },
                True, [f"{PROXY_IP}:18080"], ["127.0.0.11:53"], None,
            ),
            # 14. QUIC/UDP with socks5_noauth_udp (unrestricted first to see if Chrome sends UDP ASSOCIATE or direct UDP 8443!)
            (
                {
                    "name": "quic_socks5_udp_open",
                    "proxy": f"socks5://{PROXY_IP}:11080",
                    "geoip": False,
                    "ca_cert": ca,
                    "urls": [t_https, t_https],
                },
                False, [], [], None,
            ),
            # 15. QUIC/UDP with socks5_noauth_udp under strict DROP (only TCP proxy allowed, no UDP relay port)
            (
                {
                    "name": "quic_socks5_udp_strict_tcp_only",
                    "proxy": f"socks5://{PROXY_IP}:11080",
                    "geoip": False,
                    "ca_cert": ca,
                    "urls": [t_https, t_https],
                },
                True, [f"{PROXY_IP}:11080"], ["127.0.0.11:53"], None,
            ),
            # 16. QUIC/UDP with socks5 UDP ASSOCIATE rejected (0x07)
            (
                {
                    "name": "quic_socks5_udp_reject",
                    "proxy": f"socks5://{PROXY_IP}:11082",
                    "geoip": False,
                    "ca_cert": ca,
                    "urls": [t_https, t_https],
                },
                False, [], [], None,
            ),
            # 17. DNS path: socks5:// vs domain name (does Chrome resolve locally via 127.0.0.11:53 or send ATYP=domain?)
            (
                {
                    "name": "dns_socks5_domain",
                    "proxy": f"socks5://{PROXY_IP}:11080",
                    "geoip": False,
                    "ca_cert": ca,
                    "urls": [t_dns_http, t_dns_https],
                },
                True, [f"{PROXY_IP}:11080"], ["127.0.0.11:53"], None,
            ),
            # 18. DNS path: http:// proxy vs domain name
            (
                {
                    "name": "dns_http_domain",
                    "proxy": f"http://{PROXY_IP}:18080",
                    "geoip": False,
                    "ca_cert": ca,
                    "urls": [t_dns_http, t_dns_https],
                },
                True, [f"{PROXY_IP}:18080"], ["127.0.0.11:53"], None,
            ),
        ]

        results: list[dict[str, Any]] = []
        for spec, strict, atcp, audp, dns_ip in scenarios:
            res = run_one_scenario(
                spec,
                strict_policy=strict,
                allowed_tcp=atcp,
                allowed_udp=audp,
                dns_ip=dns_ip,
            )
            results.append(res)
            print(
                f"[{res['name']}] launch_ok={res['browser'].get('launch_ok')} "
                f"err={res['browser'].get('error')!r} "
                f"nav_ok={ {u: v.get('ok') for u, v in (res['browser'].get('nav_results') or {}).items()} } "
                f"target_hits={len(res['target_events'])} proxy_hits={len(res['proxy_events'])}"
            )

        # 19. Seed persistence across two launches with SDK proxy=
        seed_1 = run_one_scenario(
            {
                "name": "seed_restart_1",
                "proxy": f"socks5://{PROXY_IP}:11080",
                "geoip": False,
                "ca_cert": ca,
                "urls": [t_http],
            },
            strict_policy=True,
            allowed_tcp=[f"{PROXY_IP}:11080"],
            allowed_udp=["127.0.0.11:53"],
            shared_profile_dir="persist_prof",
        )
        seed_2 = run_one_scenario(
            {
                "name": "seed_restart_2",
                "proxy": f"socks5://{PROXY_IP}:11080",
                "geoip": False,
                "ca_cert": ca,
                "urls": [t_http],
            },
            strict_policy=True,
            allowed_tcp=[f"{PROXY_IP}:11080"],
            allowed_udp=["127.0.0.11:53"],
            shared_profile_dir="persist_prof",
        )
        results.extend([seed_1, seed_2])

        summary_path = SHARED_DIR / "summary.json"
        summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"SAVED_SUMMARY={summary_path}")
    finally:
        _rm_container("probe-s022-proxy")
        _rm_container("probe-s022-target")
        _rm_network(NET_NAME)


if __name__ == "__main__":
    main()
