"""AC-001 / AC-002: Diff engine and strict upgrade regression gate."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .probe_collector import ALL_CONTEXTS, ALL_METRICS

EXPECTED_METRIC_KEYS: tuple[str, ...] = tuple(
    f"{ctx}.{metric}" for ctx in ALL_CONTEXTS for metric in ALL_METRICS
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _http_summary_for_diff(report: Mapping[str, Any], req_cls: str) -> dict[str, Any]:
    hdr_samples = report.get("http_header_samples") or {}
    entry = hdr_samples.get(req_cls)
    if isinstance(entry, dict):
        return {
            "status": entry.get("status", "missing"),
            "determinism": entry.get("determinism", "missing"),
            "canonical_value": entry.get("canonical_value"),
            "unique_values": entry.get("unique_values"),
            "unique_count": entry.get("unique_count"),
            "values": entry.get("values"),
            "missing_sample_indices": entry.get("missing_sample_indices"),
        }
    hdrs = (report.get("http_headers") or {}).get(req_cls)
    if isinstance(hdrs, dict):
        return {
            "status": "ok",
            "determinism": "deterministic",
            "canonical_value": hdrs,
            "unique_values": [hdrs],
            "unique_count": 1,
            "values": [hdrs],
            "missing_sample_indices": [],
        }
    return {
        "status": "missing",
        "determinism": "missing",
        "canonical_value": None,
    }


def _metric_summary_for_diff(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {"status": "missing", "determinism": "missing"}
    return {
        "status": entry.get("status", "missing"),
        "determinism": entry.get("determinism", "missing"),
        "canonical_value": entry.get("canonical_value"),
        "unique_values": entry.get("unique_values"),
        "unique_count": entry.get("unique_count"),
        "values": entry.get("values"),
        "min": entry.get("min"),
        "max": entry.get("max"),
        "reason": entry.get("reason") or entry.get("error"),
    }


def compare_reports(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    approved_rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare baseline and candidate fingerprint reports and enforce fail-closed upgrade gating."""
    rules = dict(approved_rules or {})
    diffs: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    non_deterministic_distributions: list[dict[str, Any]] = []
    context_matrix_diff: dict[str, dict[str, Any]] = {}

    base_prof = baseline.get("profile") or {}
    cand_prof = candidate.get("profile") or {}
    if (
        base_prof.get("profile_id") != cand_prof.get("profile_id")
        or base_prof.get("config_version") != cand_prof.get("config_version")
    ):
        reason = (
            f"identity_mismatch: baseline ({base_prof.get('profile_id')}, v{base_prof.get('config_version')}) "
            f"!= candidate ({cand_prof.get('profile_id')}, v{cand_prof.get('config_version')})"
        )
        blocking_reasons.append(reason)
        diffs.append({
            "layer": "profile",
            "context": "identity",
            "field": "profile_id/config_version",
            "classification": "identity_mismatch",
            "baseline_value": {
                "profile_id": base_prof.get("profile_id"),
                "config_version": base_prof.get("config_version"),
            },
            "candidate_value": {
                "profile_id": cand_prof.get("profile_id"),
                "config_version": cand_prof.get("config_version"),
            },
            "blocking": True,
            "remediation": "Re-run both baseline and candidate probes against the same profile_id and config_version.",
        })

    base_eng = baseline.get("engine_artifact") or {}
    cand_eng = candidate.get("engine_artifact") or {}
    for side_name, eng in (("baseline", base_eng), ("candidate", cand_eng)):
        if not eng.get("approved") or not eng.get("engine_build"):
            reason = f"unapproved_engine_artifact:{side_name}"
            blocking_reasons.append(reason)
            diffs.append({
                "layer": "engine_artifact",
                "context": side_name,
                "field": "engine_artifact",
                "classification": "unapproved_engine_artifact",
                "baseline_value": base_eng if side_name == "baseline" else None,
                "candidate_value": cand_eng if side_name == "candidate" else None,
                "blocking": True,
                "remediation": f"Use an approved ADR 021 engine artifact for {side_name}.",
            })

    # 1. Context applicability matrix & per-(context, metric) comparison
    base_metrics = baseline.get("metrics") or {}
    cand_metrics = candidate.get("metrics") or {}
    all_keys = sorted(set(EXPECTED_METRIC_KEYS) | set(base_metrics) | set(cand_metrics))

    expected_unsupported = 0
    missing_count = 0
    matched_deterministic = 0

    for key in all_keys:
        b = _metric_summary_for_diff(base_metrics.get(key))
        c = _metric_summary_for_diff(cand_metrics.get(key))
        ctx_name, _, metric_name = key.partition(".")
        if not metric_name:
            ctx_name, metric_name = "unknown", key

        context_matrix_diff.setdefault(ctx_name, {})[metric_name] = {
            "baseline_status": b["status"],
            "candidate_status": c["status"],
        }

        if b["status"] == "unsupported_context" and c["status"] == "unsupported_context":
            expected_unsupported += 1
            continue

        if (b["status"] == "unsupported_context") != (c["status"] == "unsupported_context"):
            diffs.append({
                "layer": "js_api",
                "context": ctx_name,
                "field": metric_name,
                "classification": "context_support_changed",
                "baseline_value": b,
                "candidate_value": c,
                "blocking": True,
                "remediation": f"Block upgrade: context support changed for {ctx_name}.{metric_name}.",
            })
            blocking_reasons.append(f"context_support_changed:{key}")
            continue

        if b["status"] != "ok" or c["status"] != "ok":
            missing_count += 1
            diffs.append({
                "layer": "js_api",
                "context": ctx_name,
                "field": metric_name,
                "classification": "missing_measurement",
                "baseline_value": b,
                "candidate_value": c,
                "blocking": True,
                "remediation": f"Block upgrade: missing/failed measurement for {key}.",
            })
            blocking_reasons.append(f"missing_measurement:{key}")
            continue

        b_nondet = b["determinism"] == "non_deterministic" or (b.get("unique_count") or 1) > 1
        c_nondet = c["determinism"] == "non_deterministic" or (c.get("unique_count") or 1) > 1
        if b_nondet or c_nondet:
            dist_entry = {
                "layer": "js_api",
                "context": ctx_name,
                "field": metric_name,
                "baseline_distribution": {
                    "values": b.get("values"),
                    "unique_values": b.get("unique_values"),
                    "min": b.get("min"),
                    "max": b.get("max"),
                },
                "candidate_distribution": {
                    "values": c.get("values"),
                    "unique_values": c.get("unique_values"),
                    "min": c.get("min"),
                    "max": c.get("max"),
                },
            }
            non_deterministic_distributions.append(dist_entry)
            ignore_storage_usage = (
                metric_name == "storageEstimate"
                and bool(rules.get("ignore_stateful_storage_usage"))
            )
            if ignore_storage_usage:
                b_quotas = {
                    (v.get("quota") if isinstance(v, dict) else None)
                    for v in (b.get("unique_values") or [])
                }
                c_quotas = {
                    (v.get("quota") if isinstance(v, dict) else None)
                    for v in (c.get("unique_values") or [])
                }
                if b_quotas == c_quotas and None not in b_quotas:
                    matched_deterministic += 1
                    continue
            diffs.append({
                "layer": "js_api",
                "context": ctx_name,
                "field": metric_name,
                "classification": "non_deterministic_variance",
                "baseline_value": dist_entry["baseline_distribution"],
                "candidate_value": dist_entry["candidate_distribution"],
                "blocking": True,
                "remediation": f"Block upgrade: unapproved non-deterministic variance on {key}.",
            })
            blocking_reasons.append(f"non_deterministic_variance:{key}")
            continue

        if _canonical(b["canonical_value"]) != _canonical(c["canonical_value"]):
            diffs.append({
                "layer": "js_api",
                "context": ctx_name,
                "field": metric_name,
                "classification": "unapproved_drift",
                "baseline_value": b["canonical_value"],
                "candidate_value": c["canonical_value"],
                "blocking": True,
                "remediation": f"Block upgrade for profile {base_prof.get('profile_id')}: drift on {key}.",
            })
            blocking_reasons.append(f"unapproved_drift:{key}")
        else:
            matched_deterministic += 1

    # 2. HTTP request headers across request classes (completeness & sample determinism)
    base_hdrs = baseline.get("http_headers") or {}
    cand_hdrs = candidate.get("http_headers") or {}
    base_hdr_samples = baseline.get("http_header_samples") or {}
    cand_hdr_samples = candidate.get("http_header_samples") or {}
    all_req_classes = sorted(
        set(base_hdrs) | set(cand_hdrs) | set(base_hdr_samples) | set(cand_hdr_samples)
    )
    if not all_req_classes:
        missing_count += 1
        diffs.append({
            "layer": "http_header",
            "context": "http",
            "field": "http_headers",
            "classification": "missing_measurement",
            "baseline_value": base_hdrs or None,
            "candidate_value": cand_hdrs or None,
            "blocking": True,
            "remediation": "Block upgrade: HTTP header capture missing.",
        })
        blocking_reasons.append("missing_measurement:http_headers")
    else:
        for req_cls in all_req_classes:
            bh = _http_summary_for_diff(baseline, req_cls)
            ch = _http_summary_for_diff(candidate, req_cls)
            if bh["status"] != "ok" or ch["status"] != "ok":
                missing_count += 1
                diffs.append({
                    "layer": "http_header",
                    "context": f"http:{req_cls}",
                    "field": req_cls,
                    "classification": "missing_measurement",
                    "baseline_value": bh,
                    "candidate_value": ch,
                    "blocking": True,
                    "remediation": f"Block upgrade: HTTP request class {req_cls} missing/incomplete.",
                })
                blocking_reasons.append(f"missing_measurement:http.{req_cls}")
                continue
            b_nondet = bh["determinism"] == "non_deterministic" or (bh.get("unique_count") or 1) > 1
            c_nondet = ch["determinism"] == "non_deterministic" or (ch.get("unique_count") or 1) > 1
            if b_nondet or c_nondet:
                dist_entry = {
                    "layer": "http_header",
                    "context": f"http:{req_cls}",
                    "field": req_cls,
                    "baseline_distribution": {
                        "values": bh.get("values"),
                        "unique_values": bh.get("unique_values"),
                    },
                    "candidate_distribution": {
                        "values": ch.get("values"),
                        "unique_values": ch.get("unique_values"),
                    },
                }
                non_deterministic_distributions.append(dist_entry)
                diffs.append({
                    "layer": "http_header",
                    "context": f"http:{req_cls}",
                    "field": req_cls,
                    "classification": "non_deterministic_variance",
                    "baseline_value": dist_entry["baseline_distribution"],
                    "candidate_value": dist_entry["candidate_distribution"],
                    "blocking": True,
                    "remediation": f"Block upgrade: non-deterministic HTTP header variance on {req_cls}.",
                })
                blocking_reasons.append(f"non_deterministic_variance:http.{req_cls}")
                continue
            if _canonical(bh["canonical_value"]) != _canonical(ch["canonical_value"]):
                diffs.append({
                    "layer": "http_header",
                    "context": f"http:{req_cls}",
                    "field": req_cls,
                    "classification": "unapproved_drift",
                    "baseline_value": bh["canonical_value"],
                    "candidate_value": ch["canonical_value"],
                    "blocking": True,
                    "remediation": f"Block upgrade: HTTP headers drifted for {req_cls}.",
                })
                blocking_reasons.append(f"unapproved_drift:http.{req_cls}")

    # 3. TLS ClientHello / JA3 / JA4 evidence
    base_tls = baseline.get("tls_evidence") or {}
    cand_tls = candidate.get("tls_evidence") or {}
    if base_tls.get("status") != "ok" or cand_tls.get("status") != "ok":
        diffs.append({
            "layer": "tls",
            "context": "tls",
            "field": "tls_capture",
            "classification": "inconclusive",
            "baseline_value": base_tls,
            "candidate_value": cand_tls,
            "blocking": True,
            "remediation": "Block upgrade: TLS ClientHello capture unavailable/inconclusive.",
        })
        blocking_reasons.append("inconclusive:tls_capture")
    else:
        b_ja4 = sorted((base_tls.get("ja4_distribution") or {}).get("unique_values") or [])
        c_ja4 = sorted((cand_tls.get("ja4_distribution") or {}).get("unique_values") or [])
        non_deterministic_distributions.append({
            "layer": "tls",
            "context": "tls",
            "field": "ja4_distribution",
            "baseline_distribution": base_tls.get("ja4_distribution"),
            "candidate_distribution": cand_tls.get("ja4_distribution"),
        })
        if b_ja4 != c_ja4:
            diffs.append({
                "layer": "tls",
                "context": "tls",
                "field": "ja4_set",
                "classification": "unapproved_drift",
                "baseline_value": b_ja4,
                "candidate_value": c_ja4,
                "blocking": True,
                "remediation": "Block upgrade: TLS JA4 fingerprint set drifted.",
            })
            blocking_reasons.append("unapproved_drift:tls.ja4_set")

        b_ja3s = sorted((base_tls.get("ja3_sorted_distribution") or {}).get("unique_values") or [])
        c_ja3s = sorted((cand_tls.get("ja3_sorted_distribution") or {}).get("unique_values") or [])
        if b_ja3s != c_ja3s:
            diffs.append({
                "layer": "tls",
                "context": "tls",
                "field": "ja3_sorted_set",
                "classification": "unapproved_drift",
                "baseline_value": b_ja3s,
                "candidate_value": c_ja3s,
                "blocking": True,
                "remediation": "Block upgrade: TLS sorted-extension JA3 drifted.",
            })
            blocking_reasons.append("unapproved_drift:tls.ja3_sorted_set")

        b_ja3r = base_tls.get("ja3_raw_distribution") or {}
        c_ja3r = cand_tls.get("ja3_raw_distribution") or {}
        non_deterministic_distributions.append({
            "layer": "tls",
            "context": "tls",
            "field": "ja3_raw_distribution",
            "baseline_distribution": b_ja3r,
            "candidate_distribution": c_ja3r,
        })
        if not rules.get("tls_extension_shuffle_via_ja4"):
            if (
                (b_ja3r.get("unique_count") or 0) > 1
                or (c_ja3r.get("unique_count") or 0) > 1
                or sorted(b_ja3r.get("unique_values") or []) != sorted(c_ja3r.get("unique_values") or [])
            ):
                diffs.append({
                    "layer": "tls",
                    "context": "tls",
                    "field": "ja3_raw",
                    "classification": "non_deterministic_variance",
                    "baseline_value": b_ja3r,
                    "candidate_value": c_ja3r,
                    "blocking": True,
                    "remediation": (
                        "Block upgrade under strict default: raw JA3 varies per connection "
                        "(BoringSSL extension shuffle); requires explicit approval of "
                        "tls_extension_shuffle_via_ja4 normalization."
                    ),
                })
                blocking_reasons.append("non_deterministic_variance:tls.ja3_raw")

    # 4. Font evidence (when present on either side)
    base_fonts = baseline.get("font_evidence")
    cand_fonts = candidate.get("font_evidence")
    if base_fonts is not None or cand_fonts is not None:
        if base_fonts is None or cand_fonts is None:
            missing_count += 1
            diffs.append({
                "layer": "fontconfig",
                "context": "fontconfig",
                "field": "font_evidence",
                "classification": "missing_measurement",
                "baseline_value": base_fonts,
                "candidate_value": cand_fonts,
                "blocking": True,
                "remediation": "Block upgrade: fontconfig evidence missing on one side.",
            })
            blocking_reasons.append("missing_measurement:font_evidence")
        elif _canonical(base_fonts) != _canonical(cand_fonts):
            diffs.append({
                "layer": "fontconfig",
                "context": "fontconfig",
                "field": "font_evidence",
                "classification": "unapproved_drift",
                "baseline_value": base_fonts,
                "candidate_value": cand_fonts,
                "blocking": True,
                "remediation": "Block upgrade: fontconfig whitelist / OS font matching drifted.",
            })
            blocking_reasons.append("unapproved_drift:font_evidence")

    upgrade_decision = "blocked" if blocking_reasons or diffs else "approved"
    return {
        "schema": "cbrowser-fingerprint-diff/v1",
        "probe_version": baseline.get("probe_version"),
        "profile_id": base_prof.get("profile_id"),
        "config_version": base_prof.get("config_version"),
        "baseline_engine": base_eng,
        "candidate_engine": cand_eng,
        "approved_rules_applied": rules,
        "upgrade_decision": upgrade_decision,
        "blocking_reasons": sorted(set(blocking_reasons)),
        "summary": {
            "matched_deterministic": matched_deterministic,
            "expected_unsupported_context": expected_unsupported,
            "missing_count": missing_count,
            "diff_count": len(diffs),
            "non_deterministic_count": len(non_deterministic_distributions),
        },
        "context_matrix_diff": context_matrix_diff,
        "non_deterministic_distributions": non_deterministic_distributions,
        "diffs": diffs,
    }


