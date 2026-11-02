"""UDP Mux Port Allocator for WebRTC Stream Runtime (30000 - 30991).

Thread-safe / asyncio-safe, idempotent, strictly within [30000, 30991].
Provides explicit exhaustion error, and re-use only after release (AC-002).
"""

from __future__ import annotations

import asyncio


class PortPoolExhaustedError(RuntimeError):
    """Raised when no UDP mux ports are available in [30000, 30991]."""



class PortAllocator:
    MIN_PORT: int = 30000
    MAX_PORT: int = 30991

    def __init__(self, min_port: int = MIN_PORT, max_port: int = MAX_PORT):
        if min_port < 1024 or max_port > 65535 or min_port > max_port:
            raise ValueError(f"Invalid port range: [{min_port}, {max_port}]")
        self.min_port = min_port
        self.max_port = max_port
        self._lock = asyncio.Lock()
        self._allocated: dict[str, int] = {}  # profile_id -> port
        self._used_ports: set[int] = set()

    async def allocate(self, profile_id: str) -> int:
        """Idempotently allocate a UDP mux port for profile_id."""
        async with self._lock:
            if profile_id in self._allocated:
                return self._allocated[profile_id]

            for port in range(self.min_port, self.max_port + 1):
                if port not in self._used_ports:
                    self._used_ports.add(port)
                    self._allocated[profile_id] = port
                    return port

            raise PortPoolExhaustedError(
                f"UDP mux port pool exhausted [{self.min_port}, {self.max_port}]"
            )

    async def restore(self, profile_id: str, port: int) -> int:
        """Reserve a Docker-observed port; reject conflicting recovery evidence."""
        async with self._lock:
            if not self.min_port <= port <= self.max_port:
                raise ValueError(
                    "Recovered UDP mux port is outside the configured range"
                )
            previous = self._allocated.get(profile_id)
            if previous == port:
                return port
            if previous is not None:
                raise ValueError("Profile already owns a different UDP mux port")
            if port in self._used_ports:
                raise ValueError("Recovered UDP mux port is owned by another Profile")
            self._allocated[profile_id] = port
            self._used_ports.add(port)
            return port

    async def release(self, profile_id: str) -> int | None:
        """Release the port allocated to profile_id."""
        async with self._lock:
            port = self._allocated.pop(profile_id, None)
            if port is not None:
                self._used_ports.discard(port)
            return port

    def get_port(self, profile_id: str) -> int | None:
        """Return currently allocated port if any."""
        return self._allocated.get(profile_id)

    def is_port_used(self, port: int) -> bool:
        return port in self._used_ports
