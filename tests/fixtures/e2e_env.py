"""Single source of truth for E2E environment prerequisites."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def require_e2e_env(*names: str, paths: tuple[str, ...] = ()) -> dict[str, str]:
    """Return required env values; fail in required mode, skip otherwise."""
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        message = "Missing required E2E environment variables: " + ", ".join(missing)
        if os.environ.get("CBROWSER_E2E_REQUIRED") == "1":
            pytest.fail(message, pytrace=False)
        pytest.skip(message)
    values = {name: os.environ[name] for name in names}
    for name in paths:
        if not Path(values[name]).is_dir():
            message = f"E2E path is not a directory: {values[name]}"
            if os.environ.get("CBROWSER_E2E_REQUIRED") == "1":
                pytest.fail(message, pytrace=False)
            pytest.skip(message)
    return values


def free_udp_port_span(count: int = 2, *, start: int = 32000, end: int = 40960) -> int:
    """Return a base port with ``count`` consecutive free loopback UDP ports."""
    import socket

    for base in range(start, end - count + 1):
        sockets = []
        try:
            for offset in range(count):
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(("127.0.0.1", base + offset))
                sockets.append(sock)
            return base
        except OSError:
            continue
        finally:
            for sock in sockets:
                sock.close()
    raise RuntimeError("No free consecutive UDP port range found")
