"""t068 AC-001 / AC-002 / AC-006: multi-context diff gate, TLS JA3/JA4 & consistency."""

from __future__ import annotations

import copy
import struct


def _build_tls_client_hello(
    *,
    ciphers: list[int],
    extensions: list[tuple[int, bytes]],
    sni: str | None = "localhost",
) -> bytes:
    ext_bytes = bytearray()
    if sni is not None:
        host_b = sni.encode("ascii")
        sni_entry = b"\x00" + struct.pack("!H", len(host_b)) + host_b
        sni_payload = struct.pack("!H", len(sni_entry)) + sni_entry
        ext_bytes += struct.pack("!HH", 0x0000, len(sni_payload)) + sni_payload
    for etype, payload in extensions:
        ext_bytes += struct.pack("!HH", etype, len(payload)) + payload

    hs_body = bytearray()
    hs_body += struct.pack("!H", 0x0303)  # legacy version TLS 1.2
    hs_body += b"\x11" * 32  # random
    hs_body += b"\x00"  # session_id_len=0
    hs_body += struct.pack("!H", len(ciphers) * 2)
    for c in ciphers:
        hs_body += struct.pack("!H", c)
    hs_body += b"\x01\x00"  # compression methods: null
    hs_body += struct.pack("!H", len(ext_bytes)) + ext_bytes

    hs = bytes([0x01]) + len(hs_body).to_bytes(3, "big") + bytes(hs_body)
    record = struct.pack("!BHH", 0x16, 0x0301, len(hs)) + hs
    return record


def _base_report(*, engine_build: str = "146.0.7680.177.3", tls_available: bool = True) -> dict:
    contexts = ("main", "iframe", "worker", "service_worker")
    window_only = {"webdriver", "pdfViewerEnabled", "screen", "audio", "webrtc"}
    metrics = {}
    context_matrix = {}
    for ctx in contexts:
        context_matrix[ctx] = {}
        for name, val in (
            ("userAgent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"),
            ("platform", "Win32"),
            ("language", "en-US"),
            ("languages", ["en-US"]),
            ("hardwareConcurrency", 8),
            ("deviceMemory", 8),
            ("webdriver", False),
            ("pdfViewerEnabled", True),
            ("uaDataLow", {"platform": "Windows", "mobile": False, "brands": [{"brand": "Chromium", "version": "146"}]}),
            ("uaDataHigh", {"platform": "Windows", "platformVersion": "19.0.0", "architecture": "arm", "bitness": "64", "uaFullVersion": "146.0.7680.177"}),
            ("timezone", "America/New_York"),
            ("screen", {"width": 1280, "height": 800, "colorDepth": 32}),
            ("storageEstimate", {"quota": 471633758, "usage": 0}),
            ("canvas2d", "5b67a74a"),
            ("webgl", {"unmaskedVendor": "Google Inc. (NVIDIA)", "unmaskedRenderer": "ANGLE (NVIDIA, RTX 4060)"}),
            ("audio", 124.043439),
            ("fonts", {"widths": {"Segoe UI": 292.0, "PingFang SC": 260.0}}),
            ("webrtc", []),
        ):
            if name in window_only and ctx in ("worker", "service_worker"):
                context_matrix[ctx][name] = "unsupported_context"
                metrics[f"{ctx}.{name}"] = {
                    "context": ctx,
                    "metric": name,
                    "determinism": "unsupported_context",
                    "status": "unsupported_context",
                    "reason": "unavailable in worker",
                    "values": ["unsupported_context"],
                    "canonical_value": None,
                }
            else:
                context_matrix[ctx][name] = "ok"
                metrics[f"{ctx}.{name}"] = {
                    "context": ctx,
                    "metric": name,
                    "determinism": "deterministic",
                    "status": "ok",
                    "values": [val, val, val],
                    "unique_values": [val],
                    "unique_count": 1,
                    "canonical_value": val,
                }

    tls_evidence = (
        {
            "status": "ok",
            "handshake_count": 4,
            "supported_versions": ["0x0304", "0x0303"],
            "alpn": ["h2", "http/1.1"],
            "ja4_distribution": {
                "n": 4,
                "unique_count": 2,
                "unique_values": [
                    "t13d1516h2_8daaf6152771_d8a2da3f94cd",
                    "t13d1517h2_8daaf6152771_b6f405a00624",
                ],
                "counts": {
                    "t13d1516h2_8daaf6152771_d8a2da3f94cd": 1,
                    "t13d1517h2_8daaf6152771_b6f405a00624": 3,
                },
            },
            "ja3_sorted_distribution": {
                "n": 4,
                "unique_count": 2,
                "unique_values": ["sorted_a", "sorted_b"],
                "counts": {"sorted_a": 1, "sorted_b": 3},
            },
            "ja3_raw_distribution": {
                "n": 4,
                "unique_count": 4,
                "unique_values": ["h1", "h2", "h3", "h4"],
                "note": "BoringSSL shuffles TLS extension order per handshake",
            },
        }
        if tls_available
        else {"status": "inconclusive", "reason": "tls_capture_unavailable"}
    )

    return {
        "schema": "cbrowser-fingerprint-report/v1",
        "probe_version": "cbrowser-fp-probe/v1",
        "profile": {
            "profile_id": "prof-001",
            "config_version": 1,
            "config_summary": {
                "fingerprint_platform": "windows",
                "font_set_id": "71e2df2b",
                "locale": "en-US",
                "timezone": "America/New_York",
                "screen_width": 1280,
                "screen_height": 800,
                "fingerprint_seed": 290029,
            },
        },
        "engine_artifact": {
            "engine_build": engine_build,
            "platform_tag": "linux-arm64",
            "chromium_version": "146.0.7680.177",
            "binary_sha256": "3cf5231598c4fd44be1ed10c58cab4a1d59cd18b05a4800c73b946e0bfc4d34f",
            "archive_sha256": "8b71ce53b4fd131327331a31fba3835d71882d19bfaabde78dd0f5390bd16f45",
            "cloakbrowser_package": "0.6.4",
            "approved": True,
        },
        "collection_context": {
            "execution_mode": "docker_container_runtime",
            "scheme": "https" if tls_available else "http",
            "tls_capture_available": tls_available,
            "sample_count": 3,
        },
        "context_matrix": context_matrix,
        "metrics": metrics,
        "http_headers": {
            "main_after_ch": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "sec-ch-ua-platform": '"Windows"',
                "sec-ch-ua-platform-version": '"19.0.0"',
                "sec-ch-ua-arch": '"arm"',
                "sec-ch-ua-bitness": '"64"',
            },
            "worker_fetch": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
        },
        "tls_evidence": tls_evidence,
    }


