"""t054 R1 f001/test f001 + R2 test f005: unit tests for
scripts/check_edge_subnet.py.

The deploy-time precheck refuses a deploy when the candidate edge
subnet overlaps an existing Docker network subnet or a host interface
address, and fails closed (exit 2) when Docker cannot even enumerate
its networks or the candidate is not a CIDR. Docker and host-interface
enumeration are faked through the module's ``subprocess.run`` so these
tests never touch a real daemon. The ``--exclude-network`` option
excludes this instance's own edge network (same name AND same subnet);
a foreign network with the same subnet is still refused, and a
same-name network with a different subnet is stale and still refused.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_edge_subnet", ROOT / "scripts" / "check_edge_subnet.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_run_factory(
    *,
    docker_subnets: list[str] | None = None,
    docker_names: list[str | None] | None = None,
    docker_ls_fail: bool = False,
    host_ifaces: list[dict] | None = None,
):
    def fake_run(argv, **kwargs):
        if argv[:3] == ["docker", "network", "ls"]:
            if docker_ls_fail:
                return _Completed(1, "", "cannot connect to the Docker daemon")
            return _Completed(0, "net1\n")
        if argv[:3] == ["docker", "network", "inspect"]:
            subnets = docker_subnets or []
            names = docker_names or [None] * len(subnets)
            networks = []
            for subnet, name in zip(subnets, names):
                record: dict = {"IPAM": {"Config": [{"Subnet": subnet}]}}
                if name is not None:
                    record["Name"] = name
                networks.append(record)
            return _Completed(0, json.dumps(networks))
        if argv[:3] == ["ip", "-j", "addr"]:
            return _Completed(0, json.dumps(host_ifaces or []))
        return _Completed(1, "", "unexpected command")

    return fake_run


def test_no_overlap_returns_zero(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        _fake_run_factory(docker_subnets=["172.20.0.0/16"]),
    )
    assert module.main(["check_edge_subnet.py", "172.30.0.0/16"]) == 0


def test_overlap_with_docker_network_returns_one(monkeypatch, capsys) -> None:
    module = _load_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        _fake_run_factory(docker_subnets=["172.30.0.0/16"]),
    )
    assert module.main(["check_edge_subnet.py", "172.30.0.0/16"]) == 1
    assert "overlaps Docker network subnet 172.30.0.0/16" in capsys.readouterr().err


def test_overlap_with_host_interface_returns_one(monkeypatch, capsys) -> None:
    module = _load_module()
    host_ifaces = [
        {
            "addr_info": [
                {"family": "inet", "local": "172.30.5.4", "prefixlen": 16}
            ]
        }
    ]
    monkeypatch.setattr(
        module.subprocess,
        "run",
        _fake_run_factory(docker_subnets=[], host_ifaces=host_ifaces),
    )
    assert module.main(["check_edge_subnet.py", "172.30.0.0/16"]) == 1
    assert "overlaps host interface subnet" in capsys.readouterr().err


def test_docker_enumeration_failure_fails_closed(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(
        module.subprocess, "run", _fake_run_factory(docker_ls_fail=True)
    )
    assert module.main(["check_edge_subnet.py", "172.30.0.0/16"]) == 2


def test_invalid_candidate_returns_two() -> None:
    module = _load_module()
    assert module.main(["check_edge_subnet.py", "not-a-cidr"]) == 2
    assert module.main(["check_edge_subnet.py"]) == 2


def test_own_edge_network_excluded_by_name_and_subnet(monkeypatch) -> None:
    """t054 R2 test f005: the instance's own edge network (same name AND
    same subnet as the candidate) is excluded — a redeploy or rollback
    must not be refused by its own network."""
    module = _load_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        _fake_run_factory(
            docker_subnets=["172.30.0.0/16"],
            docker_names=["cbrowser-t005-edge"],
        ),
    )
    assert (
        module.main(
            [
                "check_edge_subnet.py",
                "172.30.0.0/16",
                "--exclude-network",
                "cbrowser-t005-edge",
            ]
        )
        == 0
    )


def test_foreign_network_with_same_subnet_still_refused(
    monkeypatch, capsys
) -> None:
    """t054 R2 test f005: the exclusion is scoped by name, not by subnet
    — a foreign network with the same subnet is still refused even
    while the own edge network is excluded."""
    module = _load_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        _fake_run_factory(
            docker_subnets=["172.30.0.0/16", "172.30.0.0/16"],
            docker_names=["cbrowser-t005-edge", "other-edge"],
        ),
    )
    assert (
        module.main(
            [
                "check_edge_subnet.py",
                "172.30.0.0/16",
                "--exclude-network",
                "cbrowser-t005-edge",
            ]
        )
        == 1
    )
    assert "overlaps Docker network subnet 172.30.0.0/16" in capsys.readouterr().err


def test_stale_own_network_with_different_subnet_still_refused(
    monkeypatch, capsys
) -> None:
    """t054 R2 test f005: a same-name network with a different subnet is
    stale (the edge subnet changed since the last deploy) — it is still
    refused, with the removal remedy instead of the generic hint."""
    module = _load_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        _fake_run_factory(
            docker_subnets=["172.30.0.0/16"],
            docker_names=["cbrowser-t005-edge"],
        ),
    )
    assert (
        module.main(
            [
                "check_edge_subnet.py",
                "172.30.128.0/17",
                "--exclude-network",
                "cbrowser-t005-edge",
            ]
        )
        == 1
    )
    err = capsys.readouterr().err
    assert "own edge network 'cbrowser-t005-edge'" in err
    assert "docker network rm cbrowser-t005-edge" in err


def test_exclude_network_with_unmatched_name_still_refuses(
    monkeypatch, capsys
) -> None:
    """t054 R2 test f005: the exclusion flag must not silently disable
    the check — when no network carries the excluded name, an overlap is
    still refused."""
    module = _load_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        _fake_run_factory(
            docker_subnets=["172.30.0.0/16"],
            docker_names=["other-edge"],
        ),
    )
    assert (
        module.main(
            [
                "check_edge_subnet.py",
                "172.30.0.0/16",
                "--exclude-network",
                "cbrowser-t005-edge",
            ]
        )
        == 1
    )
    assert "overlaps Docker network subnet 172.30.0.0/16" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        # Duplicate --exclude-network (raise at _parse_args :169).
        ["172.30.0.0/16", "--exclude-network", "a", "--exclude-network", "b"],
        # --exclude-network without a value (raise at _parse_args :169).
        ["172.30.0.0/16", "--exclude-network"],
        # Unknown --flag (raise at _parse_args :173).
        ["172.30.0.0/16", "--bogus"],
        # Second positional argument (raise at _parse_args :173).
        ["172.30.0.0/16", "172.31.0.0/16"],
    ],
)
def test_parse_args_usage_errors_return_two(monkeypatch, capsys, argv) -> None:
    """t054 R4 test f006: the four _UsageError branches of _parse_args
    that the Round 4 review found uncovered — each must exit 2 with the
    usage text, and parsing must fail before any subprocess call (the
    guard below would raise if main() tried to enumerate networks)."""
    module = _load_module()

    def _must_not_run(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called for usage errors")

    monkeypatch.setattr(module.subprocess, "run", _must_not_run)
    assert module.main(["check_edge_subnet.py", *argv]) == 2
    assert "usage: check_edge_subnet.py <candidate-cidr>" in capsys.readouterr().err
