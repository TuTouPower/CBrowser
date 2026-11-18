"""Unit tests for unified Profile egress planning, NetworkPolicy parity, and SDK proxy= integration."""

from __future__ import annotations

import json
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig
from cbrowser.shared.egress_plan import (
    DOCKER_EMBEDDED_DNS,
    PROXY_CREDENTIALS_CHANGED,
    PROXY_HARDENING_ARGS,
    ProxyCredentialsChangedError,
    derive_supervisor_egress_plan,
    format_proxy_url,
    probe_egress_plan,
    resolve_runtime_egress_plan,
)
from cbrowser.supervisor.network_policy import (
    NetworkPolicySpec,
    render_ip6tables_rules,
    render_iptables_rules,
)


def _write_creds(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)


@pytest.mark.parametrize("scheme", ["http", "https", "socks5"])
def test_format_proxy_url_supports_auth_and_special_chars_for_all_schemes(
    scheme: str,
) -> None:
    url = format_proxy_url(
        {
            "scheme": scheme,
            "host": "proxy.example.com",
            "port": 8080,
            "username": "u@domain",
            "password": "p@ss:w=rd%1!/#?",
        }
    )
    assert url == f"{scheme}://u%40domain:p%40ss%3Aw%3Drd%251%21%2F%23%3F@proxy.example.com:8080"


def test_format_proxy_url_brackets_ipv6_and_omits_auth_when_requested() -> None:
    creds = {
        "scheme": "http",
        "host": "fd00:22::10",
        "port": 18080,
        "username": "alice",
        "password": "secret",
    }
    assert format_proxy_url(creds, include_auth=True) == "http://alice:secret@[fd00:22::10]:18080"
    assert format_proxy_url(creds, include_auth=False) == "http://[fd00:22::10]:18080"


def test_resolve_runtime_egress_plan_direct_vs_proxied(tmp_path: Path) -> None:
    direct = resolve_runtime_egress_plan(None, None, tmp_path / "missing.json")
    assert direct.mode == "direct"
    assert direct.proxy_enforced is False
    assert direct.proxy_url is None
    assert direct.extra_browser_args == ()
    assert direct.to_network_policy_spec([]) == {
        "role": "browser",
        "allowed_tcp": [],
        "allowed_udp": [],
        "udp_mux_port": None,
        "proxy_enforced": False,
    }

    creds_path = tmp_path / "proxy_credentials.json"
    _write_creds(
        creds_path,
        {
            "scheme": "http",
            "host": "203.0.113.10",
            "port": 18080,
            "username": "alice",
            "password": "s3cr3t",
            "credential_revision": 4,
        },
    )
    proxied = resolve_runtime_egress_plan("px_1", 4, creds_path)
    assert proxied.mode == "proxy"
    assert proxied.proxy_enforced is True
    assert proxied.proxy_url == "http://alice:s3cr3t@203.0.113.10:18080"
    assert proxied.upstream_url == "http://203.0.113.10:18080"
    assert proxied.needs_proxy_dns is False
    assert proxied.extra_browser_args == PROXY_HARDENING_ARGS
    assert proxied.to_network_policy_spec([("203.0.113.10", 18080)]) == {
        "role": "browser",
        "allowed_tcp": [("203.0.113.10", 18080)],
        "allowed_udp": [],
        "udp_mux_port": None,
        "proxy_enforced": True,
    }


def test_derive_supervisor_egress_plan_fails_closed_on_missing_or_corrupt_creds(
    tmp_path: Path,
) -> None:
    missing = derive_supervisor_egress_plan(
        has_proxy=True, creds_path=tmp_path / "absent.json"
    )
    assert missing.mode == "proxy"
    assert missing.proxy_enforced is True
    assert missing.upstream_url is None
    assert missing.to_network_policy_spec([]) == {
        "role": "browser",
        "allowed_tcp": [],
        "allowed_udp": [],
        "udp_mux_port": None,
        "proxy_enforced": True,
    }