def test_tls_client_hello_parser_handles_grease_and_extension_shuffle() -> None:
    from cbrowser.fingerprint_verification.tls_capture import parse_tls_client_hello

    # GREASE cipher 0x2a2a + TLS 1.3 ciphers, GREASE ext 0x4a4a + alpn + supported_versions + groups + sig_algs
    alpn_list = b"\x02h2\x08http/1.1"
    alpn_payload = struct.pack("!H", len(alpn_list)) + alpn_list
    sv_payload = b"\x04\x03\x04\x03\x03"
    groups_payload = struct.pack("!HHH", 4, 0x11EC, 0x001D)
    sig_payload = struct.pack("!HHH", 4, 0x0403, 0x0804)
    exts_a = [
        (0x4A4A, b""),
        (0x0010, alpn_payload),
        (0x002B, sv_payload),
        (0x000A, groups_payload),
        (0x000D, sig_payload),
    ]
    exts_b = [
        (0x000D, sig_payload),
        (0x000A, groups_payload),
        (0x7A7A, b""),
        (0x002B, sv_payload),
        (0x0010, alpn_payload),
    ]
    hello_a = parse_tls_client_hello(
        _build_tls_client_hello(ciphers=[0x2A2A, 0x1301, 0x1302], extensions=exts_a, sni="localhost")
    )
    hello_b = parse_tls_client_hello(
        _build_tls_client_hello(ciphers=[0x9A9A, 0x1301, 0x1302], extensions=exts_b, sni="localhost")
    )
    assert hello_a is not None and hello_b is not None
    # Shuffled extension order changes raw JA3, while JA4 and sorted JA3 remain identical
    assert hello_a["ja3"] != hello_b["ja3"]
    assert hello_a["ja4"] == hello_b["ja4"]
    assert hello_a["ja3_sorted"] == hello_b["ja3_sorted"]
    assert hello_a["ja4"].startswith("t13d0205h2_")


