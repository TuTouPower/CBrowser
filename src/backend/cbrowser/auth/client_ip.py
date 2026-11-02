"""Resolve the client IP behind explicitly trusted reverse proxies."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_trusted_proxy_cidrs(raw: str | Iterable[str] | None) -> list[IPNetwork]:
    if raw is None:
        return []
    values = raw.split(",") if isinstance(raw, str) else raw
    networks: list[IPNetwork] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        try:
            networks.append(ipaddress.ip_network(text, strict=False))
        except ValueError as exc:
            raise ValueError(f"Invalid trusted proxy CIDR: {text!r}") from exc
    return networks


def _is_trusted(
    address: str | ipaddress._BaseAddress, networks: list[IPNetwork]
) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(parsed in network for network in networks)


def resolve_client_ip(
    peer_ip: str | None,
    forwarded_for: str | None,
    trusted_networks: list[IPNetwork],
) -> str:
    """Use XFF only when the direct peer is trusted; walk it from the right."""
    if not peer_ip:
        return "unknown"
    if not trusted_networks or not _is_trusted(peer_ip, trusted_networks):
        return peer_ip
    if not forwarded_for:
        return peer_ip
    hops = [value.strip() for value in forwarded_for.split(",") if value.strip()]
    for hop in reversed(hops):
        try:
            address = ipaddress.ip_address(hop)
        except ValueError:
            continue
        if not any(address in network for network in trusted_networks):
            return str(address)
    return peer_ip
