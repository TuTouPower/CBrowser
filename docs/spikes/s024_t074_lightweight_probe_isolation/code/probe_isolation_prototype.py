"""s024: 真实 Docker 容器内验证池化轻量探针的隔离边界与毫秒计时。

在 cbrowser-api 镜像容器里运行：httpx.Client(trust_env=False)，每次请求新建
client（不跨代理复用连接池），计时只包实际 HTTP 请求，不含容器/网络生命周期。
凭据只从环境变量读取，绝不进 argv。输出 code/results.json。
"""

from __future__ import annotations

import ipaddress
import json
import os
import sys
import time

import httpx

ALLOWED = {
    "api.ipify.org": "https://api.ipify.org",
    "icanhazip.com": "http://icanhazip.com",
}
PROXY_PORTS = [21000, 21003]


def blocked(host: str) -> str | None:
    """白名单 + 私有/回环/保留地址拦截（fail-closed）。"""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (
        ip.is_private or ip.is_loopback or ip.is_reserved
        or ip.is_link_local or ip.is_unspecified or ip.is_multicast
    ):
        return "private_or_reserved"
    if host not in ALLOWED:
        return "not_in_allowlist"
    return None


def guarded_get(port: int, host: str) -> dict:
    reason = blocked(host)
    if reason:
        return {"port": port, "host": host, "rejected": reason, "http": None}
    t0 = time.monotonic()
    try:
        with httpx.Client(
            proxy=f"http://host.docker.internal:{port}",
            trust_env=False,
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            r = client.get(ALLOWED[host])
        elapsed = round((time.monotonic() - t0) * 1000, 1)
        return {
            "port": port, "host": host, "http": r.status_code,
            "rtt_ms": elapsed, "body": r.text.strip()[:40],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "port": port, "host": host, "http": None,
            "rtt_ms": round((time.monotonic() - t0) * 1000, 1),
            "error": f"{type(exc).__name__}: {exc}"[:140],
        }


def main() -> None:
    t_start = time.monotonic()
    results = {
        "argv": sys.argv[1:],
        "creds_in_argv": any(
            "password" in a.lower() or "secret" in a.lower() or "token" in a.lower()
            for a in sys.argv
        ),
        "creds_from_env_only": bool(os.environ.get("CBROWSER_PROBE_CREDS_FILE")),
        "private_guard": [
            {"host": h, "rejected": blocked(h)}
            for h in (
                "127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.169.254",
                "::1", "0.0.0.0", "224.0.0.1", "evil.example.com",
            )
        ],
        "allowlist_ok": [guarded_get(21000, "api.ipify.org") for _ in range(3)],
        "hot_swap": [
            {"port": p, "host": "api.ipify.org", **guarded_get(p, "api.ipify.org")}
            for p in PROXY_PORTS
        ],
        "reject_outside": guarded_get(21000, "evil.example.com"),
    }
    results["total_wall_ms"] = round((time.monotonic() - t_start) * 1000, 1)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