def test_comparator_blocks_missing_drift_nondeterminism_and_distinguishes_unsupported() -> None:
    from cbrowser.fingerprint_verification.comparator import compare_reports

    base = _base_report()
    cand = copy.deepcopy(base)

    # Identical deterministic metrics + unsupported_context preserved:
    # Under strict default (no approved normalization for stochastic ja3_raw), non-deterministic
    # ja3_raw blocks unless explicitly normalized via approved rule.
    strict_res = compare_reports(base, cand)
    assert strict_res["upgrade_decision"] == "blocked"
    assert any(d["classification"] == "non_deterministic_variance" for d in strict_res["diffs"])

    # With explicit BoringSSL shuffle rule, identical reports approve and unsupported_context stays distinct
    approved_res = compare_reports(
        base, cand, approved_rules={"tls_extension_shuffle_via_ja4": True}
    )
    assert approved_res["upgrade_decision"] == "approved"
    assert approved_res["summary"]["expected_unsupported_context"] == 10  # 5 apis x 2 worker contexts
    assert approved_res["summary"]["missing_count"] == 0

    # 1) Missing measurement MUST NOT be treated as no drift -> BLOCKED
    cand_missing = copy.deepcopy(base)
    cand_missing["metrics"]["service_worker.webgl"] = {
        "context": "service_worker",
        "metric": "webgl",
        "determinism": "missing",
        "status": "error",
        "reason": "sw timed out",
        "values": [],
        "canonical_value": None,
    }
    res_missing = compare_reports(
        base, cand_missing, approved_rules={"tls_extension_shuffle_via_ja4": True}
    )
    assert res_missing["upgrade_decision"] == "blocked"
    assert any(
        d["classification"] == "missing_measurement"
        and d["context"] == "service_worker"
        and d["field"] == "webgl"
        for d in res_missing["diffs"]
    )

    # 2) Deterministic API drift -> locatable diff & BLOCKED
    cand_drift = copy.deepcopy(base)
    cand_drift["metrics"]["main.webgl"]["canonical_value"]["unmaskedRenderer"] = "ANGLE (Intel)"
    cand_drift["metrics"]["main.webgl"]["unique_values"] = [
        cand_drift["metrics"]["main.webgl"]["canonical_value"]
    ]
    res_drift = compare_reports(
        base, cand_drift, approved_rules={"tls_extension_shuffle_via_ja4": True}
    )
    assert res_drift["upgrade_decision"] == "blocked"
    assert any(
        d["classification"] == "unapproved_drift"
        and d["context"] == "main"
        and d["field"] == "webgl"
        for d in res_drift["diffs"]
    )

    # 3) Context support flip (unsupported_context -> ok) -> BLOCKED
    cand_ctx = copy.deepcopy(base)
    cand_ctx["metrics"]["worker.audio"] = {
        "context": "worker",
        "metric": "audio",
        "determinism": "deterministic",
        "status": "ok",
        "values": [1.0, 1.0, 1.0],
        "unique_values": [1.0],
        "unique_count": 1,
        "canonical_value": 1.0,
    }
    res_ctx = compare_reports(
        base, cand_ctx, approved_rules={"tls_extension_shuffle_via_ja4": True}
    )
    assert res_ctx["upgrade_decision"] == "blocked"
    assert any(d["classification"] == "context_support_changed" for d in res_ctx["diffs"])


def test_consistency_binds_metadata_and_marks_unavailable_tls_inconclusive() -> None:
    from cbrowser.fingerprint_verification.consistency import evaluate_tls_ua_ch_consistency

    report_with_tls = _base_report(tls_available=True)
    ok_res = evaluate_tls_ua_ch_consistency(report_with_tls)
    assert ok_res["verdict"] == "consistent"
    assert ok_res["bound_identity"]["engine_build"] == "146.0.7680.177.3"
    assert ok_res["bound_identity"]["config_version"] == 1
    assert ok_res["bound_identity"]["probe_version"] == "cbrowser-fp-probe/v1"

    report_no_tls = _base_report(tls_available=False)
    inc_res = evaluate_tls_ua_ch_consistency(report_no_tls)
    assert inc_res["verdict"] == "inconclusive"
    assert inc_res["tls_status"] == "inconclusive"

    report_mismatch = _base_report(tls_available=True)
    report_mismatch["http_headers"]["main_after_ch"]["sec-ch-ua-platform"] = '"Linux"'
    bad_res = evaluate_tls_ua_ch_consistency(report_mismatch)
    assert bad_res["verdict"] == "inconsistent"


