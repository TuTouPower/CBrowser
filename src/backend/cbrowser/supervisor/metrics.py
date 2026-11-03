"""Bounded stage metrics for Supervisor loops (structured logging)."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class StageStats:
    count: int = 0
    total_seconds: float = 0.0
    max_seconds: float = 0.0


class StageMetrics:
    """Counts and durations per loop stage; cheap enough for every iteration."""

    def __init__(self, report_interval_sec: float = 60.0) -> None:
        self.report_interval_sec = report_interval_sec
        self._stats: dict[str, StageStats] = {}
        self._interval_stats: dict[str, StageStats] = {}
        self._last_report = time.monotonic()

    def record(self, name: str, seconds: float) -> None:
        for bucket in (self._stats, self._interval_stats):
            stats = bucket.setdefault(name, StageStats())
            stats.count += 1
            stats.total_seconds += seconds
            stats.max_seconds = max(stats.max_seconds, seconds)

    def should_report(self, now: float | None = None) -> bool:
        clock = time.monotonic() if now is None else now
        return clock - self._last_report >= self.report_interval_sec

    def snapshot(self, now: float | None = None) -> dict[str, dict[str, float | int]]:
        clock = time.monotonic() if now is None else now
        self._last_report = clock
        names = set(self._stats) | set(self._interval_stats)
        snapshot: dict[str, dict[str, float | int]] = {}
        for name in names:
            cumulative = self._stats.get(name, StageStats())
            interval = self._interval_stats.get(name, StageStats())
            snapshot[name] = {
                "cumulative_count": cumulative.count,
                "cumulative_total_ms": round(cumulative.total_seconds * 1000, 3),
                "cumulative_max_ms": round(cumulative.max_seconds * 1000, 3),
                "interval_count": interval.count,
                "interval_total_ms": round(interval.total_seconds * 1000, 3),
                "interval_max_ms": round(interval.max_seconds * 1000, 3),
            }
        self._interval_stats = {}
        return snapshot
