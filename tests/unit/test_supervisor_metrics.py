"""Stage metrics accumulate bounded durations and counts."""

from cbrowser.supervisor.metrics import StageMetrics


def test_stage_metrics_counts_and_reports() -> None:
    metrics = StageMetrics(report_interval_sec=60.0)
    metrics.record("scan", 0.2)
    metrics.record("scan", 0.4)
    metrics.record("events", 0.01)

    assert not metrics.should_report(now=0.0)
    snapshot = metrics.snapshot(now=100.0)
    assert snapshot["scan"]["count"] == 2
    assert snapshot["scan"]["total_ms"] == 600.0
    assert snapshot["scan"]["max_ms"] == 400.0
    assert snapshot["events"]["count"] == 1
