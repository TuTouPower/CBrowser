"""t026 AC-003/AC-004: DockerAdapter fixed-endpoint media networking.

Drives the production adapter against a Docker client double whose
networks behave per d029 (explicit IPAM stored verbatim, connect with
an explicit address). The assertions are on resulting network state,
not on call counts alone.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from cbrowser.supervisor.address_pool import media_network_labels, plan_for_subnet
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.network_spec import network_labels
from cbrowser.supervisor.path_validator import PathValidator
from docker.errors import NotFound

import ipaddress

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"
PREFIX = "cbrowser-t005"
PROFILE = "prof_net"
NET_NAME = f"{PREFIX}-net-{PROFILE}"


class _FakeNetwork:
    def __init__(self, name: str, labels: dict, ipam_config: list) -> None:
        self.name = name
        self.attrs = {
            "Labels": labels,
            "IPAM": {"Config": ipam_config},
            "Containers": {},
        }

    def reload(self) -> None:
        pass

    def connect(self, container, ipv4_address: str | None = None) -> None:
        ip = ipv4_address or "10.251.0.2"
        self.attrs["Containers"][container.id] = {"IPv4Address": f"{ip}/24"}
        container.attrs["NetworkSettings"]["Networks"][self.name] = {
            "IPAddress": ip
        }

    def disconnect(self, container) -> None:
        self.attrs["Containers"].pop(container.id, None)
        container.attrs["NetworkSettings"]["Networks"].pop(self.name, None)

    def remove(self) -> None:
        self.removed = True


class _FakeNetworks:
    def __init__(self) -> None:
        self.by_name: dict[str, _FakeNetwork] = {}
        self.created: list[dict] = []

    def get(self, name: str) -> _FakeNetwork:
        if name not in self.by_name:
            raise NotFound(f"network {name} not found")
        return self.by_name[name]

    def list(self) -> list[_FakeNetwork]:
        return list(self.by_name.values())

    def create(self, name: str, driver=None, ipam=None, labels=None) -> _FakeNetwork:
        config = []
        if ipam is not None:
            for pool_config in ipam.get("Config") or []:
                config.append(
                    {
                        "Subnet": pool_config.get("Subnet"),
                        "IPRange": pool_config.get("IPRange"),
                    }
                )
        network = _FakeNetwork(name, labels or {}, config)
        self.by_name[name] = network
        self.created.append({"name": name, "ipam": ipam, "labels": labels})
        return network


class _FakeContainers:
    def __init__(self) -> None:
        self.by_id: dict[str, SimpleNamespace] = {}

    def get(self, container_id: str) -> SimpleNamespace:
        if container_id not in self.by_id:
            raise NotFound(f"container {container_id} not found")
        return self.by_id[container_id]


def _gateway(container_id: str = "gw_1") -> SimpleNamespace:
    return SimpleNamespace(
        id=container_id,
        name="gateway",
        status="running",
        labels={
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.prefix": PREFIX,
            "com.cbrowser.role": "gateway",
        },
        attrs={"NetworkSettings": {"Networks": {}}},
        reload=lambda: None,
    )


def _adapter(tmp_path, client, **kw) -> DockerAdapter:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    (engine / "geoip").mkdir(parents=True)
    # t069: production always configures a deployment identity, and
    # network ownership is decided by its label alone.
    kw.setdefault("deployment_instance_id", "dep-t026")
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=client,
        browser_image=BROWSER,
        stream_image=STREAM,
        resource_prefix=PREFIX,
        **kw,
    )


def _client() -> SimpleNamespace:
    return SimpleNamespace(networks=_FakeNetworks(), containers=_FakeContainers())


@pytest.mark.asyncio
async def test_create_allocates_explicit_subnet_range_and_labels(tmp_path):
    client = _client()
    adapter = _adapter(tmp_path, client)

    network = await adapter.create_profile_network(PROFILE)

    created = client.networks.created[0]
    pool = created["ipam"]["Config"][0]
    assert pool["Subnet"] == "10.251.0.0/24"
    assert pool["IPRange"] == "10.251.0.0/25"
    assert created["labels"]["com.cbrowser.media-spec"] == "fixed-endpoint-v1"
    assert created["labels"]["com.cbrowser.gateway-endpoint"] == "10.251.0.254"
    assert network.name == NET_NAME

    inspection = adapter.inspect_media_network(PROFILE)
    assert inspection["exists"] is True
    assert inspection["conforms"] is True


@pytest.mark.asyncio
async def test_pre_spec_network_is_not_conforming(tmp_path):
    client = _client()
    client.networks.by_name[NET_NAME] = _FakeNetwork(
        NET_NAME,
        network_labels(PREFIX, PROFILE, deployment_id="dep-t026"),
        [{"Subnet": "172.20.0.0/16", "IPRange": ""}],
    )
    adapter = _adapter(tmp_path, client)

    inspection = adapter.inspect_media_network(PROFILE)
    assert inspection["exists"] is True
    assert inspection["conforms"] is False
    assert inspection["plan"] is None


@pytest.mark.asyncio
async def test_attach_uses_fixed_endpoint_and_repairs_drift(tmp_path):
    client = _client()
    adapter = _adapter(tmp_path, client)
    await adapter.create_profile_network(PROFILE)
    gateway = _gateway()
    client.containers.by_id[gateway.id] = gateway

    result = adapter.attach_profile_infrastructure(PROFILE, gateway.id, 8443)
    assert result["gateway_ip"] == "10.251.0.254"
    assert result["gateway_url"] == "ws://10.251.0.254:8443"

    inspection = adapter.inspect_media_network(PROFILE)
    assert inspection["gateway_attached_id"] == gateway.id

    # Simulate drift: the Gateway now sits at an automatic address.
    network = client.networks.by_name[NET_NAME]
    network.attrs["Containers"][gateway.id] = {"IPv4Address": "10.251.0.2/24"}
    gateway.attrs["NetworkSettings"]["Networks"][NET_NAME] = {
        "IPAddress": "10.251.0.2"
    }
    result = adapter.attach_profile_infrastructure(PROFILE, gateway.id, 8443)
    assert result["gateway_ip"] == "10.251.0.254"


@pytest.mark.asyncio
async def test_attach_refuses_endpoint_held_by_another_container(tmp_path):
    client = _client()
    adapter = _adapter(tmp_path, client)
    await adapter.create_profile_network(PROFILE)
    network = client.networks.by_name[NET_NAME]
    network.attrs["Containers"]["someone_else"] = {
        "IPv4Address": "10.251.0.254/24"
    }
    gateway = _gateway()
    client.containers.by_id[gateway.id] = gateway

    with pytest.raises(DockerSandboxError):
        adapter.attach_profile_infrastructure(PROFILE, gateway.id, 8443)


@pytest.mark.asyncio
async def test_pool_exhaustion_is_explicit_not_random(tmp_path):
    client = _client()
    plan = plan_for_subnet(ipaddress.ip_network("10.251.9.0/24"))
    client.networks.by_name["other-net"] = _FakeNetwork(
        "other-net",
        media_network_labels(network_labels(PREFIX, "other"), plan),
        [{"Subnet": plan.subnet, "IPRange": plan.ip_range}],
    )
    adapter = _adapter(tmp_path, client, media_subnet_pool="10.251.9.0/24")

    with pytest.raises(DockerSandboxError):
        await adapter.create_profile_network(PROFILE)
    assert client.networks.created == []


# --- Round-2 additions: t026_code_f001 contract, t026_test_f003 -----


def _profile_container(container_id: str, role: str, profile: str = PROFILE):
    return SimpleNamespace(
        id=container_id,
        name=f"{PREFIX}-{role}-{profile}",
        status="running",
        labels={
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.prefix": PREFIX,
            "com.cbrowser.profile-id": profile,
            "com.cbrowser.role": role,
        },
        attrs={"NetworkSettings": {"Networks": {}}},
        reload=lambda: None,
    )


def test_get_profile_containers_returns_label_verified_pair(tmp_path):
    # code f001: the production adapter itself must provide the method
    # the Supervisor core calls — a test-double-only method hid a
    # production AttributeError in round 1.
    client = _client()
    adapter = _adapter(tmp_path, client)
    adapter.remember_profile_number(PROFILE, 1)
    browser = _profile_container("c_browser", "browser")
    stream = _profile_container("c_stream", "stream")
    browser.name = adapter.get_browser_container_name(PROFILE)
    stream.name = adapter.get_stream_container_name(PROFILE)
    client.containers.by_id[browser.name] = browser
    client.containers.by_id[stream.name] = stream

    roles = adapter.get_profile_containers(PROFILE)

    assert roles["browser"] is browser
    assert roles["stream"] is stream


def test_get_profile_containers_rejects_foreign_and_missing(tmp_path):
    client = _client()
    adapter = _adapter(tmp_path, client)
    adapter.remember_profile_number(PROFILE, 1)
    foreign = _profile_container("c_foreign", "stream", profile="other_prof")
    stream_name = adapter.get_stream_container_name(PROFILE)
    client.containers.by_id[stream_name] = foreign

    roles = adapter.get_profile_containers(PROFILE)

    assert roles["browser"] is None  # absent reads as missing
    assert roles["stream"] is None  # foreign labels are never adopted


@pytest.mark.asyncio
async def test_attach_rolls_back_only_this_rounds_connections(tmp_path):
    # AC-007 / test f003: the Gateway connects but lands on the wrong
    # address, so the attach fails — the connection made this round is
    # rolled back while the pre-existing Browser endpoint stays.
    client = _client()
    adapter = _adapter(tmp_path, client)
    await adapter.create_profile_network(PROFILE)
    network = client.networks.by_name[NET_NAME]
    browser = _profile_container("c_browser", "browser")
    network.attrs["Containers"][browser.id] = {"IPv4Address": "10.251.0.2/24"}
    browser.attrs["NetworkSettings"]["Networks"][NET_NAME] = {
        "IPAddress": "10.251.0.2"
    }
    gateway = _gateway()

    def _wrong_ip_connect(container, ipv4_address=None):
        network.attrs["Containers"][container.id] = {
            "IPv4Address": "10.251.0.99/24"
        }
        container.attrs["NetworkSettings"]["Networks"][NET_NAME] = {
            "IPAddress": "10.251.0.99"
        }

    network.connect = _wrong_ip_connect
    client.containers.by_id[gateway.id] = gateway

    with pytest.raises(DockerSandboxError):
        adapter.attach_profile_infrastructure(PROFILE, gateway.id, 8443)

    assert gateway.id not in network.attrs["Containers"]
    assert browser.id in network.attrs["Containers"]


@pytest.mark.asyncio
async def test_cleanup_network_refuses_unknown_endpoint(tmp_path):
    # AC-007 / test f003: an endpoint the Supervisor cannot account
    # for blocks network cleanup; the network is left in place.
    client = _client()
    adapter = _adapter(tmp_path, client)
    await adapter.create_profile_network(PROFILE)
    network = client.networks.by_name[NET_NAME]
    mystery = SimpleNamespace(
        id="mystery",
        name="mystery",
        labels={},
        attrs={"NetworkSettings": {"Networks": {}}},
        reload=lambda: None,
    )
    network.attrs["Containers"]["mystery"] = {"IPv4Address": "10.251.0.3/24"}
    client.containers.by_id["mystery"] = mystery

    with pytest.raises(DockerSandboxError):
        adapter.cleanup_network_by_name(NET_NAME)
    assert NET_NAME in client.networks.by_name


@pytest.mark.asyncio
async def test_rebuild_media_network_keeps_browser_attached(tmp_path):
    # AC-004: a pre-spec network is rebuilt to the fixed-endpoint spec
    # while the Browser container stays attached to the (new) network.
    from cbrowser.supervisor.network_spec import network_labels

    client = _client()
    adapter = _adapter(tmp_path, client)
    old = _FakeNetwork(
        NET_NAME,
        network_labels(PREFIX, PROFILE, deployment_id="dep-t026"),
        [{"Subnet": "172.20.0.0/16", "IPRange": ""}],
    )
    client.networks.by_name[NET_NAME] = old

    def _remove():
        old.removed = True
        client.networks.by_name.pop(NET_NAME, None)

    old.remove = _remove
    browser = _profile_container("c_browser", "browser")
    old.attrs["Containers"][browser.id] = {"IPv4Address": "172.20.0.2/16"}
    browser.attrs["NetworkSettings"]["Networks"][NET_NAME] = {
        "IPAddress": "172.20.0.2"
    }
    client.containers.by_id[browser.id] = browser

    adapter.rebuild_media_network(PROFILE)

    assert old.removed is True
    inspection = adapter.inspect_media_network(PROFILE)
    assert inspection["conforms"] is True
    new_net = client.networks.by_name[NET_NAME]
    assert browser.id in new_net.attrs["Containers"]


@pytest.mark.asyncio
async def test_rebuild_media_network_refuses_unknown_endpoint(tmp_path):
    from cbrowser.supervisor.network_spec import network_labels

    client = _client()
    adapter = _adapter(tmp_path, client)
    old = _FakeNetwork(
        NET_NAME,
        network_labels(PREFIX, PROFILE),
        [{"Subnet": "172.20.0.0/16", "IPRange": ""}],
    )
    client.networks.by_name[NET_NAME] = old
    mystery = SimpleNamespace(
        id="mystery",
        name="mystery",
        labels={},
        attrs={"NetworkSettings": {"Networks": {}}},
        reload=lambda: None,
    )
    old.attrs["Containers"]["mystery"] = {"IPv4Address": "172.20.0.9/16"}
    client.containers.by_id["mystery"] = mystery

    with pytest.raises(DockerSandboxError):
        adapter.rebuild_media_network(PROFILE)
    assert getattr(old, "removed", False) is False
    assert "mystery" in old.attrs["Containers"]


@pytest.mark.asyncio
async def test_rebuild_refuses_managed_container_with_unknown_role(tmp_path):
    # code f013: rebuild's endpoint verification matches cleanup's
    # strictness — a managed container with an unrecognized role is an
    # unknown endpoint, not something to disconnect/reconnect blindly.
    from cbrowser.supervisor.network_spec import network_labels

    client = _client()
    adapter = _adapter(tmp_path, client)
    old = _FakeNetwork(
        NET_NAME,
        network_labels(PREFIX, PROFILE),
        [{"Subnet": "172.20.0.0/16", "IPRange": ""}],
    )
    client.networks.by_name[NET_NAME] = old
    rogue = SimpleNamespace(
        id="rogue",
        name="rogue",
        labels={
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.prefix": PREFIX,
            "com.cbrowser.role": "rogue",
        },
        attrs={"NetworkSettings": {"Networks": {}}},
        reload=lambda: None,
    )
    old.attrs["Containers"]["rogue"] = {"IPv4Address": "172.20.0.9/16"}
    client.containers.by_id["rogue"] = rogue

    with pytest.raises(DockerSandboxError):
        adapter.rebuild_media_network(PROFILE)
    assert getattr(old, "removed", False) is False
