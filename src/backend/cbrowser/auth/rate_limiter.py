"""In-memory rate limiter for login failures.

Two layers: a per-source sliding window stops online guessing from one address,
and a global administrator budget stops distributed guessing from rotating
sources. Both are bounded by time windows and pruned lazily.
"""

from __future__ import annotations

import collections
import time


class LoginRateLimiter:
    """Sliding-window failed login limiter with per-source and global budgets."""

    def __init__(
        self,
        max_failures: int = 5,
        window_seconds: float = 60.0,
        global_max_failures: int = 20,
        global_window_seconds: float = 15 * 60.0,
    ):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.global_max_failures = global_max_failures
        self.global_window_seconds = global_window_seconds
        self._failures: dict[str, collections.deque[float]] = collections.defaultdict(
            collections.deque
        )
        self._global_failures: collections.deque[float] = collections.deque()
        self._calls = 0

    @staticmethod
    def _trim(queue: collections.deque[float], cutoff: float) -> None:
        while queue and queue[0] < cutoff:
            queue.popleft()

    def _prune(self, now: float) -> None:
        self._calls += 1
        if self._calls % 128 != 0 and len(self._failures) <= 1024:
            return
        cutoff = now - self.window_seconds
        for client_ip in list(self._failures):
            self._trim(self._failures[client_ip], cutoff)
            if not self._failures[client_ip]:
                self._failures.pop(client_ip, None)

    def rate_limit_layer(self, client_ip: str) -> str | None:
        now = time.time()
        self._prune(now)
        queue = self._failures.get(client_ip)
        if queue is not None:
            self._trim(queue, now - self.window_seconds)
            if len(queue) >= self.max_failures:
                return "source"
        self._trim(self._global_failures, now - self.global_window_seconds)
        if len(self._global_failures) >= self.global_max_failures:
            return "global"
        return None

    def is_rate_limited(self, client_ip: str) -> bool:
        return self.rate_limit_layer(client_ip) is not None

    def retry_after_seconds(self, client_ip: str) -> int:
        now = time.time()
        wait = 0.0
        queue = self._failures.get(client_ip)
        if queue:
            self._trim(queue, now - self.window_seconds)
            if len(queue) >= self.max_failures:
                wait = max(wait, self.window_seconds - (now - queue[0]))
        self._trim(self._global_failures, now - self.global_window_seconds)
        if len(self._global_failures) >= self.global_max_failures:
            wait = max(
                wait, self.global_window_seconds - (now - self._global_failures[0])
            )
        return max(1, int(wait) + (1 if wait % 1 else 0))

    def record_failure(self, client_ip: str) -> None:
        now = time.time()
        self._prune(now)
        self._trim(self._failures[client_ip], now - self.window_seconds)
        self._failures[client_ip].append(now)
        self._trim(self._global_failures, now - self.global_window_seconds)
        self._global_failures.append(now)

    def record_success(self, client_ip: str) -> None:
        self._failures.pop(client_ip, None)
