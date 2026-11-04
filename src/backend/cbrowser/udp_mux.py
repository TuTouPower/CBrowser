"""UDP mux port range shared by Supervisor, Stream Agent, and Gateway.

The range defaults to the production allocation window. Deployments and
isolated test instances can partition it with ``CBROWSER_UDP_MUX_MIN_PORT``
and ``CBROWSER_UDP_MUX_MAX_PORT`` so concurrent instances on one host do
not allocate the same port.
"""

from __future__ import annotations

import os

DEFAULT_UDP_MUX_MIN_PORT = 30000
DEFAULT_UDP_MUX_MAX_PORT = 30991


def _read_port(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Invalid integer in {name}: {raw!r}") from None


def udp_mux_min_port() -> int:
    return _read_port("CBROWSER_UDP_MUX_MIN_PORT", DEFAULT_UDP_MUX_MIN_PORT)


def udp_mux_max_port() -> int:
    return _read_port("CBROWSER_UDP_MUX_MAX_PORT", DEFAULT_UDP_MUX_MAX_PORT)


def udp_mux_bounds() -> tuple[int, int]:
    minimum = udp_mux_min_port()
    maximum = udp_mux_max_port()
    if not 1024 <= minimum <= maximum <= 65535:
        raise ValueError(f"Invalid UDP mux port range: [{minimum}, {maximum}]")
    return minimum, maximum
