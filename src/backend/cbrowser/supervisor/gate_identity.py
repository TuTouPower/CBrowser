"""Optional local verification ownership propagated by the gate harness."""

from __future__ import annotations

import os


def gate_labels(labels: dict[str, str]) -> dict[str, str]:
    run_id = os.environ.get("CBROWSER_GATE_RUN_ID")
    if not run_id:
        return labels
    return {**labels, "com.cbrowser.gate-run": run_id}
