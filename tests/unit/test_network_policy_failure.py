"""Network policy application failures stay fail-closed with bounded,
redacted diagnostics (t022 A34 / AC-010)."""

from __future__ import annotations

import subprocess

import pytest
from cbrowser.supervisor import network_policy
from cbrowser.supervisor.network_policy import (
    NetworkPolicyError,
    NetworkPolicySpec,
    apply_policy,
)


class _Result:
    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _spec() -> NetworkPolicySpec:
    return NetworkPolicySpec(role="browser")


def test_ipv6_failure_keeps_both_families_closed_and_reports_diagnostics(
    monkeypatch,
) -> None:
    calls: list[tuple[str, bytes | None]] = []
    noisy_stderr = ("x" * 5000 + "\x00\x1b[31m boom").encode()

    def fake_run(argv, **kwargs):
        tool = argv[0]
        calls.append((tool, kwargs.get("input")))
        if tool.endswith("-save"):
            return _Result(0, stdout=b"")
        if tool == "ip6tables-restore" and kwargs.get("input") and b"COMMIT" in kwargs["input"] and b"ipv6-icmp" in kwargs["input"]:
            return _Result(2, stderr=noisy_stderr)
        return _Result(0)

    monkeypatch.setattr(network_policy.subprocess, "run", fake_run)
    with pytest.raises(NetworkPolicyError) as caught:
        apply_policy(_spec())
    error = caught.value
    assert error.family == "ipv6"
    assert error.tool == "ip6tables-restore"
    assert error.exit_code == 2
    # stderr diagnostic is bounded and sanitized (no control bytes survive).
    assert len(error.stderr) <= 512
    assert "\x00" not in error.stderr and "\x1b" not in error.stderr
    # After the failure a fail-closed (DROP-default) ruleset was installed
    # for the IPv6 family instead of leaving default ACCEPT chains.
    fallback = [
        data
        for tool, data in calls
        if tool == "ip6tables-restore" and data and b":INPUT DROP" in data and b"ipv6-icmp" not in data
    ]
    assert fallback, "expected a fail-closed fallback restore for ipv6"


def test_ipv4_failure_does_not_leave_ipv6_open(monkeypatch) -> None:
    calls: list[tuple[str, bytes | None]] = []

    def fake_run(argv, **kwargs):
        tool = argv[0]
        calls.append((tool, kwargs.get("input")))
        if tool.endswith("-save"):
            return _Result(0, stdout=b"")
        if tool == "iptables-restore" and kwargs.get("input") and b"192.0.2.0/24" in kwargs["input"]:
            return _Result(1, stderr=b"bad rule")
        return _Result(0)

    monkeypatch.setattr(network_policy.subprocess, "run", fake_run)
    with pytest.raises(NetworkPolicyError) as caught:
        apply_policy(_spec())
    assert caught.value.family == "ipv4"
    assert caught.value.exit_code == 1
    # The not-yet-applied family also receives the fail-closed fallback.
    v6_fallback = [
        data
        for tool, data in calls
        if tool == "ip6tables-restore" and data and b":INPUT DROP" in data
    ]
    assert v6_fallback, "expected a fail-closed fallback restore for ipv6"


def test_fail_closed_fallback_replaces_rather_than_appends(monkeypatch) -> None:
    """A34/f005: the fail-closed restore must flush the table (no
    --noflush): a sibling family may already carry the target policy's
    ACCEPT rules, and leaving them ahead of the DROP defaults would not
    be closed. The normal policy restore keeps --noflush."""
    argv_log: list[list[str]] = []

    def fake_run(argv, **kwargs):
        argv_log.append(list(argv))
        tool = argv[0]
        if tool.endswith("-save"):
            return _Result(0, stdout=b"")
        if tool == "ip6tables-restore" and kwargs.get("input") and b"ipv6-icmp" in kwargs["input"]:
            return _Result(2, stderr=b"boom")
        return _Result(0)

    monkeypatch.setattr(network_policy.subprocess, "run", fake_run)
    with pytest.raises(NetworkPolicyError):
        apply_policy(_spec())
    restores = [a for a in argv_log if a[0].endswith("-restore")]
    normal = [a for a in restores if "--noflush" in a]
    fallback = [a for a in restores if "--noflush" not in a]
    assert normal, "the normal policy install keeps --noflush semantics"
    assert len(fallback) == 2  # both families get the replacing fallback