def test_tls_observing_probe_server_captures_real_handshake() -> None:
    """The HTTPS server must actually parse a ClientHello (regression for socket import)."""
    import socket
    import ssl

    from cbrowser.fingerprint_verification.tls_capture import TLSObservingProbeServer

    with TLSObservingProbeServer(use_tls=True) as server:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_alpn_protocols(["http/1.1"])
        with socket.create_connection(("127.0.0.1", server.port), timeout=5) as raw:
            with ctx.wrap_socket(raw, server_hostname="localhost") as tls:
                tls.sendall(
                    b"GET /main-fetch HTTP/1.1\r\nHost: localhost\r\n"
                    b"Connection: close\r\n\r\n"
                )
                tls.recv(4096)
    assert server.tls_records, "no TLS handshake captured by the probe server"
    hello = server.tls_records[0]["client_hello"]
    assert hello is not None
    assert hello["ja4"].startswith("t")
    assert hello["ja3_sorted"]
    assert server.http_records, "no HTTP request captured"


def test_render_diff_markdown_is_locatable() -> None:
    from cbrowser.fingerprint_verification.comparator import (
        compare_reports,
        render_diff_markdown,
    )

    base = _base_report()
    cand = copy.deepcopy(base)
    cand["metrics"]["main.webgl"]["canonical_value"]["unmaskedRenderer"] = "ANGLE (Intel)"
    diff = compare_reports(base, cand)
    text = render_diff_markdown(diff)
    assert "Upgrade Decision" in text
    assert "blocked" in text
    assert "main.webgl" in text or "webgl" in text
    assert "unapproved_drift" in text


def _make_probe_sample(
    *,
    main_headers: dict[str, str] | None = None,
    include_main_after_ch: bool = True,
    canvas_val: str = "5b67a74a",
    audio_val: float | str = 124.043439,
    worker_ua: str | None = None,
) -> dict:
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    window_only = {"webdriver", "pdfViewerEnabled", "screen", "audio", "webrtc"}
    contexts = {}
    for ctx in ("main", "iframe", "worker", "service_worker"):
        metrics = {}
        for name, val in (
            ("userAgent", worker_ua if (ctx == "worker" and worker_ua is not None) else ua),
            ("platform", "Win32"),
            ("language", "en-US"),
            ("languages", ["en-US"]),
            ("hardwareConcurrency", 8),
            ("deviceMemory", 8),
            ("webdriver", False),
            ("pdfViewerEnabled", True),
            ("uaDataLow", {"platform": "Windows", "mobile": False}),
            ("uaDataHigh", {"platform": "Windows", "platformVersion": "19.0.0"}),
            ("timezone", "America/New_York"),
            ("screen", {"width": 1280, "height": 800}),
            ("storageEstimate", {"quota": 471633758, "usage": 0}),
            ("canvas2d", canvas_val),
            ("webgl", {"unmaskedVendor": "NVIDIA"}),
            ("audio", audio_val),
            ("fonts", {"widths": {"Segoe UI": 292.0}}),
            ("webrtc", []),
        ):
            if name in window_only and ctx in ("worker", "service_worker"):
                metrics[name] = {"status": "unsupported_context", "reason": "worker"}
            elif name == "audio" and val == "error":
                metrics[name] = {"status": "error", "error": "audio timeout"}
            else:
                metrics[name] = {"status": "ok", "value": val}
        contexts[ctx] = {"context": ctx, "status": "ok", "metrics": metrics}

    http_hdrs = {
        "worker_fetch": {"user-agent": ua, "accept-language": "en-US,en;q=0.9"},
    }
    if include_main_after_ch:
        http_hdrs["main_after_ch"] = dict(
            main_headers
            or {
                "user-agent": ua,
                "accept-language": "en-US,en;q=0.9",
                "sec-ch-ua-platform": '"Windows"',
                "sec-ch-ua-platform-version": '"19.0.0"',
            }
        )

    alpn_list = b"\x02h2\x08http/1.1"
    alpn_payload = struct.pack("!H", len(alpn_list)) + alpn_list
    from cbrowser.fingerprint_verification.tls_capture import parse_tls_client_hello

    ch = parse_tls_client_hello(
        _build_tls_client_hello(
            ciphers=[0x1301, 0x1302],
            extensions=[
                (0x0010, alpn_payload),
                (0x002B, b"\x04\x03\x04\x03\x03"),
                (0x000A, struct.pack("!HHH", 4, 0x11EC, 0x001D)),
                (0x000D, struct.pack("!HHH", 4, 0x0403, 0x0804)),
            ],
            sni="localhost",
        )
    )
    return {
        "contexts": contexts,
        "http_headers": http_hdrs,
        "tls_handshakes": [{"client_hello": ch}],
    }


