"""CBrowser Network Policy Specification and In-Namespace Installer.

AC / Implementation Contract:
- NetworkPolicySpec: strict Pydantic model (role, allowed_tcp, allowed_udp).
- Endpoints are IP literals + port only. Extra fields forbidden.
- Ephemeral netns execution: python -m cbrowser.supervisor.network_policy <JSON>
- Applies to current container namespace only via subprocess argv arrays.
- IPv4 & IPv6 fail-closed:
  Browser: incoming new connections denied (loopback & established permitted).
  Browser: public egress permitted; private/CGNAT/multicast denied except allowed.
  Stream: incoming permits loopback, established, and its own UDP mux port.
  Stream: outgoing permits the trusted Gateway and explicit endpoints.
  Stream direct media: public ICE egress permitted for local viewers.
- Atomic restore per address family using iptables-restore / ip6tables-restore.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import subprocess
import sys
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger("cbrowser.supervisor.network_policy")

# Address ranges to block for private egress
# RFC1918, Carrier Grade NAT, Loopback, Link-Local, Benchmark, Multicast, Reserved
BLOCKED_IPV4_RANGES = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-Local
    ipaddress.ip_network("198.18.0.0/15"),  # Benchmark
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved / Broadcast
]

# IPv6 non-public / internal / reserved ranges
BLOCKED_IPV6_RANGES = [
    ipaddress.ip_network("::1/128"),  # Loopback
    ipaddress.ip_network("fc00::/7"),  # Unique Local Address (ULA)
    ipaddress.ip_network("fe80::/10"),  # Link-Local
    ipaddress.ip_network("ff00::/8"),  # Multicast
    ipaddress.ip_network("2001:db8::/32"),  # Documentation
    ipaddress.ip_network("100::/64"),  # Discard prefix
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped IPv6
]

# Valid UDP mux port range for Selkies / Stream
UDP_MUX_MIN = 30000
UDP_MUX_MAX = 30991

def _validate_ip_port(v: tuple[str, int]) -> tuple[str, int]:
    if not (isinstance(v, (tuple, list)) and len(v) == 2):
        raise ValueError("Endpoint must be a tuple of (IP literal, port)")
    ip_str, port = v
    if not isinstance(ip_str, str) or "%" in ip_str:
        raise ValueError("IP address must be a string literal")
    try:
        ipaddress.ip_address(ip_str)
    except ValueError as exc:
        raise ValueError(f"Invalid IP address literal: {exc}") from exc
    if not (type(port) is int and 1 <= port <= 65535):
        raise ValueError(f"Port must be an integer between 1 and 65535, got {port}")
    return (str(ipaddress.ip_address(ip_str)), port)


class NetworkPolicySpec(BaseModel):
    """Specification of network filtering policy for a container sandbox."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["browser", "stream"]
    allowed_tcp: list[tuple[str, int]] = Field(default_factory=list)
    allowed_udp: list[tuple[str, int]] = Field(default_factory=list)
    udp_mux_port: int | None = Field(default=None, ge=UDP_MUX_MIN, le=UDP_MUX_MAX)

    @field_validator("allowed_tcp", "allowed_udp", mode="before")
    @classmethod
    def validate_endpoints(cls, v: list[Any]) -> list[tuple[str, int]]:
        if not isinstance(v, list):
            raise ValueError("Endpoint list must be a list")  # noqa: TRY004
        validated: list[tuple[str, int]] = []
        for item in v:
            if isinstance(item, (tuple, list)):
                validated.append(_validate_ip_port(item))
            else:
                raise ValueError(f"Invalid endpoint format: {item}")  # noqa: TRY004
        return validated

    @model_validator(mode="after")
    def validate_role_mux_port(self) -> NetworkPolicySpec:
        if self.role == "stream" and self.udp_mux_port is None:
            raise ValueError("udp_mux_port is required for stream role (30000..30991)")
        if self.role == "browser" and self.udp_mux_port is not None:
            raise ValueError("udp_mux_port must not be specified for browser role")
        return self


