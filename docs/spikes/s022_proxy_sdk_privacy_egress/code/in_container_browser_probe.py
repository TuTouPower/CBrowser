#!/usr/bin/env python3
"""Inside-browser-container runner for s022 real CloakBrowser SDK + Chromium 146 checks."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from cloakbrowser import launch_persistent_context_async


def _read_chrome_cmdlines() -> list[list[str]]:
    out: list[list[str]] = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            raw = (p / "cmdline").read_bytes()
        except OSError:
            continue
        if b"chrome" in raw:
            parts = [x.decode("utf-8", errors="replace") for x in raw.split(b"\x00") if x]
            # Redact user:pass@ in proxy-server arg before recording
            sanitized = []
            for part in parts:
                if part.startswith("--proxy-server=") and "@" in part:
                    scheme_part, rest = part.split("://", 1)
                    _creds, host_part = rest.rsplit("@", 1)
                    sanitized.append(f"{scheme_part}://REDACTED@{host_part}")
                else:
                    sanitized.append(part)
            out.append(sanitized)
    return out


async def run_scenario(spec: dict[str, Any]) -> dict[str, Any]:
    os.environ["CLOAKBROWSER_CACHE_DIR"] = "/data/engine-cache"
    if spec.get("ca_cert"):
        os.environ["SSL_CERT_FILE"] = spec["ca_cert"]
        os.environ["REQUESTS_CA_BUNDLE"] = spec["ca_cert"]
    if spec.get("geoip_timeout_seconds") is not None:
        os.environ["CLOAKBROWSER_GEOIP_TIMEOUT_SECONDS"] = str(spec["geoip_timeout_seconds"])

    user_data_dir = Path(spec.get("user_data_dir") or tempfile.mkdtemp(prefix="s022_prof_", dir="/tmp"))
    user_data_dir.mkdir(parents=True, exist_ok=True)
    if spec.get("preferences"):
        default_dir = user_data_dir / "Default"
        default_dir.mkdir(parents=True, exist_ok=True)
        (default_dir / "Preferences").write_text(
            json.dumps(spec["preferences"]), encoding="utf-8"
        )

    # Start Xvfb for headed launch matching BrowserRunner (headless=False)
    xvfb = subprocess.Popen(
        ["Xvfb", ":99", "-screen", "0", "1280x720x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.environ["DISPLAY"] = ":99"
    time.sleep(0.4)

    result: dict[str, Any] = {
        "name": spec["name"],
        "launch_ok": False,
        "error": None,
        "nav_results": {},
        "js_env": None,
        "webrtc": None,
        "seed": None,
        "chrome_proxy_flags": [],
        "chrome_fingerprint_flags": [],
    }

    extra_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--window-position=0,0",
        "--window-size=1280,720",
        "--force-device-scale-factor=1",
        "--fingerprint-platform=windows",
        *(spec.get("extra_args") or []),
    ]
    if spec.get("ca_cert"):
        # Compute SPKI pin or ignore-certificate-errors for controlled HTTPS target in spike only
        extra_args.append("--ignore-certificate-errors")

    ctx = None
    try:
        ctx = await launch_persistent_context_async(
            user_data_dir=str(user_data_dir),
            headless=False,
            proxy=spec.get("proxy"),
            args=extra_args,
            timezone=spec.get("timezone"),
            locale=spec.get("locale"),
            geoip=bool(spec.get("geoip", False)),
            no_viewport=True,
            browser_version=spec.get("browser_version", "146.0.7680.177.3"),
        )
        result["launch_ok"] = True
        cmdlines = _read_chrome_cmdlines()
        if cmdlines:
            main_cmd = cmdlines[0]
            result["chrome_proxy_flags"] = [a for a in main_cmd if "proxy" in a or "webrtc" in a or "quic" in a.lower()]
            result["chrome_fingerprint_flags"] = [
                a for a in main_cmd if a.startswith(("--fingerprint", "--lang="))
            ]

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for url in spec.get("urls") or []:
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=12000)
                text = await page.evaluate("document.body ? document.body.innerText : ''")
                result["nav_results"][url] = {
                    "ok": True,
                    "status": resp.status if resp else None,
                    "body": text[:500],
                }
            except Exception as nav_exc:
                result["nav_results"][url] = {
                    "ok": False,
                    "error": f"{type(nav_exc).__name__}: {str(nav_exc)[:300]}",
                }

        try:
            result["js_env"] = await page.evaluate(
                """() => ({
                    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    lang: navigator.language,
                    langs: navigator.languages,
                    platform: navigator.platform
                })"""
            )
        except Exception as exc:
            result["js_env"] = {"error": str(exc)[:200]}

        if spec.get("webrtc_url"):
            try:
                await page.goto(spec["webrtc_url"], wait_until="domcontentloaded", timeout=12000)
                ice_servers = spec.get("ice_servers") or []
                result["webrtc"] = await page.evaluate(
                    "(ice) => window.runWebRTCProbe(ice)", ice_servers
                )
            except Exception as w_exc:
                result["webrtc"] = {"error": f"{type(w_exc).__name__}: {str(w_exc)[:300]}"}

        seed_file = user_data_dir / ".cloakbrowser-seed"
        if seed_file.is_file():
            result["seed"] = seed_file.read_text(encoding="utf-8").strip()
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
    finally:
        if ctx is not None:
            try:
                await ctx.close()
            except Exception:
                pass
        xvfb.terminate()
        try:
            xvfb.wait(timeout=3)
        except subprocess.TimeoutExpired:
            xvfb.kill()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-file", required=True)
    parser.add_argument("--out-file", required=True)
    args = parser.parse_args()
    spec = json.loads(Path(args.spec_file).read_text(encoding="utf-8"))
    res = asyncio.run(run_scenario(spec))
    Path(args.out_file).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
