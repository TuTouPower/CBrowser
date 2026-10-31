"""In-memory rate limiter for login failures."""

from __future__ import annotations

import collections
import time


class LoginRateLimiter:
    """Sliding window rate limiter tracking failed login attempts per client IP."""

    def __init__(self, max_failures: int = 5, window_seconds: float = 60.0):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, collections.deque[float]] = collections.defaultdict(
            collections.deque
        )

    def _cleanup(self, client_ip: str, now: float) -> None:
        queue = self._failures[client_ip]
        cutoff = now - self.window_seconds
        while queue and queue[0] < cutoff:
            queue.popleft()
        if not queue:
            self._failures.pop(client_ip, None)

    def is_rate_limited(self, client_ip: str) -> bool:
        now = time.time()
        self._cleanup(client_ip, now)
        queue = self._failures.get(client_ip)
        return queue is not None and len(queue) >= self.max_failures

    def record_failure(self, client_ip: str) -> None:
        now = time.time()
        self._cleanup(client_ip, now)
        self._failures[client_ip].append(now)

    def record_success(self, client_ip: str) -> None:
        self._failures.pop(client_ip, None)
