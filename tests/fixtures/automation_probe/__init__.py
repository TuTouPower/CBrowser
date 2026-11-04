"""Automation compatibility probe harness (t029).

Delivers the reusable probe used by t030 design input and t032 target
environment re-verification.  Everything here is test tooling: it never
becomes a production driver and it never talks to a bare CDP TCP port of
a managed Profile except through the authenticated cbat_ tunnel (chain
mode) or a loopback DevTools endpoint of a browser process the probe
itself launched (direct mode).
"""

from .harness import (
    CLOAKBROWSER_PACKAGE_VERSION,
    EGO_LITE_BASELINE_COMMIT,
    PLAYWRIGHT_VERSION,
    TARGET_ENGINE_VERSION,
    CdpBridge,
    ObservationServer,
    ProbePrerequisiteMissing,
    XTestInput,
    build_report,
    classify_cdp_method,
    compare_level_samples,
    redact_report_value,
    summarize_levels,
)

__all__ = [
    "CLOAKBROWSER_PACKAGE_VERSION",
    "EGO_LITE_BASELINE_COMMIT",
    "PLAYWRIGHT_VERSION",
    "TARGET_ENGINE_VERSION",
    "CdpBridge",
    "ObservationServer",
    "ProbePrerequisiteMissing",
    "XTestInput",
    "build_report",
    "classify_cdp_method",
    "compare_level_samples",
    "redact_report_value",
    "summarize_levels",
]
