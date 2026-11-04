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

from cbrowser.udp_mux import udp_mux_bounds
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
UDP_MUX_MIN, UDP_MUX_MAX = udp_mux_bounds()

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
            raise ValueError(
                "udp_mux_port is required for stream role "
                f"({UDP_MUX_MIN}..{UDP_MUX_MAX})"
            )
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


class NetworkPolicyError(RuntimeError):
    """A network policy application failure with bounded diagnostics.

    Carries the failing address family, tool and exit code plus a bounded,
    sanitized excerpt of the tool's stderr — never the full raw output.
    """

    def __init__(
        self, family: str, tool: str, exit_code: int | None, stderr: str
    ) -> None:
        self.family = family
        self.tool = tool
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(
            f"Network filter installation failed: family={family} "
            f"tool={tool} exit_code={exit_code} stderr={stderr!r}"
        )


_MAX_STDERR_CHARS = 512


def _bounded_stderr(raw: bytes) -> str:
    """Sanitize tool stderr into a bounded single-line diagnostic."""
    text = raw.decode("utf-8", errors="replace")
    cleaned = "".join(ch if ch.isprintable() or ch == " " else " " for ch in text)
    return " ".join(cleaned.split())[-_MAX_STDERR_CHARS:]


def _fail_closed_rules() -> str:
    """Minimal ruleset that drops everything except loopback."""
    return "\n".join(
        [
            "*filter",
            ":INPUT DROP [0:0]",
            ":FORWARD DROP [0:0]",
            ":OUTPUT DROP [0:0]",
            "-A INPUT -i lo -j ACCEPT",
            "-A OUTPUT -o lo -j ACCEPT",
            "COMMIT",
            "",
        ]
    )


_FAMILY_TOOLS = {
    "ipv4": "iptables-restore",
    "ipv6": "ip6tables-restore",
}