def test_domain_proxy_vs_literal_ip_dns_policy_for_browser_and_probe() -> None:
    domain_plan = probe_egress_plan("http", "proxy.example.com", 8080)
    assert domain_plan.needs_proxy_dns is True
    assert domain_plan.to_network_policy_spec([("93.184.216.34", 8080)]) == {
        "role": "browser",
        "allowed_tcp": [("93.184.216.34", 8080)],
        "allowed_udp": [DOCKER_EMBEDDED_DNS],
        "udp_mux_port": None,
        "proxy_enforced": True,
    }

    ip_plan = probe_egress_plan("https", "fd00:22::10", 18443)
    assert ip_plan.needs_proxy_dns is False
    assert ip_plan.to_network_policy_spec([("fd00:22::10", 18443)]) == {
        "role": "browser",
        "allowed_tcp": [("fd00:22::10", 18443)],
        "allowed_udp": [],
        "udp_mux_port": None,
        "proxy_enforced": True,
    }


def test_network_policy_proxy_enforced_blocks_output_in_both_ip_families() -> None:
    spec = NetworkPolicySpec(
        role="browser",
        allowed_tcp=[("203.0.113.10", 18080), ("fd00:22::10", 18080)],
        allowed_udp=[],
        proxy_enforced=True,
    )
    v4 = render_iptables_rules(spec)
    v6 = render_ip6tables_rules(spec)

    assert "-A OUTPUT -p tcp -d 203.0.113.10 --dport 18080 -j ACCEPT" in v4
    assert "fd00:22::10" not in v4
    assert v4.splitlines()[-2] == "-A OUTPUT -j DROP"

    assert "-A OUTPUT -p tcp -d fd00:22::10 --dport 18080 -j ACCEPT" in v6
    assert "203.0.113.10" not in v6
    assert v6.splitlines()[-2] == "-A OUTPUT -j DROP"


@pytest.mark.asyncio
async def test_browser_runner_passes_sdk_proxy_kwarg_and_hardening_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cbrowser.runtime_agent.runner as runner_mod

    run_dir = tmp_path / "run"
    user_dir = tmp_path / "profile"
    run_dir.mkdir()
    user_dir.mkdir()
    snap_path = run_dir / "snapshot.json"
    cfg = ProfileConfig(name="p1", proxy_id="px_http", geoip=False)
    snap = ConfigVersionSnapshot(
        id="snap_1",
        profile_id="prof_1",
        version=1,
        config=cfg.model_dump(),
        proxy_credential_revision=5,
        created_at="2026-11-15T00:00:00+00:00",
    )
    snap_path.write_text(snap.model_dump_json(), encoding="utf-8")

    creds_path = tmp_path / "proxy_credentials.json"
    _write_creds(
        creds_path,
        {
            "scheme": "http",
            "host": "203.0.113.20",
            "port": 18080,
            "username": "alice",
            "password": "p@ss:w=rd%1!/#?",
            "credential_revision": 5,
        },
    )

    monkeypatch.setattr(runner_mod, "PROXY_CREDENTIALS_PATH", creds_path)
    runner = runner_mod.BrowserRunner(
        profile_id="prof_1",
        runtime_instance_id="inst_1",
        config_snapshot_path=snap_path,
        run_dir=run_dir,
        user_data_dir=user_dir,
        engine_build="146.0.7680.177.3",
    )

    wrapper = tmp_path / "chrome-wrapper"
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(runner, "resolve_engine_binary", lambda: wrapper)
    monkeypatch.setattr(runner, "setup_pulse", lambda: (run_dir / "pulse.sock", run_dir / "cookie"))
    monkeypatch.setattr(runner, "setup_display", lambda width, height: run_dir / "Xauth")
    monkeypatch.setattr(runner, "_resolve_browser_version", AsyncMock(return_value=("Chrome/146", "UA")))
    monkeypatch.setattr(runner, "_configure_window", AsyncMock())
    monkeypatch.setattr(
        runner_mod,
        "prepare_profile_fontconfig",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        runner_mod,
        "run_search_defaults_initialization",
        AsyncMock(return_value=SimpleNamespace(state="applied", error_kind=None)),
    )

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/1"}
            ).encode("utf-8")

    monkeypatch.setattr(runner_mod.urllib.request, "urlopen", lambda *_a, **_k: _Resp())

    guard = SimpleNamespace(start=AsyncMock(return_value=9333), close=AsyncMock())
    monkeypatch.setattr(runner_mod, "CdpGuard", lambda *_a, **_k: guard)

    captured: dict = {}

    class _FakeContext:
        pages: list = []

        async def close(self) -> None:
            return None

    async def fake_launch(**kwargs):
        import os

        captured.update(kwargs)
        (run_dir / "chrome.pid").write_text(str(os.getpid()), encoding="utf-8")
        (user_dir / "DevToolsActivePort").write_text(
            "9222\n/devtools/browser/1\n", encoding="utf-8"
        )
        return _FakeContext()

    monkeypatch.setattr(runner_mod, "launch_persistent_context_async", fake_launch)

    await runner.start()
    try:
        assert captured["proxy"] == "http://alice:p%40ss%3Aw%3Drd%251%21%2F%23%3F@203.0.113.20:18080"
        args = captured["args"]
        assert not any(a.startswith("--proxy-server=") for a in args)
        for flag in PROXY_HARDENING_ARGS:
            assert flag in args
    finally:
        await runner.stop()


