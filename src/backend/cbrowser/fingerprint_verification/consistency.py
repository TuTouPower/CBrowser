"""AC-006: Cross-layer TLS / UA / Client Hints consistency evaluator."""

from __future__ import annotations

from typing import Any, Mapping

_PLATFORM_EXPECTATIONS: dict[str, dict[str, str]] = {
    "windows": {
        "js_platform": "Win32",
        "ua_substring": "Windows NT",
        "ch_platform": "Windows",
        "ch_platform_version": "19.0.0",
    },
    "macos": {
        "js_platform": "MacIntel",
        "ua_substring": "Macintosh",
        "ch_platform": "macOS",
        "ch_platform_version": "15.2.0",
    },
}


def _strip_quotes(val: str | None) -> str | None:
    if val is None:
        return None
    s = val.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def evaluate_tls_ua_ch_consistency(report: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate TLS/UA/Client Hints consistency bound to engine/config/probe versions."""
    profile = report.get("profile") or {}
    cfg = profile.get("config_summary") or {}
    engine = report.get("engine_artifact") or {}
    metrics = report.get("metrics") or {}
    http_headers = report.get("http_headers") or {}
    http_header_samples = report.get("http_header_samples") or {}
    tls = report.get("tls_evidence") or {}

    bound_identity = {
        "profile_id": profile.get("profile_id"),
        "config_version": profile.get("config_version"),
        "engine_build": engine.get("engine_build"),
        "binary_sha256": engine.get("binary_sha256"),
        "probe_version": report.get("probe_version"),
    }

    target_platform = cfg.get("fingerprint_platform")
    expected = _PLATFORM_EXPECTATIONS.get(str(target_platform))
    findings: list[dict[str, Any]] = []

    if expected is None:
        findings.append({
            "layer": "config",
            "status": "inconsistent",
            "detail": f"Unknown fingerprint_platform={target_platform!r}",
        })

    # 1. JS contexts consistency (main, iframe, worker, service_worker)
    js_ua_values: dict[str, Any] = {}
    if expected is not None:
        for ctx in ("main", "iframe", "worker", "service_worker"):
            ua_entry = metrics.get(f"{ctx}.userAgent") or {}
            plat_entry = metrics.get(f"{ctx}.platform") or {}
            ch_low = metrics.get(f"{ctx}.uaDataLow") or {}
            ch_high = metrics.get(f"{ctx}.uaDataHigh") or {}
            if ua_entry.get("status") != "ok":
                findings.append({
                    "layer": f"js.{ctx}",
                    "status": "missing",
                    "detail": f"{ctx}.userAgent unavailable ({ua_entry.get('status')})",
                })
            else:
                ua_val = ua_entry.get("canonical_value")
                js_ua_values[ctx] = ua_val
                if not isinstance(ua_val, str) or expected["ua_substring"] not in ua_val:
                    findings.append({
                        "layer": f"js.{ctx}",
                        "status": "inconsistent",
                        "detail": f"{ctx}.userAgent={ua_val!r} missing {expected['ua_substring']!r}",
                    })

            if plat_entry.get("status") != "ok":
                findings.append({
                    "layer": f"js.{ctx}",
                    "status": "missing",
                    "detail": f"{ctx}.platform unavailable ({plat_entry.get('status')})",
                })
            elif plat_entry.get("canonical_value") != expected["js_platform"]:
                findings.append({
                    "layer": f"js.{ctx}",
                    "status": "inconsistent",
                    "detail": f"{ctx}.platform={plat_entry.get('canonical_value')!r} != {expected['js_platform']!r}",
                })

            if ch_low.get("status") != "ok":
                findings.append({
                    "layer": f"js.{ctx}",
                    "status": "missing",
                    "detail": f"{ctx}.uaDataLow unavailable ({ch_low.get('status')})",
                })
            else:
                ch_plat = (ch_low.get("canonical_value") or {}).get("platform")
                if ch_plat != expected["ch_platform"]:
                    findings.append({
                        "layer": f"js.{ctx}",
                        "status": "inconsistent",
                        "detail": f"{ctx}.uaDataLow.platform={ch_plat!r} != {expected['ch_platform']!r}",
                    })

            if ch_high.get("status") != "ok":
                findings.append({
                    "layer": f"js.{ctx}",
                    "status": "missing",
                    "detail": f"{ctx}.uaDataHigh unavailable ({ch_high.get('status')})",
                })
            else:
                high_val = ch_high.get("canonical_value") or {}
                if high_val.get("platform") != expected["ch_platform"]:
                    findings.append({
                        "layer": f"js.{ctx}",
                        "status": "inconsistent",
                        "detail": f"{ctx}.uaDataHigh.platform={high_val.get('platform')!r} != {expected['ch_platform']!r}",
                    })
                if high_val.get("platformVersion") != expected["ch_platform_version"]:
                    findings.append({
                        "layer": f"js.{ctx}",
                        "status": "inconsistent",
                        "detail": f"{ctx}.uaDataHigh.platformVersion={high_val.get('platformVersion')!r} != {expected['ch_platform_version']!r}",
                    })

        if len({str(v) for v in js_ua_values.values()}) > 1:
            findings.append({
                "layer": "js.cross_context",
                "status": "inconsistent",
                "detail": f"Cross-context navigator.userAgent mismatch: {js_ua_values!r}",
            })

    # 2. HTTP request headers vs JS / config (including sample completeness & determinism)
    main_sample_entry = http_header_samples.get("main_after_ch")
    main_reported_bad = False
    if isinstance(main_sample_entry, Mapping):
        if main_sample_entry.get("status") != "ok":
            main_reported_bad = True
            findings.append({
                "layer": "http.main_after_ch",
                "status": "missing",
                "detail": (
                    "main_after_ch HTTP headers incomplete across samples "
                    f"(missing indices={main_sample_entry.get('missing_sample_indices')})"
                ),
            })
        elif main_sample_entry.get("determinism") == "non_deterministic":
            main_reported_bad = True
            findings.append({
                "layer": "http.main_after_ch",
                "status": "inconsistent",
                "detail": "main_after_ch HTTP headers varied across repeated samples",
            })

    for req_cls, sample_entry in sorted(http_header_samples.items()):
        if req_cls == "main_after_ch" or not isinstance(sample_entry, Mapping):
            continue
        if sample_entry.get("status") != "ok":
            findings.append({
                "layer": f"http.{req_cls}",
                "status": "missing",
                "detail": f"{req_cls} HTTP headers incomplete across samples",
            })
        elif sample_entry.get("determinism") == "non_deterministic":
            findings.append({
                "layer": f"http.{req_cls}",
                "status": "inconsistent",
                "detail": f"{req_cls} HTTP headers varied across repeated samples",
            })

    main_headers = {
        k.lower(): v for k, v in (http_headers.get("main_after_ch") or {}).items()
    }
    ref_js_ua = js_ua_values.get("main") or next(iter(js_ua_values.values()), None)
    if not main_headers and not main_reported_bad:
        findings.append({
            "layer": "http.main_after_ch",
            "status": "missing",
            "detail": "main_after_ch HTTP headers missing",
        })
    elif main_headers and expected is not None:
        hdr_ua = main_headers.get("user-agent")
        if not hdr_ua or expected["ua_substring"] not in hdr_ua:
            findings.append({
                "layer": "http.main_after_ch",
                "status": "inconsistent",
                "detail": f"HTTP User-Agent={hdr_ua!r} missing {expected['ua_substring']!r}",
            })
        if ref_js_ua and hdr_ua != ref_js_ua:
            findings.append({
                "layer": "http.main_after_ch",
                "status": "inconsistent",
                "detail": "HTTP User-Agent differs from JS navigator.userAgent",
            })
        hdr_ch_plat = _strip_quotes(main_headers.get("sec-ch-ua-platform"))
        if hdr_ch_plat != expected["ch_platform"]:
            findings.append({
                "layer": "http.main_after_ch",
                "status": "inconsistent",
                "detail": f"HTTP Sec-CH-UA-Platform={hdr_ch_plat!r} != {expected['ch_platform']!r}",
            })
        hdr_ch_ver = _strip_quotes(main_headers.get("sec-ch-ua-platform-version"))
        if hdr_ch_ver != expected["ch_platform_version"]:
            findings.append({
                "layer": "http.main_after_ch",
                "status": "inconsistent",
                "detail": f"HTTP Sec-CH-UA-Platform-Version={hdr_ch_ver!r} != {expected['ch_platform_version']!r}",
            })

    if expected is not None:
        for req_cls in (
            "iframe_doc",
            "main_fetch",
            "worker_script",
            "worker_fetch",
            "sw_script",
            "sw_fetch",
        ):
            raw_cls_hdrs = http_headers.get(req_cls)
            if not isinstance(raw_cls_hdrs, Mapping):
                continue
            cls_hdrs = {k.lower(): v for k, v in raw_cls_hdrs.items()}
            cls_ua = cls_hdrs.get("user-agent")
            if not cls_ua or expected["ua_substring"] not in cls_ua:
                findings.append({
                    "layer": f"http.{req_cls}",
                    "status": "inconsistent",
                    "detail": f"{req_cls} User-Agent={cls_ua!r} missing {expected['ua_substring']!r}",
                })
            elif ref_js_ua and cls_ua != ref_js_ua:
                findings.append({
                    "layer": f"http.{req_cls}",
                    "status": "inconsistent",
                    "detail": f"{req_cls} User-Agent differs from JS navigator.userAgent",
                })
            if req_cls in ("iframe_doc", "main_fetch") and "sec-ch-ua-platform" in cls_hdrs:
                cls_plat = _strip_quotes(cls_hdrs.get("sec-ch-ua-platform"))
                if cls_plat != expected["ch_platform"]:
                    findings.append({
                        "layer": f"http.{req_cls}",
                        "status": "inconsistent",
                        "detail": f"{req_cls} Sec-CH-UA-Platform={cls_plat!r} != {expected['ch_platform']!r}",
                    })

    # 3. Local TLS handshake evidence
    tls_available = bool((report.get("collection_context") or {}).get("tls_capture_available"))
    tls_status = "inconclusive"
    tls_observation: dict[str, Any] = {}
    if not tls_available or tls.get("status") != "ok":
        tls_status = "inconclusive"
        tls_observation = {
            "status": "inconclusive",
            "reason": tls.get("reason") or "local TLS handshake capture unavailable",
        }
    else:
        ja4_dist = tls.get("ja4_distribution") or {}
        if not ja4_dist.get("unique_values"):
            tls_status = "inconclusive"
            tls_observation = {
                "status": "inconclusive",
                "reason": "TLS capture enabled but zero ClientHello JA4 samples recorded",
            }
        else:
            tls_status = "verified"
            tls_observation = {
                "status": "verified",
                "supported_versions": tls.get("supported_versions", []),
                "alpn": tls.get("alpn", []),
                "ja4_values": ja4_dist.get("unique_values", []),
                "ja3_raw_unique_count": (tls.get("ja3_raw_distribution") or {}).get("unique_count"),
                "stack_note": (
                    "Observed local BoringSSL/Chromium TLS ClientHello; Linux container "
                    "BoringSSL TLS stack is shared across windows/macos personas."
                ),
            }

    # Explicit non-p045 architectural note when windows runs on linux-arm64
    arch_note = None
    main_high = (metrics.get("main.uaDataHigh") or {}).get("canonical_value") or {}
    if target_platform == "windows" and main_high.get("architecture") == "arm":
        arch_note = (
            "Known platform limitation (d032/p045 parked): Windows UA reports x64 while "
            "UA-CH architecture on linux-arm64 reports arm; intentionally left untouched."
        )

    has_inconsistent = any(f["status"] == "inconsistent" for f in findings)
    has_missing = any(f["status"] == "missing" for f in findings)
    if has_inconsistent:
        verdict = "inconsistent"
    elif has_missing or tls_status != "verified":
        verdict = "inconclusive"
    else:
        verdict = "consistent"

    return {
        "verdict": verdict,
        "tls_status": tls_status,
        "bound_identity": bound_identity,
        "tls_observation": tls_observation,
        "arch_observation_note": arch_note,
        "findings": findings,
    }