def test_aggregate_samples_catches_partial_http_missing_header_variance_and_js_states() -> None:
    from cbrowser.domain.models import ProfileConfig
    from cbrowser.fingerprint_verification.comparator import compare_reports
    from cbrowser.fingerprint_verification.probe_collector import aggregate_samples

    cfg = ProfileConfig(name="p-agg", fingerprint_platform="windows", fingerprint_seed=290029)
    engine_art = {
        "engine_build": "146.0.7680.177.3",
        "binary_sha256": "3cf5231598c4fd44be1ed10c58cab4a1d59cd18b05a4800c73b946e0bfc4d34f",
        "approved": True,
    }

    base_rep = aggregate_samples(
        profile_id="p-agg",
        config_version=1,
        config=cfg,
        engine_artifact=engine_art,
        samples=[_make_probe_sample(), _make_probe_sample()],
        execution_mode="unit",
        scheme="https",
        tls_capture_available=True,
    )
    assert base_rep["consistency"]["verdict"] == "consistent"
    assert base_rep["http_header_samples"]["main_after_ch"]["status"] == "ok"
    assert base_rep["http_header_samples"]["main_after_ch"]["determinism"] == "deterministic"

    # 1) Partial HTTP missing in sample 0 -> must block & mark inconclusive (t068_code_f001)
    partial_missing = aggregate_samples(
        profile_id="p-agg",
        config_version=1,
        config=cfg,
        engine_artifact=engine_art,
        samples=[_make_probe_sample(include_main_after_ch=False), _make_probe_sample()],
        execution_mode="unit",
        scheme="https",
        tls_capture_available=True,
    )
    assert partial_missing["http_header_samples"]["main_after_ch"]["status"] == "missing"
    assert partial_missing["http_header_samples"]["main_after_ch"]["missing_sample_indices"] == [0]
    assert "main_after_ch" not in partial_missing["http_headers"]
    assert partial_missing["consistency"]["verdict"] == "inconclusive"
    res_partial = compare_reports(
        base_rep, partial_missing, approved_rules={"tls_extension_shuffle_via_ja4": True}
    )
    assert res_partial["upgrade_decision"] == "blocked"
    assert "missing_measurement:http.main_after_ch" in res_partial["blocking_reasons"]

    # 2) Sample-to-sample HTTP header drift -> must block as non_deterministic_variance (t068_code_f001)
    drifted_hdrs = dict(_make_probe_sample()["http_headers"]["main_after_ch"])
    drifted_hdrs["sec-ch-ua-platform"] = '"Linux"'
    hdr_variance = aggregate_samples(
        profile_id="p-agg",
        config_version=1,
        config=cfg,
        engine_artifact=engine_art,
        samples=[_make_probe_sample(main_headers=drifted_hdrs), _make_probe_sample()],
        execution_mode="unit",
        scheme="https",
        tls_capture_available=True,
    )
    assert hdr_variance["http_header_samples"]["main_after_ch"]["determinism"] == "non_deterministic"
    assert hdr_variance["http_header_samples"]["main_after_ch"]["unique_count"] == 2
    assert hdr_variance["consistency"]["verdict"] == "inconsistent"
    res_hdr_var = compare_reports(
        base_rep, hdr_variance, approved_rules={"tls_extension_shuffle_via_ja4": True}
    )
    assert res_hdr_var["upgrade_decision"] == "blocked"
    assert "non_deterministic_variance:http.main_after_ch" in res_hdr_var["blocking_reasons"]

    # 3) Single-sample JS error -> determinism="missing"; numeric JS variance -> min/max
    js_mix = aggregate_samples(
        profile_id="p-agg",
        config_version=1,
        config=cfg,
        engine_artifact=engine_art,
        samples=[
            _make_probe_sample(audio_val="error", canvas_val="aaa"),
            _make_probe_sample(audio_val=1.5, canvas_val="bbb"),
        ],
        execution_mode="unit",
        scheme="https",
        tls_capture_available=True,
    )
    assert js_mix["metrics"]["main.audio"]["determinism"] == "missing"
    assert js_mix["metrics"]["main.canvas2d"]["determinism"] == "non_deterministic"
    assert js_mix["metrics"]["main.canvas2d"]["unique_count"] == 2

    js_num = aggregate_samples(
        profile_id="p-agg",
        config_version=1,
        config=cfg,
        engine_artifact=engine_art,
        samples=[_make_probe_sample(audio_val=10.5), _make_probe_sample(audio_val=12.0)],
        execution_mode="unit",
        scheme="https",
        tls_capture_available=True,
    )
    assert js_num["metrics"]["main.audio"]["determinism"] == "non_deterministic"
    assert js_num["metrics"]["main.audio"]["min"] == 10.5
    assert js_num["metrics"]["main.audio"]["max"] == 12.0