@pytest.mark.asyncio
async def test_browser_runner_fails_closed_before_launch_on_stale_creds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cbrowser.runtime_agent.runner as runner_mod

    run_dir = tmp_path / "run"
    user_dir = tmp_path / "profile"
    run_dir.mkdir()
    user_dir.mkdir()
    snap_path = run_dir / "snapshot.json"
    cfg = ProfileConfig(name="p1", proxy_id="px_1", geoip=True)
    snap = ConfigVersionSnapshot(
        id="snap_1",
        profile_id="prof_1",
        version=1,
        config=cfg.model_dump(),
        proxy_credential_revision=9,
        created_at="2026-11-15T00:00:00+00:00",
    )
    snap_path.write_text(snap.model_dump_json(), encoding="utf-8")

    creds_path = tmp_path / "proxy_credentials.json"
    _write_creds(
        creds_path,
        {
            "scheme": "socks5",
            "host": "203.0.113.20",
            "port": 1080,
            "username": "alice",
            "password": "super_secret_password",
            "credential_revision": 8,
        },
    )
    monkeypatch.setattr(runner_mod, "PROXY_CREDENTIALS_PATH", creds_path)
    launch_mock = AsyncMock()
    monkeypatch.setattr(runner_mod, "launch_persistent_context_async", launch_mock)

    runner = runner_mod.BrowserRunner(
        profile_id="prof_1",
        runtime_instance_id="inst_1",
        config_snapshot_path=snap_path,
        run_dir=run_dir,
        user_data_dir=user_dir,
    )
    with pytest.raises(ProxyCredentialsChangedError) as exc:
        await runner.start()
    assert str(exc.value) == PROXY_CREDENTIALS_CHANGED
    assert "super_secret_password" not in str(exc.value)
    launch_mock.assert_not_called()


