"""Fixed-endpoint address allocation for Profile media networks (t026).

Docker cannot reserve an address on an auto-subnet network, and an
existing network's IPAM cannot be changed after creation (d029). The
only reliable shape is: explicit subnet + an ip_range that covers only
part of it, with the shared Gateway attached at a fixed endpoint inside
the subnet but outside the ip_range, so automatic assignment can never
take it. The Supervisor allocates one subnet per Profile media network
from a configured pool, records the allocation in network labels, and
never falls back to a random/auto address when allocation fails.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

MEDIA_SPEC_ID = "fixed-endpoint-v1"

LABEL_MEDIA_SPEC = "com.cbrowser.media-spec"
LABEL_MEDIA_SUBNET = "com.cbrowser.media-subnet"
LABEL_MEDIA_IP_RANGE = "com.cbrowser.media-ip-range"
LABEL_GATEWAY_ENDPOINT = "com.cbrowser.gateway-endpoint"

DEFAULT_MEDIA_SUBNET_POOL = "10.251.0.0/16"
DEFAULT_SUBNET_PREFIXLEN = 24


class MediaPoolExhaustedError(RuntimeError):
    """No free subnet remains in the configured media address pool."""


@dataclass(frozen=True)
class MediaNetworkPlan:
    """One Profile media network's fixed addressing (all IPv4)."""

    subnet: str
    ip_range: str
    gateway_endpoint: str

    def subnet_network(self) -> ipaddress.IPv4Network:
        return ipaddress.ip_network(self.subnet)

    def validate(self) -> None:
        subnet = ipaddress.ip_network(self.subnet)
        ip_range = ipaddress.ip_network(self.ip_range)
        endpoint = ipaddress.ip_address(self.gateway_endpoint)
        if not ip_range.subnet_of(subnet):
            raise ValueError("media ip_range must lie inside the subnet")
        if endpoint not in subnet:
            raise ValueError("gateway endpoint must lie inside the subnet")
        if endpoint in ip_range:
            raise ValueError("gateway endpoint must lie outside the ip_range")
        if endpoint in (subnet.network_address, subnet.broadcast_address):
            raise ValueError("gateway endpoint must be a usable host address")


def plan_for_subnet(subnet: ipaddress.IPv4Network) -> MediaNetworkPlan:
    """Derive the plan for one subnet: low half is the automatic range,
    the last usable address is the fixed Gateway endpoint (d029)."""
    halves = list(subnet.subnets(prefixlen_diff=1))
    ip_range = halves[0]
    endpoint = subnet.broadcast_address - 1
    plan = MediaNetworkPlan(
        subnet=str(subnet),
        ip_range=str(ip_range),
        gateway_endpoint=str(endpoint),
    )
    plan.validate()
    return plan


class MediaSubnetAllocator:
    """Hands out pool subnets that collide with nothing already in use."""

    def __init__(
        self,
        pool: str = DEFAULT_MEDIA_SUBNET_POOL,
        subnet_prefixlen: int = DEFAULT_SUBNET_PREFIXLEN,
    ) -> None:
        self.pool = ipaddress.ip_network(pool)
        if subnet_prefixlen < self.pool.prefixlen or subnet_prefixlen > 30:
            raise ValueError("media subnet prefix length outside the pool")
        self.subnet_prefixlen = subnet_prefixlen

    def allocate(self, used: Iterable[ipaddress.IPv4Network]) -> MediaNetworkPlan:
        """First pool subnet that overlaps none of ``used``.

        ``used`` must cover every existing Docker network subnet and the
        host route destinations the caller knows about; an overlapping
        candidate is skipped, never forced. Exhaustion is explicit.
        """
        used_networks = list(used)
        for candidate in self.pool.subnets(new_prefix=self.subnet_prefixlen):
            if any(candidate.overlaps(other) for other in used_networks):
                continue
            return plan_for_subnet(candidate)
        raise MediaPoolExhaustedError(
            f"media subnet pool {self.pool} exhausted "
            f"(prefix /{self.subnet_prefixlen})"
        )


def plan_from_labels(labels: dict[str, str] | None) -> MediaNetworkPlan | None:
    """The recorded plan when a network carries a valid current spec.

    Returns None for pre-spec networks and for any inconsistent label
    set; callers treat None as "does not conform, migrate by rebuild".
    """
    if not labels or labels.get(LABEL_MEDIA_SPEC) != MEDIA_SPEC_ID:
        return None
    try:
        plan = MediaNetworkPlan(
            subnet=labels[LABEL_MEDIA_SUBNET],
            ip_range=labels[LABEL_MEDIA_IP_RANGE],
            gateway_endpoint=labels[LABEL_GATEWAY_ENDPOINT],
        )
        plan.validate()
        return plan
    except (KeyError, ValueError):
        return None


def media_network_labels(
    base_labels: dict[str, str], plan: MediaNetworkPlan
) -> dict[str, str]:
    labels = dict(base_labels)
    labels[LABEL_MEDIA_SPEC] = MEDIA_SPEC_ID
    labels[LABEL_MEDIA_SUBNET] = plan.subnet
    labels[LABEL_MEDIA_IP_RANGE] = plan.ip_range
    labels[LABEL_GATEWAY_ENDPOINT] = plan.gateway_endpoint
    return labels


def host_route_networks(
    route_file: Path = Path("/proc/net/route"),
) -> list[ipaddress.IPv4Network]:
    """Best-effort IPv4 destinations from the kernel route table.

    Used only as extra collision input for allocation; an unreadable
    table yields no routes rather than failing the allocation.
    """
    networks: list[ipaddress.IPv4Network] = []
    try:
        lines = route_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return networks
    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 3:
            continue
        try:
            destination = int(fields[1], 16)
            mask = int(fields[7], 16) if len(fields) > 7 else 0
        except ValueError:
            continue
        if destination == 0:
            continue
        # /proc/net/route stores addresses as host-endian hex; the
        # little-endian byte order of the parsed integer is the dotted
        # quad order.
        address = ipaddress.IPv4Address(destination.to_bytes(4, "little"))
        prefixlen = bin(mask).count("1")
        try:
            networks.append(
                ipaddress.ip_network(f"{address}/{prefixlen}", strict=False)
            )
        except ValueError:
            continue
    return networks
