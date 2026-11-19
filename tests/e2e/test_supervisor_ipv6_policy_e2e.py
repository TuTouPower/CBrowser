"""Private IPv6 echo must be denied while an allowed TCP peer stays reachable."""

import asyncio
import json
import uuid

import docker
import pytest

from e2e_env import require_e2e_env
from e2e_volumes import (
    ContainerPolicyAgentClient,
    init_prefix_volumes,
    policy_agent_socket_mount,
    remove_prefix_volumes,
)
from cbrowser.supervisor.container_spec import policy_agent_environment
from cbrowser.supervisor.network_policy import NetworkPolicySpec
from cbrowser.supervisor.policy_agent_client import PolicyAgentRejected
from cbrowser.supervisor.policy_agent_protocol import PolicyAgentIdentity

pytestmark = [pytest.mark.serial, pytest.mark.e2e_images('CBROWSER_RUNTIME_TEST_IMAGE', 'CBROWSER_SUPERVISOR_TEST_IMAGE')]


@pytest.mark.asyncio
async def test_kernel_ipv6_echo_isolation_preserves_allowed_tcp(tmp_path):
    names = ("CBROWSER_RUNTIME_TEST_IMAGE", "CBROWSER_SUPERVISOR_TEST_IMAGE")
    images = require_e2e_env(*names)
    client = docker.from_env()
    for image in images.values():
        assert image.startswith("sha256:")
        client.images.get(image)
    prefix = "t005-ipv6-" + uuid.uuid4().hex[:10]
    part = uuid.uuid4().hex[:8]
    subnet = f"fdcb:{part[:4]}:{part[4:]}::/64"
    network = None
    created = []
    server_script = """import socket,sys
s=socket.socket(socket.AF_INET6,socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind(('::',18888));s.listen();sys.stdout.write('READY\\n');sys.stdout.flush()
while True:
 c,p=s.accept();c.sendall(b'PONG');c.close()
"""
    probe = """import json,socket,struct,sys
result={}
s=socket.socket(socket.AF_INET6,socket.SOCK_DGRAM,socket.IPPROTO_ICMPV6)
s.settimeout(1)
try:
 s.sendto(struct.pack('!BBHHH',128,0,0,0,1)+b'isolated',(sys.argv[1],0))
 result['echo_ok']=s.recv(256)[0]==129
except OSError as e:
 result.update(echo_ok=False,error_type=type(e).__name__,errno=e.errno)
finally:s.close()
t=socket.socket(socket.AF_INET6,socket.SOCK_STREAM);t.settimeout(2)
t.connect((sys.argv[1],18888));result['tcp_response']=t.recv(4).decode();t.close()
sys.stdout.write(json.dumps(result))
"""
    try:
        network = client.networks.create(
            prefix,
            driver="bridge",
            enable_ipv6=True,
            ipam=docker.types.IPAMConfig(
                pool_configs=[docker.types.IPAMPool(subnet=subnet)]
            ),
            labels={"com.cbrowser.prefix": prefix},
        )
        for name, script in (
            ("peer", server_script),
            ("client", "import time;time.sleep(120)"),
        ):
            container = client.containers.create(
                images[names[0]],
                entrypoint="python3",
                command=["-u", "-c", script],
                name=prefix + "-" + name,
                network=network.name,
                user="1000:1000",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                sysctls={"net.ipv4.ping_group_range": "0 2147483647"},
                labels={"com.cbrowser.prefix": prefix},
            )
            created.append(container)
            container.start()
        peer, target = created
        for _ in range(50):
            if b"READY" in peer.logs():
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail("IPv6 TCP server did not become ready")
        peer.reload()
        peer_ip = peer.attrs["NetworkSettings"]["Networks"][network.name][
            "GlobalIPv6Address"
        ]
        assert peer_ip

        def observe():
            result = target.exec_run(
                ["python3", "-c", probe, peer_ip], user="1000:1000"
            )
            assert result.exit_code == 0, result.output.decode()
            return json.loads(result.output)

        before = observe()
        assert before["echo_ok"] is True
        assert before["tcp_response"] == "PONG"
        policy = NetworkPolicySpec(
            role="browser", allowed_tcp=[(peer_ip, 18888)]
        )
        # t082: the persistent Policy Agent owns installation.  Start
        # it in the target's netns and install revision 1 over UDS.
        identity = PolicyAgentIdentity(
            deployment_id="e2e",
            profile_id="e2e-" + prefix,
            runtime_instance_id="e2e-inst",
            config_version=1,
            role="browser",
            target_container_id=target.id,
        )
        init_prefix_volumes(client, prefix, images[names[1]], roles=("runtime",))
        agent = client.containers.create(
            images[names[1]],
            entrypoint=["python3", "-m", "cbrowser.supervisor.policy_agent"],
            name=prefix + "-policy-agent",
            network_mode="container:" + target.id,
            user="0:0",
            read_only=True,
            cap_drop=["ALL"],
            cap_add=["NET_ADMIN"],
            security_opt=["no-new-privileges:true"],
            environment=policy_agent_environment(
                deployment_id=identity.deployment_id,
                profile_id=identity.profile_id,
                runtime_instance_id=identity.runtime_instance_id,
                config_version=identity.config_version,
                role=identity.role,
                target_container_id=identity.target_container_id,
            ),
            mounts=[policy_agent_socket_mount(prefix)],
            labels={"com.cbrowser.prefix": prefix},
        )
        created.append(agent)
        agent.start()
        agent_client = ContainerPolicyAgentClient(
            client,
            prefix,
            images[names[1]],
            identity,
            timeout=10.0,
        )
        try:
            agent_client.wait_ready_health(timeout_sec=15.0)
        except TimeoutError as exc:
            pytest.fail(f"{exc}: " + agent.logs().decode())
        agent_client.install(policy, 1)
        assert agent_client.inspect(policy, 1) is True
        # Advance to revision 2 so both a conflicting spec at the applied
        # revision and a replayed older valid revision (1 < 2, ge=1) are
        # rejected by the monotonic revision fence.
        agent_client.install(policy, 2)
        assert agent_client.inspect(policy, 2) is True
        conflicting_policy = NetworkPolicySpec(
            role="browser", allowed_tcp=[(peer_ip, 19999)]
        )
        with pytest.raises(PolicyAgentRejected):
            agent_client.install(conflicting_policy, 2)
        with pytest.raises(PolicyAgentRejected):
            agent_client.install(policy, 1)
        assert agent_client.inspect(policy, 2) is True
        after = observe()
        (tmp_path / "ipv6_policy_proof.json").write_text(
            json.dumps({"before": before, "after": after}, indent=2)
        )
        assert after["tcp_response"] == "PONG"
        assert after["echo_ok"] is False
        # Zero-leak assertion runs on the live client (t024 AC-011/A33):
        # after the finally block closes it, this check could not run.
        for container in reversed(created):
            container.remove(force=True)
        created.clear()
        if network is not None:
            network.remove()
            network = None
        remove_prefix_volumes(client, prefix)
        assert not client.containers.list(
            all=True, filters={"label": "com.cbrowser.prefix=" + prefix}
        )
    finally:
        for container in reversed(created):
            container.remove(force=True)
        if network is not None:
            network.remove()
        remove_prefix_volumes(client, prefix)
        client.close()
