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


def probe_network_name(prefix: str, probe_id: str) -> str:
    """One-shot network for an egress probe helper (t052).  A fresh
    network per probe keeps probes isolated from each other and from
    profile networks; it is removed after the probe."""
    return f"{prefix}-probe-net-{probe_id}"


def network_labels(
    prefix: str,
    profile_id: str,
    *,
    deployment_id: str | None = None,
) -> dict[str, str]:
    labels = {
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.profile-id": profile_id,
        "com.cbrowser.prefix": prefix,
    }
    if deployment_id:
        labels["com.cbrowser.instance-id"] = deployment_id
    return labels


def network_ownership_matches(
    labels: dict[str, Any],
    *,
    deployment_id: str | None = None,
) -> bool:
    """Ownership for a network from its labels (A59/AC-021, strict t069).

    The non-empty deployment instance id is the sole ownership
    credential: the network is ours only when its
    ``com.cbrowser.instance-id`` label equals ``deployment_id``. A
    missing deployment id, or a missing or mismatched label, means
    "not ours" -- never claim, never delete. Name, prefix and
    managed-by labels play no part in the decision.
    """
    if not deployment_id:
        return False
    return labels.get("com.cbrowser.instance-id") == deployment_id


def endpoint_port(scheme: str) -> int | None:
    return DEFAULT_ENDPOINT_PORTS.get(scheme)
