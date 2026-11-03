"""Stage metrics accumulate bounded durations and counts."""

from cbrowser.supervisor.metrics import StageMetrics


def test_stage_metrics_counts_and_reports() -> None:
    metrics = StageMetrics(report_interval_sec=60.0)
    metrics.record("scan", 0.2)
    metrics.record("scan", 0.4)
    metrics.record("events", 0.01)

    assert not metrics.should_report(now=0.0)
    snapshot = metrics.snapshot(now=100.0)
    assert snapshot["scan"]["cumulative_count"] == 2
    assert snapshot["scan"]["cumulative_total_ms"] == 600.0
    assert snapshot["scan"]["cumulative_max_ms"] == 400.0
    assert snapshot["scan"]["interval_count"] == 2
    assert snapshot["scan"]["interval_total_ms"] == 600.0
    assert snapshot["scan"]["interval_max_ms"] == 400.0
    assert snapshot["events"]["cumulative_count"] == 1

    metrics.record("scan", 0.1)
    next_snapshot = metrics.snapshot(now=200.0)
    assert next_snapshot["scan"]["cumulative_count"] == 3
    assert next_snapshot["scan"]["cumulative_total_ms"] == 700.0
    assert next_snapshot["scan"]["interval_count"] == 1
    assert next_snapshot["scan"]["interval_total_ms"] == 100.0
    assert next_snapshot["scan"]["interval_max_ms"] == 100.0
    assert next_snapshot["events"]["interval_count"] == 0
