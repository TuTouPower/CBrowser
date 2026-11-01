"""Stateless Docker network names, labels and ownership rules."""

from __future__ import annotations

from typing import Any

DEFAULT_ENDPOINT_PORTS = {
    "http": 80,
    "https": 443,
    "ws": 80,
    "wss": 443,
    "socks5": 1080,
    "socks5h": 1080,
}


def profile_network_name(prefix: str, profile_id: str) -> str:
    return f"{prefix}-net-{profile_id}"


def browser_network_name(prefix: str, profile_id: str) -> str:
    return f"{prefix}-browser-net-{profile_id}"


def network_labels(prefix: str, profile_id: str) -> dict[str, str]:
    return {
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.profile-id": profile_id,
        "com.cbrowser.prefix": prefix,
    }


def network_ownership_matches(
    prefix: str, name: str, labels: dict[str, Any]
) -> bool:
    profile_id = labels.get("com.cbrowser.profile-id")
    return (
        isinstance(profile_id, str)
        and name
        in {
            profile_network_name(prefix, profile_id),
            browser_network_name(prefix, profile_id),
        }
        and labels.get("com.cbrowser.prefix") == prefix
        and labels.get("com.cbrowser.managed-by") == "supervisor"
        and labels.get("com.cbrowser.profile-id") == profile_id
    )


def endpoint_port(scheme: str) -> int | None:
    return DEFAULT_ENDPOINT_PORTS.get(scheme)
