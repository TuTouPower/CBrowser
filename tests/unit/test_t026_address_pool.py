"""t026 AC-003: fixed-endpoint media address planning.

The allocator must be explicit and fail loudly: no silent fallback to a
random Docker subnet when the pool is exhausted or a candidate collides
with an existing network or a host route.
"""

import ipaddress
from pathlib import Path

import pytest
from cbrowser.supervisor.address_pool import (
    LABEL_GATEWAY_ENDPOINT,
    LABEL_MEDIA_SPEC,
    MediaNetworkPlan,
    MediaPoolExhaustedError,
    MediaSubnetAllocator,
    host_route_networks,
    media_network_labels,
    plan_for_subnet,
    plan_from_labels,
)


def _net(text: str) -> ipaddress.IPv4Network:
    return ipaddress.ip_network(text)


def test_plan_for_subnet_derives_range_and_endpoint():
    plan = plan_for_subnet(_net("10.251.7.0/24"))
    assert plan.subnet == "10.251.7.0/24"
    # Low half is the container range; the Gateway endpoint sits at the
    # top usable host address, outside the range.
    assert plan.ip_range == "10.251.7.0/25"
    assert plan.gateway_endpoint == "10.251.7.254"
    plan.validate()


def test_plan_validation_rejects_endpoint_inside_range():
    plan = MediaNetworkPlan(
        subnet="10.251.7.0/24",
        ip_range="10.251.7.0/24",
        gateway_endpoint="10.251.7.10",
    )
    with pytest.raises(ValueError):
        plan.validate()


def test_allocator_skips_used_subnets():
    allocator = MediaSubnetAllocator("10.251.0.0/16")
    used = [_net("10.251.0.0/24"), _net("10.251.1.0/24")]
    assert allocator.allocate(used).subnet == "10.251.2.0/24"


def test_allocator_exhaustion_is_explicit():
    allocator = MediaSubnetAllocator("10.251.9.0/24")
    first = allocator.allocate([])
    assert first.subnet == "10.251.9.0/24"
    with pytest.raises(MediaPoolExhaustedError):
        allocator.allocate([_net(first.subnet)])


def test_labels_round_trip_and_drift_detection():
    plan = plan_for_subnet(_net("10.251.3.0/24"))
    labels = media_network_labels({"com.cbrowser.role": "media"}, plan)
    assert labels[LABEL_MEDIA_SPEC] == "fixed-endpoint-v1"
    assert labels[LABEL_GATEWAY_ENDPOINT] == "10.251.3.254"
    assert plan_from_labels(labels) == plan
    # A spec id from another generation is not this spec.
    drifted = dict(labels)
    drifted[LABEL_MEDIA_SPEC] = "fixed-endpoint-v0"
    assert plan_from_labels(drifted) is None
    # Missing labels mean a pre-t026 network: not conforming.
    assert plan_from_labels({}) is None
    assert plan_from_labels(None) is None


def test_host_route_networks_parses_proc_net_route(tmp_path: Path):
    # 0000FE0A little-endian is 10.254.0.0; mask FFFFFF00 is /24. The
    # default route (destination 0) is not a collision input.
    route_file = tmp_path / "route"
    route_file.write_text(
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
        "eth0\t0000FE0A\t00000000\t0001\t0\t0\t0\tFFFFFF00\n"
        "eth0\t00000000\t0100FE0A\t0003\t0\t0\t0\t00000000\n"
    )
    networks = host_route_networks(route_file)
    assert [str(n) for n in networks] == ["10.254.0.0/24"]
    assert host_route_networks(tmp_path / "missing") == []
