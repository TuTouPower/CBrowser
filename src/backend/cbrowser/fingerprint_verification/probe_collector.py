"""Offline CDP / Font / Multi-context fingerprint probe collector & sample aggregator."""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from cbrowser import font_sets
from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig
from cbrowser.engine_artifacts import (
    current_linux_platform_tag,
    verify_extracted_engine_cache,
)
from cbrowser.runtime_agent.fontconfig import (
    BASE_FONTS_DIR,
    FONT_SET_MOUNT_ROOT,
)
from cbrowser.runtime_agent.runner import BrowserRunner

from .consistency import evaluate_tls_ua_ch_consistency
from .tls_capture import TLSObservingProbeServer

PROBE_VERSION = "cbrowser-fp-probe/v1"
REPORT_SCHEMA = "cbrowser-fingerprint-report/v1"

ALL_CONTEXTS: tuple[str, ...] = ("main", "iframe", "worker", "service_worker")
ALL_METRICS: tuple[str, ...] = (
    "userAgent",
    "platform",
    "language",
    "languages",
    "hardwareConcurrency",
    "deviceMemory",
    "webdriver",
    "pdfViewerEnabled",
    "uaDataLow",
    "uaDataHigh",
    "timezone",
    "screen",
    "storageEstimate",
    "canvas2d",
    "webgl",
    "audio",
    "fonts",
    "webrtc",
)
WINDOW_ONLY_METRICS = frozenset(
    {"webdriver", "pdfViewerEnabled", "screen", "audio", "webrtc"}
)