def _install_fail_closed(family: str) -> None:
    """Best-effort DROP-everything install for one family after a failure.

    Unlike the normal path this restore deliberately omits --noflush:
    the failed family's sibling may already carry the target policy's
    ACCEPT rules, and a fail-closed state that leaves earlier ACCEPT
    rules ahead of the DROP defaults is not closed. The restore replaces
    the whole table with the minimal DROP ruleset (review
    t022_code_f005).
    """
    try:
        subprocess.run(
            [_FAMILY_TOOLS[family], "-w", "5"],
            input=_fail_closed_rules().encode("utf-8"),
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:  # noqa: BLE001 - fallback failure keeps the original diagnostic
        logger.warning("Fail-closed fallback failed for family=%s", family)


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
    rendered = {
        "ipv4": render_iptables_rules(spec),
        "ipv6": render_ip6tables_rules(spec),
    }
    for family in ("ipv4", "ipv6"):
        tool = _FAMILY_TOOLS[family]
        result = subprocess.run(
            [tool, "-w", "5", "--noflush"],
            input=rendered[family].encode("utf-8"),
            capture_output=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            # Fail closed on every family: the failed one may be partially
            # applied and the untouched one still has default ACCEPT chains.
            # Existing teardown removes the namespace afterwards.
            for fallback_family in ("ipv4", "ipv6"):
                _install_fail_closed(fallback_family)
            raise NetworkPolicyError(
                family=family,
                tool=tool,
                exit_code=result.returncode,
                stderr=_bounded_stderr(result.stderr or b""),
            )


_IMPLICIT_PROTOCOL_MODULES = frozenset({"tcp", "udp", "icmp", "icmp6"})


def _normalized_address(value: str) -> str:
    try:
        return str(ipaddress.ip_network(value, strict=False))
    except ValueError:
        return value


def _canonical_rule(line: str) -> str:
    """Normalize a rule so renderer and live dumps compare semantically.

    ``iptables-save`` on the nft backend canonicalizes what
    ``iptables-restore`` accepted: it adds implicit ``-m tcp``/``-m udp``
    modules, writes IPv4 hosts as ``/32``, reorders match clauses, and
    sorts conntrack states. The same ruleset must verify as equal after
    one apply/read cycle, otherwise convergence would rebuild a healthy
    Stream forever (t032 AC-007 real-kernel finding).
    """
    tokens = line.split()
    if len(tokens) < 2 or tokens[0] != "-A":
        return line
    chain = tokens[1]
    atoms: list[str] = []
    index = 2
    while index < len(tokens):
        token = tokens[index]
        if token == "-m" and index + 1 < len(tokens):
            module = tokens[index + 1]
            if module not in _IMPLICIT_PROTOCOL_MODULES:
                atoms.append(f"-m {module}")
            index += 2
            continue
        value = tokens[index + 1] if index + 1 < len(tokens) else ""
        if token in ("-d", "-s"):
            atoms.append(f"{token} {_normalized_address(value)}")
        elif token == "--ctstate":
            atoms.append(f"{token} {','.join(sorted(value.split(',')))}")
        else:
            atoms.append(f"{token} {value}")
        index += 2
    return f"-A {chain} " + " ".join(sorted(atoms))


def parse_filter_rules(text: str) -> tuple[dict[str, str], frozenset[str]]:
    """Parse an iptables-save / iptables-restore filter table.

    Returns (chain default policies, canonical rule lines). Packet/byte
    counters are stripped and rules are canonicalized so a live
    `iptables-save` dump and the rendered restore script for the same
    ruleset parse to equal values.
    """
    policies: dict[str, str] = {}
    rules: set[str] = set()
    in_filter = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "*filter":
            in_filter = True
            continue
        if line == "COMMIT":
            in_filter = False
            continue
        if not in_filter:
            continue
        if line.startswith(":"):
            fields = line[1:].split()
            if len(fields) >= 2:
                policies[fields[0]] = fields[1]
        elif line.startswith("-A "):
            rules.add(_canonical_rule(line))
    return policies, frozenset(rules)


def rendered_filter_rules(spec: NetworkPolicySpec) -> dict[str, tuple[dict[str, str], frozenset[str]]]:
    """The exact parsed ruleset a successful apply of ``spec`` installs."""
    return {
        "ipv4": parse_filter_rules(render_iptables_rules(spec)),
        "ipv6": parse_filter_rules(render_ip6tables_rules(spec)),
    }


def _save_tool(family: str) -> str:
    return "iptables-save" if family == "ipv4" else "ip6tables-save"


def current_filter_rules(family: str) -> tuple[dict[str, str], frozenset[str]]:
    """Dump the live filter table of this namespace for one family."""
    result = subprocess.run(
        [_save_tool(family), "-t", "filter"],
        capture_output=True,
        timeout=5,
        check=True,
    )
    return parse_filter_rules(result.stdout.decode("utf-8"))


def verify_policy(spec: NetworkPolicySpec) -> bool:
    """True only when the live rules in this namespace equal the spec's."""
    expected = rendered_filter_rules(spec)
    for family in ("ipv4", "ipv6"):
        if current_filter_rules(family) != expected[family]:
            return False
    return True


def install_fail_closed() -> None:
    """Replace both families with the DROP-everything ruleset.

    Used when a Browser namespace's live rules drift from its rendered
    spec: the runtime keeps running but loses all non-loopback traffic
    until an explicit restart reinstalls the real policy (t026 AC-005).

    Unlike the apply-path fallback (best-effort by design), this
    explicit entry point is strict: a failed restore raises
    NetworkPolicyError so callers never record a fail-close that did
    not actually happen.
    """
    for family in ("ipv4", "ipv6"):
        tool = _FAMILY_TOOLS[family]
        try:
            completed = subprocess.run(
                [tool, "-w", "5"],
                input=_fail_closed_rules().encode("utf-8"),
                capture_output=True,
                timeout=10,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001 - strict wrapper re-raises as NetworkPolicyError
            raise NetworkPolicyError(
                family=family,
                tool=tool,
                exit_code=None,
                stderr=f"restore could not run: {type(exc).__name__}",
            ) from exc
        if completed.returncode != 0:
            raise NetworkPolicyError(
                family=family,
                tool=tool,
                exit_code=completed.returncode,
                stderr=_bounded_stderr(completed.stderr or b""),
            )


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    mode = "apply"
    if argv and argv[0] in ("verify", "fail-closed"):
        mode = argv[0]
        argv = argv[1:]
    if mode == "fail-closed":
        if argv:
            sys.stderr.write(
                "Usage: python -m cbrowser.supervisor.network_policy fail-closed\n"
            )
            sys.exit(1)
        try:
            install_fail_closed()
        except Exception as exc:  # noqa: BLE001 - fail-closed install failure exits with code 3
            logger.error(
                "Fail-closed installation failed: error_type=%s", type(exc).__name__
            )
            sys.exit(3)
        return
    if len(argv) != 1:
        sys.stderr.write(
            "Usage: python -m cbrowser.supervisor.network_policy "
            "[verify|fail-closed] <POLICY_JSON>\n"
        )
        sys.exit(1)

    try:
        raw_json = argv[0]
        data = json.loads(raw_json)
        spec = NetworkPolicySpec.model_validate(data)
    except Exception as exc:  # noqa: BLE001 - CLI argument json decode or schema validation error exits with code 2
        logger.error("Invalid policy spec: error_type=%s", type(exc).__name__)
        sys.exit(2)

    if mode == "verify":
        try:
            matched = verify_policy(spec)
        except Exception as exc:  # noqa: BLE001 - verification tooling failure exits with code 3
            logger.error(
                "Policy verification failed: error_type=%s", type(exc).__name__
            )
            sys.exit(3)
        sys.exit(0 if matched else 4)

    try:
        apply_policy(spec)
    except NetworkPolicyError as exc:
        logger.error(
            "Policy installation failed: family=%s tool=%s exit_code=%s stderr=%s",
            exc.family,
            exc.tool,
            exc.exit_code,
            exc.stderr,
        )
        sys.exit(3)
    except Exception as exc:  # noqa: BLE001 - iptables policy installation failure exits with code 3
        logger.error("Policy installation failed: error_type=%s", type(exc).__name__)
        sys.exit(3)


if __name__ == "__main__":
    main()
