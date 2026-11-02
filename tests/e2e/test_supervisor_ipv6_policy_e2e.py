"""Private IPv6 echo must be denied while an allowed TCP peer stays reachable."""

import asyncio
import json
import os
import uuid

import docker
import pytest


@pytest.mark.asyncio
async def test_kernel_ipv6_echo_isolation_preserves_allowed_tcp(tmp_path):
    names = ("CBROWSER_RUNTIME_TEST_IMAGE", "CBROWSER_SUPERVISOR_TEST_IMAGE")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        pytest.skip("Missing E2E inputs: " + ", ".join(missing))
    images = {name: os.environ[name] for name in names}
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
        policy = {"role": "browser", "allowed_tcp": [[peer_ip, 18888]]}
        helper = client.containers.create(
            images[names[1]],
            entrypoint=["python3", "-m", "cbrowser.supervisor.network_policy"],
            command=[json.dumps(policy)],
            name=prefix + "-policy",
            network_mode="container:" + target.id,
            user="0:0",
            read_only=True,
            cap_drop=["ALL"],
            cap_add=["NET_ADMIN"],
            security_opt=["no-new-privileges:true"],
            tmpfs={"/run": "rw,size=4m"},
            labels={"com.cbrowser.prefix": prefix},
        )
        created.append(helper)
        helper.start()
        assert helper.wait(timeout=20)["StatusCode"] == 0, helper.logs().decode()
        helper.remove()
        created.remove(helper)
        # A second installer must refuse an already configured namespace.
        conflicting = client.containers.create(
            images[names[1]],
            entrypoint=["python3", "-m", "cbrowser.supervisor.network_policy"],
            command=[json.dumps(policy)],
            name=prefix + "-conflict",
            network_mode="container:" + target.id,
            user="0:0",
            read_only=True,
            cap_drop=["ALL"],
            cap_add=["NET_ADMIN"],
            security_opt=["no-new-privileges:true"],
            tmpfs={"/run": "rw,size=4m"},
            labels={"com.cbrowser.prefix": prefix},
        )
        created.append(conflicting)
        conflicting.start()
        assert conflicting.wait(timeout=20)["StatusCode"] == 3
        conflicting.remove()
        created.remove(conflicting)
        after = observe()
        (tmp_path / "ipv6_policy_proof.json").write_text(
            json.dumps({"before": before, "after": after}, indent=2)
        )
        assert after["tcp_response"] == "PONG"
        assert after["echo_ok"] is False
    finally:
        for container in reversed(created):
            container.remove(force=True)
        if network is not None:
            network.remove()
        assert not client.containers.list(
            all=True, filters={"label": "com.cbrowser.prefix=" + prefix}
        )
        client.close()