_LINUX_FONT_RE = re.compile(
    r"Liberation|Nimbus|DejaVu|URW|Standard Symbols|P052|C059|D050000L|Z003|"
    r"WenQuanYi|文泉驿|Unifont|FreeSans|FreeSerif|FreeMono|IPAGothic|IPA|"
    r"Loma|Noto Color Emoji",
    re.IGNORECASE,
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def sanitize_config_summary(config: ProfileConfig) -> dict[str, Any]:
    """Return a secret-free summary of the ProfileConfig snapshot."""
    return {
        "name": config.name,
        "fingerprint_platform": config.fingerprint_platform,
        "font_set_id": config.font_set_id,
        "locale": config.locale,
        "timezone": config.timezone,
        "screen_width": config.screen_width,
        "screen_height": config.screen_height,
        "gpu_family": config.gpu_family,
        "fingerprint_seed": config.fingerprint_seed,
        "geoip": config.geoip,
        "humanize": config.humanize,
        "human_preset": config.human_preset,
        "allow_3p_cookies": config.allow_3p_cookies,
        "portable_cookies": config.portable_cookies,
        "transparent_proxy": config.transparent_proxy,
        "has_proxy": bool(config.proxy_id),
        "color_scheme": config.color_scheme,
    }


def collect_offline_font_evidence(
    *,
    fontconfig_path: Path | None,
    platform_name: str,
    font_set_id: str | None,
    font_set_root: Path = FONT_SET_MOUNT_ROOT,
) -> dict[str, Any]:
    """Reuse font_sets integrity checks and run offline fc-list/fc-match probe."""
    # Only reproducible observations belong in a fingerprint report. A
    # per-run temp path (fontconfig_file) would drift on every measurement
    # without representing any engine/config change.
    evidence: dict[str, Any] = {
        "platform": platform_name,
        "font_set_id": font_set_id,
        "fontconfig_present": bool(
            fontconfig_path is not None and fontconfig_path.is_file()
        ),
        "manifest_integrity": None,
        "fc_list": None,
        "fc_match": None,
    }
    if font_set_id:
        set_dir = font_set_root / platform_name / font_set_id
        if set_dir.is_dir():
            evidence["manifest_integrity"] = font_sets.check_font_set(set_dir)
        else:
            evidence["manifest_integrity"] = {"ok": False, "problems": ["font set dir missing"]}
    else:
        evidence["manifest_integrity"] = {
            "ok": True,
            "note": f"unbound fallback to {BASE_FONTS_DIR}",
        }

    if fontconfig_path is None or not fontconfig_path.is_file():
        return evidence

    env = dict(os.environ)
    env["FONTCONFIG_FILE"] = str(fontconfig_path)
    try:
        proc = subprocess.run(
            ["fc-list", ":", "family"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
            check=False,
        )
        families = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        files_proc = subprocess.run(
            ["fc-list", "-f", "%{file}\n"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
            check=False,
        )
        files = sorted({line.strip() for line in files_proc.stdout.splitlines() if line.strip()})
        evidence["fc_list"] = {
            "returncode": proc.returncode,
            "family_count": len(families),
            "file_count": len(files),
            "linux_font_hits": sum(1 for fam in families if _LINUX_FONT_RE.search(fam)),
        }
        probe_names = (
            ("Microsoft YaHei", "SimSun", "Segoe UI", "Consolas")
            if platform_name == "windows"
            else ("PingFang SC", "Hiragino Sans GB", "Helvetica Neue", "Menlo")
        )
        matches: dict[str, str] = {}
        for fam in probe_names:
            m = subprocess.run(
                ["fc-match", "-f", "%{family}|%{file}", fam],
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
                check=False,
            )
            matches[fam] = m.stdout.strip()
        evidence["fc_match"] = matches
    except (OSError, subprocess.SubprocessError) as exc:
        evidence["fc_list"] = {"error": f"{type(exc).__name__}: {exc}"}
    return evidence


def classify_http_records(records: list[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """Classify raw HTTP requests into stable per-context request-header snapshots."""
    classified: dict[str, dict[str, str]] = {}
    for rec in records:
        path = str(rec.get("path") or "")
        headers = dict(rec.get("headers") or {})
        if path == "/":
            if "sec-ch-ua-arch" in headers or "sec-ch-ua-platform-version" in headers:
                classified["main_after_ch"] = headers
            else:
                classified.setdefault("main_initial", headers)
        elif path == "/main-fetch":
            classified["main_fetch"] = headers
        elif path == "/iframe":
            classified["iframe_doc"] = headers
        elif path == "/worker.js":
            classified["worker_script"] = headers
        elif path == "/worker-fetch":
            classified["worker_fetch"] = headers
        elif path == "/sw.js":
            classified["sw_script"] = headers
        elif path == "/sw-fetch":
            classified["sw_fetch"] = headers
        elif path == "/favicon.ico":
            classified["favicon"] = headers
    return classified


def _summarize_distribution(values: list[str]) -> dict[str, Any]:
    counts = Counter(values)
    unique = sorted(counts.keys())
    return {
        "n": len(values),
        "unique_count": len(unique),
        "unique_values": unique,
        "counts": {k: counts[k] for k in unique},
    }


def _aggregate_tls_samples(
    samples: list[dict[str, Any]], *, tls_capture_available: bool
) -> dict[str, Any]:
    if not tls_capture_available:
        return {"status": "inconclusive", "reason": "tls_capture_unavailable"}
    handshakes: list[dict[str, Any]] = []
    for sample in samples:
        handshakes.extend(sample.get("tls_handshakes") or [])
    parsed_list = [h.get("client_hello") for h in handshakes if h.get("client_hello")]
    if not parsed_list:
        return {
            "status": "inconclusive",
            "reason": "no_tls_client_hello_captured",
        }
    ja4_vals = [p["ja4"] for p in parsed_list]
    ja3_sorted_vals = [p["ja3_sorted"] for p in parsed_list]
    ja3_raw_vals = [p["ja3"] for p in parsed_list]
    return {
        "status": "ok",
        "handshake_count": len(parsed_list),
        "supported_versions": sorted(
            {v for p in parsed_list for v in p.get("supported_versions", [])}
        ),
        "alpn": sorted(
            {a for p in parsed_list for a in p.get("alpn", [])}
        ),
        "sni": sorted(
            {s for p in parsed_list for s in p.get("sni", [])}
        ),
        "ciphers_set": sorted(
            {c for p in parsed_list for c in p.get("ciphers", [])}
        ),
        "extensions_set": sorted(
            {e for p in parsed_list for e in p.get("extensions_set", [])}
        ),
        "ja4_distribution": _summarize_distribution(ja4_vals),
        "ja3_sorted_distribution": _summarize_distribution(ja3_sorted_vals),
        "ja3_raw_distribution": {
            **_summarize_distribution(ja3_raw_vals),
            "note": "BoringSSL shuffles TLS extension order per connection.",
        },
    }


def aggregate_samples(
    *,
    profile_id: str,
    config_version: int,
    config: ProfileConfig,
    engine_artifact: Mapping[str, Any],
    samples: list[dict[str, Any]],
    execution_mode: str,
    scheme: str,
    tls_capture_available: bool,
    display: str | None = None,
    font_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate repeated probe samples into a canonical baseline/candidate report."""
    context_matrix: dict[str, dict[str, str]] = {}
    metrics: dict[str, dict[str, Any]] = {}

    for ctx in ALL_CONTEXTS:
        context_matrix[ctx] = {}
        for metric_name in ALL_METRICS:
            per_sample = [
                ((sample.get("contexts") or {}).get(ctx) or {}).get("metrics", {}).get(metric_name)
                for sample in samples
            ]
            statuses = [
                (item.get("status") if isinstance(item, dict) else "missing")
                for item in per_sample
            ]
            if all(s == "unsupported_context" for s in statuses) and statuses:
                context_matrix[ctx][metric_name] = "unsupported_context"
                reason = (per_sample[0] or {}).get("reason") if isinstance(per_sample[0], dict) else "unsupported_context"
                metrics[f"{ctx}.{metric_name}"] = {
                    "context": ctx,
                    "metric": metric_name,
                    "status": "unsupported_context",
                    "determinism": "unsupported_context",
                    "reason": reason,
                    "values": ["unsupported_context"] * len(statuses),
                    "canonical_value": None,
                }
                continue

            if any(s != "ok" for s in statuses) or not statuses:
                bad_status = next((s for s in statuses if s != "ok"), "missing")
                context_matrix[ctx][metric_name] = bad_status
                reasons = [
                    (item.get("error") or item.get("reason") or item.get("status"))
                    if isinstance(item, dict)
                    else "missing"
                    for item in per_sample
                ]
                metrics[f"{ctx}.{metric_name}"] = {
                    "context": ctx,
                    "metric": metric_name,
                    "status": bad_status,
                    "determinism": "missing",
                    "reason": "; ".join(str(r) for r in reasons),
                    "values": [
                        item.get("value") if isinstance(item, dict) and item.get("status") == "ok" else None
                        for item in per_sample
                    ],
                    "canonical_value": None,
                }
                continue

            context_matrix[ctx][metric_name] = "ok"
            values = [item["value"] for item in per_sample if isinstance(item, dict)]
            unique_map: dict[str, Any] = {}
            for val in values:
                unique_map.setdefault(_canonical(val), val)
            unique_values = [unique_map[k] for k in sorted(unique_map)]
            is_det = len(unique_values) == 1
            entry: dict[str, Any] = {
                "context": ctx,
                "metric": metric_name,
                "status": "ok",
                "determinism": "deterministic" if is_det else "non_deterministic",
                "values": values,
                "unique_values": unique_values,
                "unique_count": len(unique_values),
                "canonical_value": unique_values[0] if is_det else None,
            }
            if values and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
                entry["min"] = min(values)
                entry["max"] = max(values)
            metrics[f"{ctx}.{metric_name}"] = entry

    # Aggregate HTTP headers across all samples: preserve per-class sample completeness
    # and cross-sample variance instead of silently picking the last observation.
    sample_count = len(samples)
    http_headers_per_sample = [sample.get("http_headers") or {} for sample in samples]
    aggregated_http: dict[str, Any] = {}
    http_header_samples: dict[str, Any] = {}
    all_req_classes = sorted(
        {"main_after_ch"} | {k for h in http_headers_per_sample for k in h}
    )
    for req_cls in all_req_classes:
        per_sample_hdrs = [
            h.get(req_cls) if isinstance(h, Mapping) else None
            for h in http_headers_per_sample
        ]
        observed = [hdr for hdr in per_sample_hdrs if isinstance(hdr, Mapping)]
        missing_indices = [
            idx for idx, hdr in enumerate(per_sample_hdrs) if not isinstance(hdr, Mapping)
        ]
        unique_map: dict[str, dict[str, Any]] = {}
        for hdr in observed:
            norm_hdr = dict(hdr)
            unique_map.setdefault(_canonical(norm_hdr), norm_hdr)
        unique_values = [unique_map[k] for k in sorted(unique_map)]
        all_present = sample_count > 0 and len(observed) == sample_count
        if not all_present:
            http_header_samples[req_cls] = {
                "request_class": req_cls,
                "status": "missing",
                "determinism": "missing",
                "sample_count": sample_count,
                "observed_count": len(observed),
                "missing_sample_indices": missing_indices,
                "values": per_sample_hdrs,
                "unique_values": unique_values,
                "unique_count": len(unique_values),
                "canonical_value": None,
            }
            continue

        is_det = len(unique_values) == 1
        http_header_samples[req_cls] = {
            "request_class": req_cls,
            "status": "ok",
            "determinism": "deterministic" if is_det else "non_deterministic",
            "sample_count": sample_count,
            "observed_count": len(observed),
            "missing_sample_indices": [],
            "values": per_sample_hdrs,
            "unique_values": unique_values,
            "unique_count": len(unique_values),
            "canonical_value": unique_values[0] if is_det else None,
        }
        if is_det:
            aggregated_http[req_cls] = unique_values[0]

    tls_evidence = _aggregate_tls_samples(
        samples, tls_capture_available=tls_capture_available
    )

    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "probe_version": PROBE_VERSION,
        "profile": {
            "profile_id": profile_id,
            "config_version": config_version,
            "config_summary": sanitize_config_summary(config),
        },
        "engine_artifact": dict(engine_artifact),
        "collection_context": {
            "execution_mode": execution_mode,
            "scheme": scheme,
            "tls_capture_available": tls_capture_available,
            "os_arch": f"{platform.system()}/{platform.machine()}",
            "display": display,
            "sample_count": sample_count,
            "collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
        "context_matrix": context_matrix,
        "metrics": metrics,
        "http_headers": aggregated_http,
        "http_header_samples": http_header_samples,
        "tls_evidence": tls_evidence,
    }
    if font_evidence is not None:
        report["font_evidence"] = dict(font_evidence)
    report["consistency"] = evaluate_tls_ua_ch_consistency(report)
    return report


async def collect_sample_from_page(
    *,
    page: Any,
    browser_ws_url: str,
    server: TLSObservingProbeServer,
) -> dict[str, Any]:
    """Navigate an existing page to the local probe server and collect one sample."""
    import logging
    import websockets

    logger = logging.getLogger("cbrowser.fingerprint_verification.collector")
    server.reset_records()
    ws_conn = None
    console_messages: list[str] = []

    def _on_console(msg: Any) -> None:
        try:
            text = str(msg.text)
        except Exception:  # noqa: BLE001 - console capture is best-effort diagnostics
            return
        console_messages.append(text)
        if text.startswith("FP:"):
            logger.info("probe page %s", text)

    page.on("console", _on_console)
    try:
        if server.use_tls:
            logger.info("connecting browser CDP for TLS ignore")
            ws_conn = await websockets.connect(
                browser_ws_url, max_size=32 * 1024 * 1024
            )
            await ws_conn.send(
                json.dumps({
                    "id": 1,
                    "method": "Security.setIgnoreCertificateErrors",
                    "params": {"ignore": True},
                })
            )
            await ws_conn.recv()
            logger.info("Security.setIgnoreCertificateErrors applied")
        logger.info("navigating to %s", server.origin)
        await page.goto(server.origin, wait_until="domcontentloaded", timeout=30000)
        logger.info("navigation done; awaiting probe promise")
        try:
            contexts = await asyncio.wait_for(
                page.evaluate("() => window.__fpProbeDone"),
                timeout=45,
            )
        except Exception as exc:  # noqa: BLE001 - missing context is a measurement, not a crash
            logger.warning("probe promise incomplete (%s): %s", type(exc).__name__, exc)
            contexts = {
                ctx: {"context": ctx, "status": "error", "metrics": {}}
                for ctx in ("main", "iframe", "worker", "service_worker")
            }
        logger.info("probe promise resolved")
        await page.wait_for_timeout(200)
        return {
            "contexts": contexts,
            "tls_handshakes": list(server.tls_records),
            "http_headers": classify_http_records(list(server.http_records)),
            "console_messages": list(console_messages),
        }
    finally:
        try:
            page.remove_listener("console", _on_console)
        except Exception:  # noqa: BLE001 - listener cleanup is best-effort
            pass
        if ws_conn is not None:
            await ws_conn.close()


async def measure_profile_with_browser_runner(
    *,
    profile_id: str,
    config_version: int,
    config: ProfileConfig,
    engine_cache_dir: Path,
    engine_build: str | None = None,
    fonts_dir: Path | None = None,
    samples: int = 3,
    use_tls: bool = True,
    display: str = ":165",
    reuse_user_data: bool = False,
) -> dict[str, Any]:
    """Run real BrowserRunner instances against the local probe server and return full report."""
    target_tag = current_linux_platform_tag()
    verification = verify_extracted_engine_cache(
        engine_cache_dir,
        platform_tag=target_tag,
        engine_build=engine_build,
        run_version_probe=True,
    )
    engine_artifact = verification.to_dict()

    # Optionally mount host font set directory into FONT_SET_MOUNT_ROOT if not already mounted
    mounted_symlink: Path | None = None
    if fonts_dir is not None and config.font_set_id:
        expected_mount = FONT_SET_MOUNT_ROOT / config.fingerprint_platform / config.font_set_id
        src_dir = fonts_dir / config.fingerprint_platform / config.font_set_id
        if not expected_mount.exists() and src_dir.is_dir():
            expected_mount.parent.mkdir(parents=True, exist_ok=True)
            expected_mount.symlink_to(src_dir)
            mounted_symlink = expected_mount

    work_root = Path(tempfile.mkdtemp(prefix=f"cb-fp-measure-{profile_id}-"))
    shared_ud = work_root / "shared_profile"
    collected_samples: list[dict[str, Any]] = []
    last_fontconfig: Path | None = None
    cdp_product: str | None = None
    cdp_ua: str | None = None

    try:
        with TLSObservingProbeServer(use_tls=use_tls) as server:
            for idx in range(samples):
                sample_dir = work_root / f"sample_{idx}"
                sample_dir.mkdir(parents=True, exist_ok=True)
                snap_path = sample_dir / "snapshot.json"
                snapshot = ConfigVersionSnapshot(
                    id=f"snap-{profile_id}-v{config_version}",
                    profile_id=profile_id,
                    version=config_version,
                    config=config.model_dump(),
                    created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                )
                snap_path.write_text(snapshot.model_dump_json(), encoding="utf-8")

                ud_dir = shared_ud if reuse_user_data else (sample_dir / "profile")
                runner = BrowserRunner(
                    profile_id=profile_id,
                    runtime_instance_id=f"fp_{idx}_{os.getpid()}",
                    config_snapshot_path=snap_path,
                    run_dir=sample_dir / "run",
                    user_data_dir=ud_dir,
                    events_dir=sample_dir / "events",
                    engine_cache_dir=engine_cache_dir,
                    display=display,
                    engine_build=verification.engine_build,
                )
                prev_pulse = os.environ.get("PULSE_RUNTIME_PATH")
                os.environ["PULSE_RUNTIME_PATH"] = str(runner.pulse_dir / "runtime")
                try:
                    await runner.start()
                    last_fontconfig = runner.fontconfig_path
                    info_json = json.loads(runner.runner_info_file.read_text(encoding="utf-8"))
                    cdp_product = info_json.get("browser_product")
                    cdp_ua = info_json.get("browser_user_agent")
                    page = (
                        runner.browser_context.pages[0]
                        if runner.browser_context.pages
                        else await runner.browser_context.new_page()
                    )
                    assert runner.browser_ws_url is not None
                    sample_res = await collect_sample_from_page(
                        page=page,
                        browser_ws_url=runner.browser_ws_url,
                        server=server,
                    )
                    collected_samples.append(sample_res)
                finally:
                    await runner.stop()
                    try:
                        subprocess.run(
                            ["pulseaudio", "--kill"],
                            env={**os.environ, "PULSE_RUNTIME_PATH": str(runner.pulse_dir / "runtime")},
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5,
                            check=False,
                        )
                    except (OSError, subprocess.SubprocessError):
                        pass
                    if prev_pulse is None:
                        os.environ.pop("PULSE_RUNTIME_PATH", None)
                    else:
                        os.environ["PULSE_RUNTIME_PATH"] = prev_pulse

        engine_artifact["cdp_browser_product"] = cdp_product
        engine_artifact["cdp_browser_user_agent"] = cdp_ua
        font_evidence = collect_offline_font_evidence(
            fontconfig_path=last_fontconfig,
            platform_name=config.fingerprint_platform,
            font_set_id=config.font_set_id,
            font_set_root=FONT_SET_MOUNT_ROOT,
        )
        return aggregate_samples(
            profile_id=profile_id,
            config_version=config_version,
            config=config,
            engine_artifact=engine_artifact,
            samples=collected_samples,
            execution_mode="browser_runner_container",
            scheme="https" if use_tls else "http",
            tls_capture_available=use_tls,
            display=display,
            font_evidence=font_evidence,
        )
    finally:
        if mounted_symlink is not None and mounted_symlink.is_symlink():
            mounted_symlink.unlink(missing_ok=True)
        shutil.rmtree(work_root, ignore_errors=True)
