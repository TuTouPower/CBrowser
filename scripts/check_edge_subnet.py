#!/usr/bin/env python3
"""Refuse a deploy when the derived edge subnet overlaps existing networks.

Usage: check_edge_subnet.py <candidate-cidr> [--exclude-network <name>]

The edge network is a fixed per-instance /16 (derived by deploy.sh from
the instance identity). Docker refuses a second bridge network with an
overlapping subnet at compose-up time; this check fails earlier, with an
actionable hint, by comparing the candidate against:

- every existing Docker network subnet (``docker network ls`` + inspect), and
- every host interface address (``ip -j addr`` on Linux, ``ifconfig`` on
  macOS/BSD — best effort; when neither is available only Docker networks
  are checked).

The ``--exclude-network`` option names this instance's own edge network
(``${CBROWSER_PREFIX}-edge``, passed by deploy.sh). A network is excluded
only when its name AND its subnet both match the candidate: after the
first deploy the own edge network already exists with exactly this
subnet, and a redeploy or rollback must not be refused by its own
network (t054 R2 test f005). A same-name network with a different subnet
is stale — the edge subnet changed since the last deploy — and is still
refused, with a specific remedy instead of the generic hint. Foreign
networks are never excluded.

Exit 0: no overlap. Exit 1: overlap found (details on stderr).
Exit 2: Docker network enumeration failed (fail closed — the deploy must
not proceed blind when Docker cannot even list its networks).
"""

from __future__ import annotations

import ipaddress
import json
import re
import subprocess
import sys