def test_comparator_edge_cases_empty_metrics_http_font_and_storage_quota() -> None:
    from cbrowser.fingerprint_verification.comparator import compare_reports

    base = _base_report()

    # Empty metrics guard (t068_code_f004)
    empty_b = copy.deepcopy(base)
    empty_c = copy.deepcopy(base)
    empty_b["metrics"] = {}
    empty_c["metrics"] = {}
    res_empty = compare_reports(
        empty_b, empty_c, approved_rules={"tls_extension_shuffle_via_ja4": True}
    )
    assert res_empty["upgrade_decision"] == "blocked"
    assert res_empty["summary"]["missing_count"] >= 72

    # HTTP header drift across reports
    cand_http = copy.deepcopy(base)
    cand_http["http_headers"]["worker_fetch"]["accept-language"] = "fr-FR"
    res_http = compare_reports(
        base, cand_http, approved_rules={"tls_extension_shuffle_via_ja4": True}
    )
    assert res_http["upgrade_decision"] == "blocked"
    assert "unapproved_drift:http.worker_fetch" in res_http["blocking_reasons"]

    # Font evidence missing and drift
    base_font = copy.deepcopy(base)
    base_font["font_evidence"] = {"fc_list": {"linux_font_hits": 0, "families": ["Segoe UI"]}}
    cand_font_missing = copy.deepcopy(base)
    res_font_miss = compare_reports(
        base_font, cand_font_missing, approved_rules={"tls_extension_shuffle_via_ja4": True}
    )
    assert res_font_miss["upgrade_decision"] == "blocked"
    assert "missing_measurement:font_evidence" in res_font_miss["blocking_reasons"]

    cand_font_drift = copy.deepcopy(base_font)
    cand_font_drift["font_evidence"]["fc_list"]["families"] = ["Liberation Sans"]
    res_font_drift = compare_reports(
        base_font, cand_font_drift, approved_rules={"tls_extension_shuffle_via_ja4": True}
    )
    assert res_font_drift["upgrade_decision"] == "blocked"
    assert "unapproved_drift:font_evidence" in res_font_drift["blocking_reasons"]

    # ignore_stateful_storage_usage approves identical quota, blocks changed quota
    cand_usage = copy.deepcopy(base)
    cand_usage["metrics"]["main.storageEstimate"] = {
        "context": "main",
        "metric": "storageEstimate",
        "status": "ok",
        "determinism": "non_deterministic",
        "values": [{"quota": 471633758, "usage": 0}, {"quota": 471633758, "usage": 8489}],
        "unique_values": [{"quota": 471633758, "usage": 0}, {"quota": 471633758, "usage": 8489}],
        "unique_count": 2,
        "canonical_value": None,
    }
    res_usage_ok = compare_reports(
        base,
        cand_usage,
        approved_rules={
            "tls_extension_shuffle_via_ja4": True,
            "ignore_stateful_storage_usage": True,
        },
    )
    assert res_usage_ok["upgrade_decision"] == "approved"

    cand_quota = copy.deepcopy(cand_usage)
    cand_quota["metrics"]["main.storageEstimate"]["unique_values"][1]["quota"] = 999999
    res_quota_bad = compare_reports(
        base,
        cand_quota,
        approved_rules={
            "tls_extension_shuffle_via_ja4": True,
            "ignore_stateful_storage_usage": True,
        },
    )
    assert res_quota_bad["upgrade_decision"] == "blocked"
    assert "non_deterministic_variance:main.storageEstimate" in res_quota_bad["blocking_reasons"]


