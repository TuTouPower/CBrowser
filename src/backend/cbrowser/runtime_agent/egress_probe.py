"""One-shot egress probe helper (t052).

Runs inside the Browser image as a short-lived helper container, so it
shares the Browser's network policy and proxy parameters:

    python3 -m cbrowser.runtime_agent.egress_probe \
        --credentials-file /run/cbrowser/runtime/proxy_credentials.json \
        --geoip-db /data/engine-cache/geoip/GeoLite2-City.mmdb \
        --echo-url https://api.ipify.org

It prints exactly one JSON object to stdout — ``{"egress_ip", "country_code"}``
on success or ``{"error_code"}`` on failure — and nothing else.  The
password is read from the credentials file and never printed, logged or
echoed.  Exit code 0 means the probe produced an observation; 1 means it
did not (the caller records a failed observation with the error code).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cbrowser.domain.egress_observation import (
    ECHO_URLS,
    EgressProbeError,
    GeoIpLookup,
    probe_egress,
)
from cbrowser.domain.proxy_endpoint import ProxyEndpoint


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe proxy egress (t052)")
    parser.add_argument("--credentials-file", required=True)
    parser.add_argument("--echo-url", action="append", default=[])
    parser.add_argument("--geoip-db", default=None)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    try:
        raw = json.loads(Path(args.credentials_file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _emit({"error_code": "proxy_credentials_unavailable"})
        return 1
    if not isinstance(raw, dict):
        _emit({"error_code": "proxy_credentials_unavailable"})
        return 1
    try:
        endpoint = ProxyEndpoint(
            scheme=raw["scheme"],
            host=raw["host"],
            port=raw["port"],
            username=raw.get("username"),
            password=raw.get("password"),
        )
    except (KeyError, TypeError, ValueError):
        _emit({"error_code": "proxy_credentials_unavailable"})
        return 1

    echo_urls = tuple(args.echo_url) if args.echo_url else ECHO_URLS
    try:
        egress_ip, country = probe_egress(
            endpoint,
            echo_urls=echo_urls,
            geoip=GeoIpLookup(db_path=args.geoip_db),
            timeout=args.timeout,
        )
    except EgressProbeError as exc:
        _emit({"error_code": exc.code})
        return 1
    _emit({"egress_ip": egress_ip, "country_code": country})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