def _docker_networks() -> list[tuple[str | None, ipaddress.IPv4Network]]:
    """Every existing Docker network as (name, subnet) pairs.

    The name comes from ``docker network inspect`` (``Name`` field); it
    may be None for records without one, which are always treated as
    foreign. Inspect failures fail closed (RuntimeError → exit 2).
    """
    try:
        listed = subprocess.run(
            ["docker", "network", "ls", "--format", "{{.ID}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"docker network ls failed: {exc}") from exc
    if listed.returncode != 0:
        raise RuntimeError(
            f"docker network ls failed (exit {listed.returncode}): "
            f"{listed.stderr.strip()}"
        )
    ids = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
    if not ids:
        return []
    try:
        inspected = subprocess.run(
            ["docker", "network", "inspect", *ids],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"docker network inspect failed: {exc}") from exc
    if inspected.returncode != 0:
        raise RuntimeError(
            f"docker network inspect failed (exit {inspected.returncode}): "
            f"{inspected.stderr.strip()}"
        )
    subnets: list[tuple[str | None, ipaddress.IPv4Network]] = []
    try:
        networks = json.loads(inspected.stdout)
    except ValueError as exc:
        raise RuntimeError(
            f"docker network inspect returned unparseable JSON: {exc}"
        ) from exc
    for network in networks if isinstance(networks, list) else []:
        name = network.get("Name")
        configs = (network.get("IPAM") or {}).get("Config") or []
        for config in configs:
            subnet = config.get("Subnet")
            if subnet:
                subnets.append(
                    (name, ipaddress.ip_network(subnet, strict=False))
                )
    return subnets


def _host_interface_networks() -> list[ipaddress.IPv4Network]:
    """Host interface networks, best effort (empty when unenumerable)."""
    try:
        out = subprocess.run(
            ["ip", "-j", "addr"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0:
            networks: list[ipaddress.IPv4Network] = []
            for iface in json.loads(out.stdout):
                for addr in iface.get("addr_info", []):
                    if addr.get("family") != "inet":
                        continue
                    networks.append(
                        ipaddress.ip_network(
                            f"{addr['local']}/{addr['prefixlen']}",
                            strict=False,
                        )
                    )
            return networks
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
        pass
    try:
        out = subprocess.run(
            ["ifconfig"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            return []
    except (OSError, subprocess.TimeoutExpired):
        return []
    networks = []
    # ifconfig forms: "inet 192.168.1.2 netmask 0xffffff00 ..." (macOS/BSD)
    # and "inet 172.17.0.1  netmask 255.255.0.0 ..." (Linux).
    for match in re.finditer(
        r"inet (\d+\.\d+\.\d+\.\d+) netmask (0x[0-9a-fA-F]+|\d+\.\d+\.\d+\.\d+)",
        out.stdout,
    ):
        ip, mask = match.groups()
        if mask.startswith("0x"):
            mask_int = int(mask, 16)
            prefixlen = bin(mask_int).count("1")
        else:
            prefixlen = ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
        networks.append(
            ipaddress.ip_network(f"{ip}/{prefixlen}", strict=False)
        )
    return networks


class _UsageError(Exception):
    """CLI argument error: main() prints usage and returns 2."""


def _parse_args(argv: list[str]) -> tuple[str, str | None]:
    """Parse ``<candidate-cidr> [--exclude-network <name>]``.

    Raises _UsageError on a duplicate/missing --exclude-network value,
    an unknown --flag, a second positional, or a missing candidate.
    """
    candidate_text: str | None = None
    exclude_network: str | None = None
    args = argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--exclude-network":
            if exclude_network is not None or i + 1 >= len(args):
                raise _UsageError
            exclude_network = args[i + 1]
            i += 2
        elif arg.startswith("--") or candidate_text is not None:
            raise _UsageError
        else:
            candidate_text = arg
            i += 1
    if candidate_text is None:
        raise _UsageError
    return candidate_text, exclude_network


def _classify_overlaps(
    existing: list[tuple[str | None, ipaddress.IPv4Network]],
    candidate: ipaddress.IPv4Network,
    exclude_network: str | None,
) -> tuple[
    list[tuple[str, ipaddress.IPv4Network]],
    list[tuple[str | None, ipaddress.IPv4Network]],
]:
    """Split overlapping Docker networks into (conflicts, stale_own).

    A network is excluded only when its name AND its subnet both match
    the candidate: this instance's own edge network, created by an
    earlier deploy of the same instance with the same subnet — a
    redeploy or rollback must not be refused by its own network
    (t054 R2 test f005). A same-name network with a different subnet
    is stale (the edge subnet changed since the last deploy) and is
    still refused, with its own remedy. Foreign networks are never
    excluded.
    """
    conflicts: list[tuple[str, ipaddress.IPv4Network]] = []
    stale_own: list[tuple[str | None, ipaddress.IPv4Network]] = []
    for name, net in existing:
        if not net.overlaps(candidate):
            continue
        if (
            exclude_network is not None
            and name == exclude_network
            and net == candidate
        ):
            continue
        if exclude_network is not None and name == exclude_network:
            stale_own.append((name, net))
            continue
        conflicts.append(("Docker network", net))
    return conflicts, stale_own


def main(argv: list[str]) -> int:
    try:
        candidate_text, exclude_network = _parse_args(argv)
    except _UsageError:
        print(
            f"usage: {argv[0]} <candidate-cidr> [--exclude-network <name>]",
            file=sys.stderr,
        )
        return 2
    try:
        candidate = ipaddress.ip_network(candidate_text, strict=False)
    except ValueError as exc:
        print(f"invalid candidate subnet {candidate_text!r}: {exc}", file=sys.stderr)
        return 2
    try:
        existing = _docker_networks()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    conflicts, stale_own = _classify_overlaps(
        existing, candidate, exclude_network
    )
    for net in _host_interface_networks():
        if net.overlaps(candidate):
            conflicts.append(("host interface", net))
    if not conflicts and not stale_own:
        return 0
    for name, net in stale_own:
        print(
            f"edge subnet {candidate} overlaps own edge network "
            f"{name!r} (subnet {net}); remove the stale network with "
            f"'docker network rm {name}' before redeploying",
            file=sys.stderr,
        )
    for label, net in conflicts:
        print(
            f"edge subnet {candidate} overlaps {label} subnet {net}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
