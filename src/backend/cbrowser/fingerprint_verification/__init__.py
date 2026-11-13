"""Local fingerprint baseline, 4-context probe, TLS JA3/JA4 capture & upgrade diff gate."""

from cbrowser.fingerprint_verification.comparator import (
    compare_reports,
    render_diff_markdown,
)
from cbrowser.fingerprint_verification.consistency import (
    evaluate_tls_ua_ch_consistency,
)
from cbrowser.fingerprint_verification.probe_collector import (
    ALL_CONTEXTS,
    ALL_METRICS,
    PROBE_VERSION,
    REPORT_SCHEMA,
    WINDOW_ONLY_METRICS,
    aggregate_samples,
)
from cbrowser.fingerprint_verification.tls_capture import (
    TLSObservingProbeServer,
    parse_tls_client_hello,
)

__all__ = [
    "ALL_CONTEXTS",
    "ALL_METRICS",
    "PROBE_VERSION",
    "REPORT_SCHEMA",
    "TLSObservingProbeServer",
    "WINDOW_ONLY_METRICS",
    "aggregate_samples",
    "compare_reports",
    "evaluate_tls_ua_ch_consistency",
    "parse_tls_client_hello",
    "render_diff_markdown",
]