def test_consistency_missing_vs_inconsistent_and_cross_context_checks() -> None:
    from cbrowser.fingerprint_verification.consistency import evaluate_tls_ua_ch_consistency

    # Missing platform/uaDataLow should yield inconclusive (status="missing"), not inconsistent
    rep_miss = _base_report(tls_available=True)
    rep_miss["metrics"]["iframe.platform"] = {"status": "error", "canonical_value": None}
    res_miss = evaluate_tls_ua_ch_consistency(rep_miss)
    assert res_miss["verdict"] == "inconclusive"
    assert any(f["status"] == "missing" and "iframe.platform" in f["detail"] for f in res_miss["findings"])

    # Cross-context worker userAgent mismatch -> inconsistent
    rep_ctx = _base_report(tls_available=True)
    rep_ctx["metrics"]["worker.userAgent"]["canonical_value"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/99.0.0.0 Safari/537.36"
    )
    res_ctx = evaluate_tls_ua_ch_consistency(rep_ctx)
    assert res_ctx["verdict"] == "inconsistent"
    assert any(f["layer"] == "js.cross_context" for f in res_ctx["findings"])

    # Secondary HTTP worker_fetch User-Agent mismatch -> inconsistent
    rep_wf = _base_report(tls_available=True)
    rep_wf["http_headers"]["worker_fetch"]["User-Agent"] = "WrongAgent"
    res_wf = evaluate_tls_ua_ch_consistency(rep_wf)
    assert res_wf["verdict"] == "inconsistent"
    assert any(f["layer"] == "http.worker_fetch" for f in res_wf["findings"])


def test_parse_tls_client_hello_rejects_odd_lengths_and_truncated_extensions() -> None:
    from cbrowser.fingerprint_verification.tls_capture import parse_tls_client_hello

    valid = _build_tls_client_hello(
        ciphers=[0x1301, 0x1302],
        extensions=[
            (0x000A, struct.pack("!HHH", 4, 0x11EC, 0x001D)),
            (0x000D, struct.pack("!HHH", 4, 0x0403, 0x0804)),
            (0x002B, b"\x04\x03\x04\x03\x03"),
        ],
    )
    assert parse_tls_client_hello(valid) is not None
    # Truncated record
    assert parse_tls_client_hello(valid[:-3]) is None

    # Odd cipher suite byte length
    hs_odd_cs = bytearray()
    hs_odd_cs += struct.pack("!H", 0x0303) + b"\x11" * 32 + b"\x00" + struct.pack("!H", 3) + b"\x13\x01\x00" + b"\x01\x00"
    hs_rec = bytes([0x01]) + len(hs_odd_cs).to_bytes(3, "big") + bytes(hs_odd_cs)
    assert parse_tls_client_hello(struct.pack("!BHH", 0x16, 0x0301, len(hs_rec)) + hs_rec) is None

    # Odd supported_groups internal length & truncated extension header length
    assert parse_tls_client_hello(_build_tls_client_hello(ciphers=[0x1301], extensions=[(0x000A, struct.pack("!H", 3) + b"\x11\xec\x00")])) is None
    assert parse_tls_client_hello(_build_tls_client_hello(ciphers=[0x1301], extensions=[(0x000D, struct.pack("!H", 3) + b"\x04\x03\x08")])) is None
    assert parse_tls_client_hello(_build_tls_client_hello(ciphers=[0x1301], extensions=[(0x002B, b"\x03\x03\x04\x03")])) is None

    # Zero-length ALPN entry (RFC 7301 requires >= 1 byte) -> None, and _alpn_tag handles empty string safely
    from cbrowser.fingerprint_verification.tls_capture import _alpn_tag

    assert _alpn_tag([""]) == "00"
    assert parse_tls_client_hello(_build_tls_client_hello(ciphers=[0x1301], extensions=[(0x0010, b"\x00\x01\x00")])) is None
