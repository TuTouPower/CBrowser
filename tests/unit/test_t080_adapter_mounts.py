"""t080: DockerAdapter mount contracts under typed volume subpath mounts.

These replace the scenarios removed from test_a36_socket_root,
test_supervisor_selkies_token_isolation, test_supervisor_selkies_tokens,
test_t035_proxy_runtime, test_t041_font_runtime and
test_t052_supervisor_probe (see the NOTEs there): the behavioral
assertions are the same, expressed against the `mounts` list of typed
Mount dicts (Source = named volume, VolumeOptions.Subpath, Target,
ReadOnly) that ADR 029 substitutes for the host bind-mount dict.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from cbrowser.supervisor.selkies_tokens import SelkiesTokens
from cbrowser.runtime_agent import socket_root as sr
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.domain.proxy_endpoint import parse_proxy_link

BROWSER = "sha256:" + "a" * 64
STREAM = "sha256:" + "b" * 64
PREFIX = "cbrowser-t005"
DATA_VOL = f"{PREFIX}-data"
FONTS_VOL = f"{PREFIX}-fonts"
RUNTIME_VOL = f"{PREFIX}-runtime"


def _by_target(mounts: list) -> dict[str, dict]:
    return {m["Target"]: m for m in mounts}


def _adapter(tmp_path: Path, client=None) -> DockerAdapter:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True, exist_ok=True)
    (engine / "geoip").mkdir(parents=True, exist_ok=True)
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=client if client is not None else MagicMock(),
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
        deployment_instance_id="dep-test",
    )


def _stub_agent(adapter) -> None:
    """t082: stub the Policy Agent seam (in-process rig) like the
    install seam; lifecycle coverage lives in
    test_t082_adapter_policy_agents."""
    from tests.unit.policy_agent_test_support import PolicyAgentTestRig

    rig = PolicyAgentTestRig()
    rig.executor.resolutions.update(
        {"proxy.example.com": ["93.184.216.34"],
         "host.docker.internal": ["192.168.65.254"]}
    )
    rig.install_on(adapter)
    rig.stub_ensure(adapter)
    adapter._test_rig = rig  # type: ignore[attr-defined]


def _gate(root: Path, role: str) -> Path:
    return root / "control" / "gates" / "p1" / "inst" / role


# --- a36: the Browser mounts the shared agent socket root ---------------


@pytest.mark.asyncio
async def test_browser_container_mounts_shared_socket_root(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    (data_root / "engine_cache" / "geoip").mkdir(parents=True)
    socket_root = tmp_path / "socks"
    validator = PathValidator(data_root, socket_root=socket_root)
    adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=data_root / "engine_cache",
        docker_client=MagicMock(),
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
        deployment_instance_id="dep-test",
    )
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=data_root / "gate")
    adapter._validate_cache_paths = MagicMock()
    adapter._install_network_policy = MagicMock()
    _stub_agent(adapter)
    adapter.remember_profile_number("p1", 1)
    dirs = adapter.prepare_profile_directories("p1")
    (dirs["runtime"] / "snapshot.json").write_text(
        json.dumps({"version": 1, "config": {}}), encoding="utf-8"
    )
    container = MagicMock()
    container.id = "cid"
    adapter.client.containers.run = MagicMock(return_value=container)
    await adapter.start_browser_container(
        profile_id="p1",
        runtime_instance_id="i1",
        snapshot_json_path=dirs["runtime"] / "snapshot.json",
    )
    kwargs = adapter.client.containers.run.call_args.kwargs
    expected_dir = sr.agent_socket_dir(socket_root, "p1", "i1")
    mount = _by_target(kwargs["mounts"])[str(expected_dir)]
    assert mount["Source"] == RUNTIME_VOL
    assert mount["VolumeOptions"]["Subpath"] == (
        "sockets/" + expected_dir.relative_to(socket_root).as_posix()
    )
    assert mount["ReadOnly"] is False
    assert kwargs["environment"][sr.AGENT_SOCKET_ROOT_ENV] == str(socket_root)


# --- selkies token isolation ---------------------------------------------


@pytest.mark.asyncio
async def test_browser_container_mounts_never_include_secret_directory(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    adapter.remember_profile_number("p1", 1)
    dirs = adapter.prepare_profile_directories("p1")
    snapshot_path = dirs["runtime"] / "snapshot.json"
    snapshot_path.write_text(json.dumps({"version": 1, "config": {}}), encoding="utf-8")
    _c = MagicMock()
    _c.id = "cid-run"
    adapter.client.containers.run.return_value = _c
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(
        return_value=_gate(tmp_path / "data", "browser")
    )
    adapter._validate_cache_paths = MagicMock()
    adapter._resolved_endpoint = MagicMock(return_value=[])
    adapter._install_network_policy = MagicMock()
    _stub_agent(adapter)

    await adapter.start_browser_container(
        profile_id="p1",
        runtime_instance_id="inst_1",
        snapshot_json_path=snapshot_path,
    )

    mounts = adapter.client.containers.run.call_args.kwargs["mounts"]
    # The runtime tree is mounted; the secret directory (runtime volume
    # subpath .secrets/p1) is never mounted, in whole or in part, and no
    # mount is a parent of it.
    assert "/run/cbrowser/runtime" in _by_target(mounts)
    for mount in mounts:
        subpath = mount["VolumeOptions"]["Subpath"]
        assert subpath != ".secrets/p1"
        assert not subpath.startswith(".secrets/p1/")
        if subpath:
            # No mount may be a parent of the secret directory either.
            assert not ".secrets/p1".startswith(subpath.rstrip("/") + "/")


async def _start_stream(adapter: DockerAdapter, tmp_path: Path):
    adapter.remember_profile_number("p1", 1)
    dirs = adapter.prepare_profile_directories("p1")
    (dirs["x11"] / "X99").touch()
    (dirs["runtime"] / "Xauthority").touch()
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    agent_secret = secret_dir / "agent_secret"
    agent_secret.write_text("agent_secret_test", encoding="utf-8")
    agent_secret.chmod(0o600)
    tokens_path = secret_dir / "selkies_tokens.json"
    SelkiesTokens.generate().write_credentials_file(tokens_path)
    adapter.client.api.inspect_container.return_value = {
        "Config": {
            "Hostname": "b-host",
            "Labels": {"com.cbrowser.config-version": "1"},
        }
    }
    stream_container = MagicMock()
    stream_container.id = "cid-stream"
    adapter.client.containers.run.return_value = stream_container
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(
        return_value=_gate(tmp_path / "data", "stream")
    )
    adapter._resolved_endpoint = MagicMock(return_value=[("127.0.0.1", 18097)])
    adapter._install_network_policy = MagicMock()
    _stub_agent(adapter)
    await adapter.start_stream_container(
        profile_id="p1",
        runtime_instance_id="inst_1",
        browser_container_name="cbrowser-p1-browser",
        udp_mux_port=30006,
        agent_secret_path=agent_secret,
        selkies_tokens_path=tokens_path,
    )
    return adapter.client.containers.run.call_args.kwargs


@pytest.mark.asyncio
async def test_stream_container_mounts_token_from_secret_directory(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    kwargs = await _start_stream(adapter, tmp_path)
    mounts = _by_target(kwargs["mounts"])
    tokens_mount = mounts["/tmp/selkies_credentials.json"]
    assert tokens_mount["Source"] == RUNTIME_VOL
    assert tokens_mount["VolumeOptions"]["Subpath"] == ".secrets/p1/selkies_tokens.json"
    assert tokens_mount["ReadOnly"] is True
    secret_mount = mounts["/tmp/secret.txt"]
    assert secret_mount["VolumeOptions"]["Subpath"] == ".secrets/p1/agent_secret"
    assert secret_mount["ReadOnly"] is True
    # Stream receives no Profile, Artifact or font mounts at all.
    for mount in kwargs["mounts"]:
        assert mount["Source"] in (RUNTIME_VOL,)
    assert kwargs["environment"]["CBROWSER_SELKIES_CREDENTIALS_FILE"] == (
        "/tmp/selkies_credentials.json"
    )


# --- t035: proxy credentials mount + egress resolution --------------------


@pytest.mark.asyncio
async def test_browser_container_mounts_credentials_read_only_and_resolves_egress(
    tmp_path: Path,
) -> None:
    from tests.unit.test_t035_proxy_runtime import _write_creds

    root = (tmp_path / "data").resolve()
    (root / "engine_cache" / "geoip").mkdir(parents=True)
    adapter = DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=root / "engine_cache",
        docker_client=MagicMock(),
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
        deployment_instance_id="dep-test",
    )
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=root / "gate")
    adapter._validate_cache_paths = MagicMock()
    # t082: resolution seam is the Policy Agent resolve; the stub
    # records the URL and returns the same fixed answer as before.
    adapter._resolve_via_agent = MagicMock(return_value=[("1.2.3.4", 1080)])
    adapter._install_network_policy = MagicMock()
    _stub_agent(adapter)
    adapter.remember_profile_number("p1", 1)
    dirs = adapter.prepare_profile_directories("p1")
    (dirs["runtime"] / "snapshot.json").write_text(
        json.dumps({"version": 1, "config": {"proxy_id": "px1", "geoip": True}}),
        encoding="utf-8",
    )
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    creds = secret_dir / "proxy_credentials.json"
    _write_creds(creds)
    container = MagicMock()
    container.id = "cid"
    adapter.client.containers.run = MagicMock(return_value=container)

    await adapter.start_browser_container(
        profile_id="p1",
        runtime_instance_id="inst_1",
        snapshot_json_path=dirs["runtime"] / "snapshot.json",
    )
    mounts = _by_target(adapter.client.containers.run.call_args.kwargs["mounts"])
    creds_mount = mounts["/run/cbrowser/proxy_credentials.json"]
    assert creds_mount["Source"] == RUNTIME_VOL
    assert (
        creds_mount["VolumeOptions"]["Subpath"]
        == ".secrets/p1/proxy_credentials.json"
    )
    assert creds_mount["ReadOnly"] is True
    assert adapter._resolve_via_agent.call_args.args[1] == (
        "socks5://proxy.example.com:1080"
    )
    policy = adapter._install_network_policy.call_args.args[1]
    assert policy["role"] == "browser"
    assert policy["proxy_enforced"] is True
    assert policy["allowed_udp"] == [("127.0.0.11", 53)]
    assert adapter.client.containers.run.call_args.kwargs["extra_hosts"] is None


# --- t041: platform font set mounts ----------------------------------------


async def _start_browser_with_config(tmp_path: Path, config: dict) -> list:
    root = (tmp_path / "data").resolve()
    (root / "engine_cache" / "geoip").mkdir(parents=True)
    adapter = DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=root / "engine_cache",
        docker_client=MagicMock(),
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
        deployment_instance_id="dep-test",
    )
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=root / "gate")
    adapter._validate_cache_paths = MagicMock()
    adapter._install_network_policy = MagicMock()
    _stub_agent(adapter)
    adapter.remember_profile_number("p1", 1)
    dirs = adapter.prepare_profile_directories("p1")
    (dirs["runtime"] / "snapshot.json").write_text(
        json.dumps({"version": 1, "config": config}), encoding="utf-8"
    )
    container = MagicMock()
    container.id = "cid"
    adapter.client.containers.run = MagicMock(return_value=container)
    await adapter.start_browser_container(
        profile_id="p1",
        runtime_instance_id="inst_1",
        snapshot_json_path=dirs["runtime"] / "snapshot.json",
    )
    return adapter.client.containers.run.call_args.kwargs["mounts"]


@pytest.mark.asyncio
async def test_browser_container_mounts_font_set_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.unit.test_t041_font_runtime import _make_font_set

    fonts_root, set_id = _make_font_set(tmp_path)
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(fonts_root))
    mounts = await _start_browser_with_config(
        tmp_path,
        {
            "geoip": True,
            "fingerprint_platform": "windows",
            "font_set_id": set_id,
        },
    )
    font_mount = _by_target(mounts)[f"/run/cbrowser/fonts/windows/{set_id}"]
    assert font_mount["Source"] == FONTS_VOL
    assert font_mount["VolumeOptions"]["Subpath"] == f"windows/{set_id}"
    assert font_mount["ReadOnly"] is True
    # The fonts root itself is never mounted.
    assert all(
        m["VolumeOptions"]["Subpath"] for m in mounts if m["Source"] == FONTS_VOL
    )


@pytest.mark.asyncio
async def test_browser_container_no_font_mount_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(tmp_path / "fonts"))
    mounts = await _start_browser_with_config(
        tmp_path,
        {"geoip": True, "fingerprint_platform": "windows", "font_set_id": None},
    )
    font_targets = [
        m["Target"]
        for m in mounts
        if str(m["Target"]).startswith("/run/cbrowser/fonts/")
    ]
    assert font_targets == []


# --- t052: egress probe helper mounts --------------------------------------


def test_stream_ports_map_udp_mux_to_loopback() -> None:
    # Carried from the removed test_container_spec_stream_specs (see the
    # NOTE in test_refactor_behavior_equivalence.py): the stream UDP
    # mux port is published on loopback only.
    from cbrowser.supervisor.container_spec import stream_ports

    assert stream_ports(30006) == {"30006/udp": ("127.0.0.1", 30006)}


def test_probe_helper_uses_browser_policy_and_returns_full_observation(
    tmp_path: Path,
) -> None:
    from tests.unit.test_t052_supervisor_probe import _adapter as probe_adapter
    from tests.unit.test_t052_supervisor_probe import _probe_kwargs

    adapter, fake, calls, _root = probe_adapter(tmp_path)
    endpoint = parse_proxy_link("http://user:pw@proxy.example.com:8080")
    outcome = adapter.run_egress_probe(
        proxy_id="px-1",
        endpoint=endpoint,
        credentials={"password": "pw", "credential_revision": 1},
    )
    assert outcome.egress_ip == "203.0.113.7"
    assert outcome.country_code == "JP"
    assert outcome.latency_ms >= 1

    probe = _probe_kwargs(calls, "time.sleep")
    assert probe["network"].startswith("cbrowser-t005-probe-net-")
    assert probe["extra_hosts"] is None
    assert probe["labels"]["com.cbrowser.role"] == "egress-probe"
    assert probe["labels"]["com.cbrowser.managed-by"] == "supervisor"
    mounts = _by_target(probe["mounts"])
    assert mounts["/data/engine-cache/geoip"]["ReadOnly"] is True
    creds_mount = mounts["/run/cbrowser/runtime/proxy_credentials.json"]
    assert creds_mount["ReadOnly"] is True
    # Probe credentials are written per-probe under the data volume's
    # control/probe/<probe_id> directory (pre-existing layout).
    assert creds_mount["Source"] == DATA_VOL
    assert creds_mount["VolumeOptions"]["Subpath"].startswith("control/probe/")
    assert creds_mount["VolumeOptions"]["Subpath"].endswith(
        "/proxy_credentials.json"
    )
    agent_kwargs = _probe_kwargs(calls, "policy_agent")
    assert agent_kwargs["network_mode"] == "container:fake-probe-id"
    installed = adapter._test_rig.executor.installed  # type: ignore[attr-defined]
    assert len(installed) == 1
    policy_doc = installed[0][0]
    assert policy_doc.role == "browser"
    assert policy_doc.proxy_enforced is True
    assert policy_doc.allowed_tcp == [("93.184.216.34", 8080)]
    assert policy_doc.allowed_udp == [("127.0.0.11", 53)]
    assert all(c.removed for c in fake.containers.created)
    assert all(n.removed for n in fake.networks.created)


# --- _runtime_policy_ready with named-volume subpath mounts ---


def _gate_container(
    *,
    profile: str = "p1",
    instance: str = "inst1",
    role: str = "browser",
    subpath: str = "gates/p1/inst1/browser_abc123",
    volume_name: str = RUNTIME_VOL,
    mount_type: str = "volume",
    rw: bool = False,
    read_only: bool = True,
    include_host_mount: bool = True,
    include_active_mount: bool = True,
):
    from types import SimpleNamespace

    active_mounts = (
        [
            {
                "Type": mount_type,
                "Name": volume_name,
                "Source": f"/var/lib/docker/volumes/{volume_name}/_data",
                "Destination": "/run/cbrowser_policy",
                "RW": rw,
            }
        ]
        if include_active_mount
        else []
    )
    host_mounts = (
        [
            {
                "Type": mount_type,
                "Source": volume_name,
                "Target": "/run/cbrowser_policy",
                "ReadOnly": read_only,
                "VolumeOptions": {"Subpath": subpath} if subpath is not None else {},
            }
        ]
        if include_host_mount
        else []
    )
    return SimpleNamespace(
        labels={
            "com.cbrowser.network-policy": "v1",
            "com.cbrowser.profile-id": profile,
            "com.cbrowser.role": role,
        },
        attrs={
            "Config": {
                "Env": [f"CBROWSER_RUNTIME_INSTANCE_ID={instance}"],
                "Entrypoint": [
                    "python3",
                    "/run/cbrowser_policy/startup_gate.py",
                    "--instance-id",
                    instance,
                    "--role",
                    role,
                ],
            },
            "Mounts": active_mounts,
            "HostConfig": {"Mounts": host_mounts},
        },
    )


def test_runtime_policy_ready_accepts_named_volume_subpath_gate(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    gate_dir = (
        adapter.validator.data_root
        / "control"
        / "gates"
        / "p1"
        / "inst1"
        / "browser_abc123"
    )
    gate_dir.mkdir(parents=True)
    (gate_dir / "ready.json").write_text(
        json.dumps({"instance_id": "inst1", "role": "browser", "status": "ready"}),
        encoding="utf-8",
    )
    container = _gate_container()
    assert adapter._runtime_policy_ready(container) is True


def test_runtime_policy_ready_rejects_invalid_volume_mounts_without_crashing(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    gate_dir = (
        adapter.validator.data_root
        / "control"
        / "gates"
        / "p1"
        / "inst1"
        / "browser_abc123"
    )
    gate_dir.mkdir(parents=True)
    ready_file = gate_dir / "ready.json"
    ready_file.write_text(
        json.dumps({"instance_id": "inst1", "role": "browser", "status": "ready"}),
        encoding="utf-8",
    )

    # Missing HostConfig.Mounts subpath (old host-volume Source would trigger PathSecurityError)
    assert adapter._runtime_policy_ready(_gate_container(include_host_mount=False)) is False
    # Bind mount rejected
    assert adapter._runtime_policy_ready(_gate_container(mount_type="bind")) is False
    # Wrong volume rejected
    assert adapter._runtime_policy_ready(_gate_container(volume_name="wrong-vol")) is False
    # Writable mount rejected
    assert adapter._runtime_policy_ready(_gate_container(rw=True)) is False
    assert adapter._runtime_policy_ready(_gate_container(read_only=False)) is False
    # Subpath traversal / wrong role rejected
    assert (
        adapter._runtime_policy_ready(
            _gate_container(subpath="gates/p1/inst1/../inst2/browser_abc123")
        )
        is False
    )
    assert (
        adapter._runtime_policy_ready(
            _gate_container(subpath="gates/p1/inst1/stream_abc123")
        )
        is False
    )
    # Missing active mount entry rejected
    assert adapter._runtime_policy_ready(_gate_container(include_active_mount=False)) is False

    # Symlink ready.json rejected
    outside = tmp_path / "outside.json"
    outside.write_text(ready_file.read_text(encoding="utf-8"), encoding="utf-8")
    ready_file.unlink()
    ready_file.symlink_to(outside)
    assert adapter._runtime_policy_ready(_gate_container()) is False
