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
        self._last_report = time.monotonic()

    def record(self, name: str, seconds: float) -> None:
        stats = self._stats.setdefault(name, StageStats())
        stats.count += 1
        stats.total_seconds += seconds
        stats.max_seconds = max(stats.max_seconds, seconds)

    def should_report(self, now: float | None = None) -> bool:
        clock = time.monotonic() if now is None else now
        return clock - self._last_report >= self.report_interval_sec

    def snapshot(self, now: float | None = None) -> dict[str, dict[str, float | int]]:
        clock = time.monotonic() if now is None else now
        self._last_report = clock
        return {
            name: {
                "count": stats.count,
                "total_ms": round(stats.total_seconds * 1000, 3),
                "max_ms": round(stats.max_seconds * 1000, 3),
            }
            for name, stats in self._stats.items()
        }
