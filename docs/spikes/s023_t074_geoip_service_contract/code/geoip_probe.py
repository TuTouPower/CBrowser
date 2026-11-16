"""s023: 经真实代理出口实测免 Key HTTPS GeoIP 服务的字段稳定性 / RTT / 限流。

运行：gate venv python（httpx 0.28），代理为本地 mihomo-proxy 的一对一节点端口。
输出 code/results.json，不写入任何凭据。
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

import httpx

PORTS = [21000, 21001, 21003, 21013, 21062]
SERVICES = {
    "ipwho.is": "https://ipwho.is/",
    "api.ip.sb": "https://api.ip.sb/geoip",
    "freeipapi": "https://freeipapi.com/api/json",
    "ipify": "https://api.ipify.org",
}
OUT = Path(__file__).resolve().parent / "results.json"


def extract(name: str, body: str) -> dict:
    if name == "ipify":
        return {"json_ok": True, "ip": body.strip(), "kind": "plain_ip_echo"}
    try:
        d = json.loads(body)
    except Exception:
        return {"json_ok": False, "raw": body[:120]}
    if name == "ipwho.is":
        return {
            "json_ok": True, "ip": d.get("ip"),
            "country_code": d.get("country_code"),
            "country_name": d.get("country"), "city": d.get("city"),
            "success": d.get("success"),
        }
    if name == "api.ip.sb":
        return {
            "json_ok": True, "ip": d.get("ip"),
            "country_code": d.get("country_code"),
            "country_name": d.get("country"), "city": d.get("city"),
        }
    return {
        "json_ok": True,
        "ip": d.get("ipAddress") or d.get("ip"),
        "country_code": d.get("countryCode"),
        "country_name": d.get("countryName"),
        "city": d.get("cityName"),
    }


def probe(port: int, name: str, url: str) -> dict:
    t0 = time.monotonic()
    try:
        with httpx.Client(
            proxy=f"http://127.0.0.1:{port}",
            trust_env=False,
            timeout=20.0,
            follow_redirects=True,
        ) as client:
            r = client.get(url)
        rtt_ms = round((time.monotonic() - t0) * 1000, 1)
        return {
            "port": port, "service": name, "http": r.status_code,
            "rtt_ms": rtt_ms, **extract(name, r.text),
        }
    except Exception as exc:  # noqa: BLE001 - spike records every failure mode
        return {
            "port": port, "service": name, "http": None,
            "rtt_ms": round((time.monotonic() - t0) * 1000, 1),
            "error": f"{type(exc).__name__}: {exc}"[:160],
        }


def main() -> None:
    rows = [probe(p, n, u) for p in PORTS for n, u in SERVICES.items()]
    burst = [
        probe(21000, "ipify", SERVICES["ipify"])
        for _ in range(12)
    ]

    by_service = {}
    for name in SERVICES:
        subset = [r for r in rows if r["service"] == name]
        ok = [r for r in subset if r["http"] == 200 and r.get("json_ok")]
        rtts = [r["rtt_ms"] for r in ok]
        by_service[name] = {
            "ok": len(ok), "total": len(subset),
            "http_codes": sorted(
                {r["http"] for r in subset}, key=lambda x: (x is None, x)
            ),
            "rtt_median_ms": round(statistics.median(rtts), 1) if rtts else None,
            "rtt_min_ms": min(rtts) if rtts else None,
            "rtt_max_ms": max(rtts) if rtts else None,
            "sample": ok[0] if ok else None,
            "failures": [
                r.get("error") for r in subset if r["http"] is None
            ][:2],
        }

    OUT.write_text(
        json.dumps(
            {
                "matrix": rows, "by_service": by_service,
                "burst": [{"http": b["http"], "rtt_ms": b.get("rtt_ms")} for b in burst],
            },
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(by_service, ensure_ascii=False, indent=2))
    print("burst http:", [b["http"] for b in burst])


if __name__ == "__main__":
    main()