def render_diff_markdown(diff_report: Mapping[str, Any]) -> str:
    """Render a concise, locatable Markdown diff report."""
    base_e = diff_report.get("baseline_engine") or {}
    cand_e = diff_report.get("candidate_engine") or {}
    summary = diff_report.get("summary") or {}
    lines = [
        f"# Fingerprint Upgrade Regression Diff ({diff_report.get('profile_id')} v{diff_report.get('config_version')})",
        "",
        f"- **Upgrade Decision**: `{diff_report.get('upgrade_decision')}`",
        f"- **Baseline Engine**: `{base_e.get('engine_build')}` (sha256: `{base_e.get('binary_sha256')}`)",
        f"- **Candidate Engine**: `{cand_e.get('engine_build')}` (sha256: `{cand_e.get('binary_sha256')}`)",
        f"- **Probe Version**: `{diff_report.get('probe_version')}`",
        f"- **Matched Deterministic**: {summary.get('matched_deterministic')} | **Expected Unsupported Context**: {summary.get('expected_unsupported_context')} | **Missing**: {summary.get('missing_count')} | **Diffs**: {summary.get('diff_count')}",
        "",
        "## Blocking Reasons",
        "",
    ]
    reasons = diff_report.get("blocking_reasons") or []
    if not reasons:
        lines.append("- None")
    else:
        for r in reasons:
            lines.append(f"- `{r}`")

    lines.extend(["", "## Locatable Diffs", ""])
    diffs = diff_report.get("diffs") or []
    if not diffs:
        lines.append("No diffs detected.")
    else:
        lines.append("|layer|context|field|classification|remediation|")
        lines.append("|---|---|---|---|---|")
        for d in diffs:
            lines.append(
                f"|{d.get('layer')}|{d.get('context')}|{d.get('field')}|{d.get('classification')}|{d.get('remediation')}|"
            )
    return "\n".join(lines) + "\n"