def test_start_and_browser_policy_spec_parity_for_proxied_and_direct(
    tmp_path: Path,
) -> None:
    from cbrowser.supervisor.docker_adapter import DockerAdapter
    from cbrowser.supervisor.path_validator import PathValidator

    root = (tmp_path / "data").resolve()
    (root / "engine_cache" / "geoip").mkdir(parents=True)
    adapter = DockerAdapter(
        PathValidator(root),
        root / "engine_cache",
        docker_client=MagicMock(),
        browser_image="sha256:" + "a" * 64,
        stream_image="sha256:" + "b" * 64,
        deployment_instance_id="dep-test",
    )
    # t082: derivation runs through the target's Policy Agent; the
    # upstream here is an IP literal, so no resolution is needed and
    # the in-process rig only records installs.
    from tests.unit.policy_agent_test_support import PolicyAgentTestRig

    rig = PolicyAgentTestRig()
    rig.install_on(adapter)
    container = MagicMock()
    container.id = "cid-parity"
    rig.stub_ensure(adapter)
    adapter.ensure_policy_agent(
        container,
        profile_id="p_parity",
        instance_id="i_parity",
        config_version=1,
        role="browser",
    )

    runtime_dir = adapter.validator.get_runtime_dir("p_parity")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    secret_dir = adapter.validator.get_secret_dir("p_parity")
    secret_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "snapshot.json").write_text(
        json.dumps({"version": 1, "config": {"proxy_id": "px_1"}}),
        encoding="utf-8",
    )
    creds = secret_dir / "proxy_credentials.json"
    _write_creds(
        creds,
        {
            "scheme": "https",
            "host": "203.0.113.50",
            "port": 18080,
            "username": "u",
            "password": "p",
            "credential_revision": 1,
        },
    )

    spec_from_verify = adapter.browser_policy_spec("p_parity", container)
    spec_from_start = adapter._browser_egress_policy(
        container, has_proxy=True, creds_file=creds
    )
    assert spec_from_verify == spec_from_start
    assert spec_from_verify == {
        "role": "browser",
        "allowed_tcp": [("203.0.113.50", 18080)],
        "allowed_udp": [],
        "udp_mux_port": None,
        "proxy_enforced": True,
    }

    # Direct mode parity
    (runtime_dir / "snapshot.json").write_text(
        json.dumps({"version": 2, "config": {"proxy_id": None}}),
        encoding="utf-8",
    )
    creds.unlink()
    direct_verify = adapter.browser_policy_spec("p_parity", container)
    direct_start = adapter._browser_egress_policy(
        container, has_proxy=False, creds_file=creds
    )
    assert direct_verify == direct_start
    assert direct_verify["proxy_enforced"] is False
    assert direct_verify["allowed_tcp"] == []


