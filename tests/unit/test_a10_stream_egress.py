from __future__ import annotations

import subprocess

import pytest
from cbrowser.supervisor import network_policy as np_module
from cbrowser.supervisor.network_policy import (
    NetworkPolicyError,
    NetworkPolicySpec,
    apply_policy,
    render_ip6tables_rules,
    render_iptables_rules,
)

MUX = 30025
GATEWAY_V4 = ("10.251.7.254", 8443)
GATEWAY_V6 = ("fdcb::254", 8443)
DNS_V4 = ("10.251.7.253", 53)
DNS_V6 = ("fdcb::253", 53)

V4_LOCAL = ["169.254.0.0/16"]
V6_LOCAL = ["fe80::/10"]


def _stream_spec() -> NetworkPolicySpec:
    # t054: no LAN media allowance exists anymore; the stream media set
    # is link-local only.
    return NetworkPolicySpec(
        role="stream",
        udp_mux_port=MUX,
        allowed_tcp=[GATEWAY_V4, GATEWAY_V6],
        allowed_udp=[DNS_V4, DNS_V6],
    )


def _browser_spec() -> NetworkPolicySpec:
    return NetworkPolicySpec(
        role="browser",
        allowed_tcp=[("1.1.1.1", 443)],
    )


def _media_destinations(rules: str) -> list[str]:
    destinations: list[str] = []
    for line in rules.splitlines():
        if line.startswith("-A OUTPUT") and f"--sport {MUX}" in line and "-j ACCEPT" in line:
            tokens = line.split()
            assert "-d" in tokens
            destinations.append(tokens[tokens.index("-d") + 1])
    return destinations


def test_browser_vs_stream_default_output_policy() -> None:
    browser = _browser_spec()
    stream = _stream_spec()
    for render in (render_iptables_rules, render_ip6tables_rules):
        browser_rules = render(browser)
        stream_rules = render(stream)
        assert "-A OUTPUT -j ACCEPT" in browser_rules
        assert "-A OUTPUT -j DROP" not in browser_rules
        assert "-A OUTPUT -j ACCEPT" not in stream_rules
        assert "-A OUTPUT -j DROP" in stream_rules


def test_browser_public_egress_still_accepted() -> None:
    browser = _browser_spec()
    v4 = render_iptables_rules(browser)
    v6 = render_ip6tables_rules(browser)
    assert "-A OUTPUT -p tcp -d 1.1.1.1 --dport 443 -j ACCEPT" in v4
    assert "-A OUTPUT -j ACCEPT" in v4
    assert "-A OUTPUT -j ACCEPT" in v6


def test_browser_has_no_media_rules() -> None:
    for render in (render_iptables_rules, render_ip6tables_rules):
        assert f"--sport {MUX}" not in render(_browser_spec())


def test_stream_control_endpoints_allowed_both_families() -> None:
    spec = _stream_spec()
    v4 = render_iptables_rules(spec)
    v6 = render_ip6tables_rules(spec)
    assert "-A OUTPUT -p tcp -d 10.251.7.254 --dport 8443 -j ACCEPT" in v4
    assert "-A OUTPUT -p udp -d 10.251.7.253 --dport 53 -j ACCEPT" in v4
    assert "-A OUTPUT -p tcp -d fdcb::254 --dport 8443 -j ACCEPT" in v6
    assert "-A OUTPUT -p udp -d fdcb::253 --dport 53 -j ACCEPT" in v6


def test_stream_has_explicit_terminal_drop_and_no_unconditional_accept() -> None:
    spec = _stream_spec()
    for render in (render_iptables_rules, render_ip6tables_rules):
        rules = render(spec)
        assert "-A OUTPUT -j ACCEPT" not in rules
        assert "-A OUTPUT -j DROP" in rules


def test_stream_local_media_networks_are_link_local_only() -> None:
    spec = _stream_spec()
    assert _media_destinations(render_iptables_rules(spec)) == V4_LOCAL
    assert _media_destinations(render_ip6tables_rules(spec)) == V6_LOCAL


def test_stream_media_rules_limited_to_destination_networks() -> None:
    spec = _stream_spec()
    for render in (render_iptables_rules, render_ip6tables_rules):
        rules = render(spec)
        assert f"-A OUTPUT -p udp --sport {MUX} -j ACCEPT" not in rules
        assert "-A OUTPUT -p tcp -j ACCEPT" not in rules
        assert "-A OUTPUT -p udp -j ACCEPT" not in rules
        assert "-A OUTPUT -j ACCEPT" not in rules
        for dest in _media_destinations(rules):
            assert dest not in ("0.0.0.0/0", "::/0")
        assert rules.rstrip().endswith("COMMIT")


def test_stream_media_rules_precede_blocked_drops() -> None:
    spec = _stream_spec()
    for render in (render_iptables_rules, render_ip6tables_rules):
        lines = render(spec).splitlines()
        media_idx = [
            i for i, line in enumerate(lines)
            if f"--sport {MUX}" in line and "-j ACCEPT" in line
        ]
        drop_idx = [
            i for i, line in enumerate(lines)
            if line.startswith("-A OUTPUT -d") and line.endswith("-j DROP")
        ]
        assert media_idx
        assert drop_idx
        assert max(media_idx) < min(drop_idx)
        assert max(drop_idx) < lines.index("-A OUTPUT -j DROP")


def test_stream_install_failure_keeps_gate_closed(monkeypatch) -> None:
    calls: list[tuple[str, bytes | None]] = []

    def fake_run(argv, **kwargs):
        tool = argv[0]
        data = kwargs.get("input") or b""
        calls.append((tool, data))
        if tool.endswith("-save"):
            return subprocess.CompletedProcess(argv, 0, stdout=b"")
        if tool.endswith("-restore") and str(MUX).encode() in data:
            return subprocess.CompletedProcess(argv, 3, stderr=b"denied")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(np_module.subprocess, "run", fake_run)
    with pytest.raises(NetworkPolicyError):
        apply_policy(_stream_spec())
    fallbacks = [
        data
        for tool, data in calls
        if tool.endswith("-restore")
        and data
        and b":OUTPUT DROP" in data
        and b"-A OUTPUT -j ACCEPT" not in data
        and str(MUX).encode() not in data
    ]
    assert len(fallbacks) == 2