def render_iptables_rules(spec: NetworkPolicySpec) -> str:
    """Render IPv4 iptables-restore script."""
    lines: list[str] = [
        "*filter",
        ":INPUT DROP [0:0]",
        ":FORWARD DROP [0:0]",
        ":OUTPUT DROP [0:0]",
        # Loopback interface is fully allowed
        "-A INPUT -i lo -j ACCEPT",
        "-A OUTPUT -o lo -j ACCEPT",
        # Established and related traffic is allowed
        "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
        "-A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
    ]

    # Role-specific INPUT rules
    if spec.role == "stream":
        assert spec.udp_mux_port is not None
        lines.append(f"-A INPUT -p udp --dport {spec.udp_mux_port} -j ACCEPT")

    # OUTPUT rules: explicitly allowed endpoints
    for ip_str, port in spec.allowed_tcp:
        addr = ipaddress.ip_address(ip_str)
        if addr.version == 4:
            lines.append(f"-A OUTPUT -p tcp -d {ip_str} --dport {port} -j ACCEPT")

    for ip_str, port in spec.allowed_udp:
        addr = ipaddress.ip_address(ip_str)
        if addr.version == 4:
            lines.append(f"-A OUTPUT -p udp -d {ip_str} --dport {port} -j ACCEPT")

    # Block non-public / internal IPv4 ranges
    for net in BLOCKED_IPV4_RANGES:
        lines.append(f"-A OUTPUT -d {net} -j DROP")

    lines.append("-A OUTPUT -j ACCEPT")
    lines.append("COMMIT\n")

    return "\n".join(lines)


def render_ip6tables_rules(spec: NetworkPolicySpec) -> str:
    """Render IPv6 ip6tables-restore script."""
    lines: list[str] = [
        "*filter",
        ":INPUT DROP [0:0]",
        ":FORWARD DROP [0:0]",
        ":OUTPUT DROP [0:0]",
        # Loopback interface allowed
        "-A INPUT -i lo -j ACCEPT",
        "-A OUTPUT -o lo -j ACCEPT",
        # Neighbor discovery stays on the local link (RFC 4861 hop limit 255).
        *[
            f"-A {chain} -p ipv6-icmp --icmpv6-type {kind} -m hl --hl-eq 255 -j ACCEPT"
            for chain in ("INPUT", "OUTPUT")
            for kind in (133, 134, 135, 136)
        ],
        # Established and related traffic
        "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
        "-A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
    ]

    # Role-specific INPUT rules
    if spec.role == "stream":
        assert spec.udp_mux_port is not None
        lines.append(f"-A INPUT -p udp --dport {spec.udp_mux_port} -j ACCEPT")

    # OUTPUT rules for allowed IPv6 endpoints
    for ip_str, port in spec.allowed_tcp:
        addr = ipaddress.ip_address(ip_str)
        if addr.version == 6:
            lines.append(f"-A OUTPUT -p tcp -d {ip_str} --dport {port} -j ACCEPT")

    for ip_str, port in spec.allowed_udp:
        addr = ipaddress.ip_address(ip_str)
        if addr.version == 6:
            lines.append(f"-A OUTPUT -p udp -d {ip_str} --dport {port} -j ACCEPT")

    # Block private / ULA / non-public IPv6 ranges
    for net6 in BLOCKED_IPV6_RANGES:
        lines.append(f"-A OUTPUT -d {net6} -j DROP")

    lines.append("-A OUTPUT -j ACCEPT")
    lines.append("COMMIT\n")

    return "\n".join(lines)


def apply_policy(spec: NetworkPolicySpec) -> None:
    """Install only in a fresh owned namespace, without replacing another policy."""
    for command in ("iptables-save", "ip6tables-save"):
        result = subprocess.run(
            [command, "-t", "filter"],
            capture_output=True,
            timeout=5,
            check=True,
        )
        for line in result.stdout.decode("utf-8").splitlines():
            if line.startswith("-A "):
                raise RuntimeError("Network namespace already has a filter policy")
            fields = line.split()
            if (
                len(fields) >= 2
                and fields[0] in {":INPUT", ":OUTPUT", ":FORWARD"}
                and fields[1] != "ACCEPT"
            ):
                raise RuntimeError("Network namespace already has a filter policy")
    for command, rules in (
        ("iptables-restore", render_iptables_rules(spec)),
        ("ip6tables-restore", render_ip6tables_rules(spec)),
    ):
        result = subprocess.run(
            [command, "-w", "5", "--noflush"],
            input=rules.encode("utf-8"),
            capture_output=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Network filter installation failed")


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 1:
        sys.stderr.write(
            "Usage: python -m cbrowser.supervisor.network_policy <POLICY_JSON>\n"
        )
        sys.exit(1)

    try:
        raw_json = argv[0]
        data = json.loads(raw_json)
        spec = NetworkPolicySpec.model_validate(data)
    except Exception as exc:  # noqa: BLE001 - CLI argument json decode or schema validation error exits with code 2
        logger.error("Invalid policy spec: error_type=%s", type(exc).__name__)
        sys.exit(2)

    try:
        apply_policy(spec)
    except Exception as exc:  # noqa: BLE001 - iptables policy installation failure exits with code 3
        logger.error("Policy installation failed: error_type=%s", type(exc).__name__)
        sys.exit(3)


if __name__ == "__main__":
    main()