@pytest.mark.asyncio
async def test_supervisor_core_proxied_policy_drift_triggers_fail_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SupervisorCore + real DockerAdapter.browser_policy_spec + real verify_policy
    detects missing proxy_enforced DROP rules and calls fail_close_container once."""
    import ipaddress
    import httpx

    import cbrowser.supervisor.network_policy as np_module
    from cbrowser.supervisor.address_pool import plan_for_subnet
    from cbrowser.supervisor.core import ActiveSession, SupervisorCore
    from cbrowser.supervisor.docker_adapter import DockerAdapter
    from cbrowser.supervisor.event_forwarder import EventForwarder
    from cbrowser.supervisor.network_policy import (
        rendered_filter_rules,
        verify_policy,
    )
    from cbrowser.supervisor.path_validator import PathValidator
    from cbrowser.supervisor.port_allocator import PortAllocator

    root = (tmp_path / "data").resolve()
    (root / "engine_cache" / "geoip").mkdir(parents=True)
    adapter = DockerAdapter(
        PathValidator(root),
        root / "engine_cache",
        docker_client=MagicMock(),
        browser_image="sha256:" + "a" * 64,
        stream_image="sha256:" + "b" * 64,
        deployment_instance_id="dep-test",
    )

    profile_id = "p_drift"
    instance_id = "inst_drift"
    runtime_dir = adapter.validator.get_runtime_dir(profile_id)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    secret_dir = adapter.validator.get_secret_dir(profile_id)
    secret_dir.mkdir(parents=True, exist_ok=True)
    (secret_dir / "agent_secret.txt").write_text("x" * 40, encoding="utf-8")
    (runtime_dir / "snapshot.json").write_text(
        json.dumps({"version": 1, "config": {"proxy_id": "px_1"}}),
        encoding="utf-8",
    )
    _write_creds(
        secret_dir / "proxy_credentials.json",
        {
            "scheme": "http",
            "host": "203.0.113.50",
            "port": 18080,
            "username": "u",
            "password": "p",
            "credential_revision": 1,
        },
    )

    # t082: seed the Browser's Policy Agent handle as startup left it
    # (policy installed at revision 1), so browser_policy_spec returns
    # the frozen spec; the drift below is in the live rules only.
    from cbrowser.shared.egress_plan import derive_supervisor_egress_plan
    from cbrowser.supervisor.docker_adapter import _PolicyAgentHandle
    from cbrowser.supervisor.network_policy import NetworkPolicySpec as _Spec
    from cbrowser.supervisor.policy_agent_protocol import (
        PolicyAgentIdentity as _Identity,
        policy_spec_digest as _digest,
    )
    from tests.unit.policy_agent_test_support import PolicyAgentTestRig

    _rig = PolicyAgentTestRig()
    _rig.install_on(adapter)
    _plan = derive_supervisor_egress_plan(
        has_proxy=True, creds_path=secret_dir / "proxy_credentials.json"
    )
    _spec = _Spec.model_validate(
        _plan.to_network_policy_spec([("203.0.113.50", 18080)])
    )
    _identity = _Identity(
        deployment_id="dep-test",
        profile_id=profile_id,
        runtime_instance_id="inst_drift",
        config_version=1,
        role="browser",
        target_container_id="c_browser",
    )
    adapter._policy_agents["c_browser"] = _PolicyAgentHandle(
        identity=_identity,
        client=_rig.factory(None, _identity),
        agent_container_id="agent-drift",
        spec=_spec,
        digest=_digest(_spec),
        revision=1,
        upstream_url=_plan.upstream_url,
    )

    plan = plan_for_subnet(ipaddress.ip_network("10.251.7.0/24"))
    browser_c = SimpleNamespace(
        id="c_browser", name="b_drift", status="running", labels={"com.cbrowser.role": "browser"}
    )
    stream_c = SimpleNamespace(
        id="c_stream", name="s_drift", status="running", labels={"com.cbrowser.role": "stream"}
    )

    drifted_live_rules = rendered_filter_rules(
        NetworkPolicySpec(
            role="browser",
            allowed_tcp=[("203.0.113.50", 18080)],
            proxy_enforced=False,
        )
    )
    monkeypatch.setattr(
        np_module, "current_filter_rules", lambda family: drifted_live_rules[family]
    )

    fail_closed_calls: list[str] = []
    adapter.inspect_media_network = MagicMock(  # type: ignore[method-assign]
        return_value={
            "exists": True,
            "conforms": True,
            "plan": plan,
            "gateway_attached_id": "gw_1",
            "gateway_ip": plan.gateway_endpoint,
            "endpoints": {},
        }
    )
    adapter.resolve_gateway_container_id = MagicMock(return_value="gw_1")  # type: ignore[method-assign]
    adapter.get_profile_containers = MagicMock(  # type: ignore[method-assign]
        return_value={"browser": browser_c, "stream": stream_c}
    )
    adapter.stream_policy_spec = MagicMock(return_value={"role": "stream"})  # type: ignore[method-assign]

    def _verify(container, spec):
        if spec.get("role") == "stream":
            return True
        return verify_policy(NetworkPolicySpec.model_validate(spec))

    adapter.verify_container_policy = _verify  # type: ignore[method-assign]
    adapter.fail_close_container = lambda c: fail_closed_calls.append(c.id)  # type: ignore[method-assign]

    gateway = SimpleNamespace(
        agent_registered=AsyncMock(return_value=True),
        registration_status=AsyncMock(
            return_value={
                "profile_id": profile_id,
                "gateway_build_id": "gw-1",
                "agent_build_id": "ag-1",
                "selkies_version": "2.2.1",
                "rejection": None,
                "rejection_runtime_instance_id": None,
            }
        ),
    )
    api = httpx.AsyncClient(
        base_url="http://api.invalid",
        transport=httpx.MockTransport(lambda r: httpx.Response(404)),
    )
    core = SupervisorCore(
        adapter,
        PortAllocator(),
        EventForwarder("http://api.invalid", tmp_path / "spool", client=api),
        api,
        gateway_control=gateway,
        gateway_container_id="gw_1",
    )
    core._sessions[profile_id] = ActiveSession(
        profile_id, instance_id, 1, 30005, "c_browser", "c_stream",
        desired_state="running", observed_state="running",
    )
    scan = {
        "browser": {"status": "running", "instance_id": instance_id},
        "stream": {"status": "running", "instance_id": instance_id},
    }

    await core._converge_session(profile_id, core._sessions[profile_id], scan)
    await core._converge_session(profile_id, core._sessions[profile_id], scan)

    assert fail_closed_calls == ["c_browser"]
    observation = core.get_transport_observation(profile_id)
    assert observation.transport_state == "failed"
    assert observation.last_error == "browser_policy_drift"
