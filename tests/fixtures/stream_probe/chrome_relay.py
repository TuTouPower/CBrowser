"""Real Chrome TURN rotation oracle, sampled only after generation retirement."""

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import subprocess
import time

TURN_IMAGE = os.environ.get("CBROWSER_TURN_TEST_IMAGE", "")


def docker(*args):
    result = subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True, timeout=20
    )
    return result.stdout.strip()


def credential(secret, side, generation):
    username = f"{int(time.time()) + 300}:{side}:{generation}:{secrets.token_hex(4)}"
    password = base64.b64encode(
        hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    ).decode()
    return username, password


async def verify_relay_rotations(
    page,
    other_page,
    gateway,
    profile_id,
    network,
    stream_name,
    work_dir,
    containers,
    media_stats,
):
    """Keep coturn alive until the caller's exact container cleanup."""
    assert TURN_IMAGE.startswith("sha256:"), "Immutable coturn test image required"
    network_info = json.loads(docker("network", "inspect", network))[0]
    subnet = ipaddress.ip_network(network_info["IPAM"]["Config"][0]["Subnet"])
    turn_ip = str(subnet[10])
    secret = secrets.token_hex(24)
    turn_dir = work_dir / "turn"
    turn_dir.mkdir(mode=0o700)
    config = turn_dir / "turnserver.conf"
    config.write_text(
        "listening-port=3478\nmin-port=42100\nmax-port=42140\n"
        "realm=cbrowser.local\nuse-auth-secret\nno-cli\n"
        f"static-auth-secret={secret}\nrelay-ip={turn_ip}\n"
        f"external-ip=127.0.0.1/{turn_ip}\nallow-loopback-peers\nverbose\n"
    )
    config.chmod(0o644)
    turn_name = f"{stream_name}-turn"
    docker(
        "run",
        "-d",
        "--name",
        turn_name,
        "--network",
        network,
        "--ip",
        turn_ip,
        "-p",
        "127.0.0.1:34861:3478/udp",
        "-p",
        "127.0.0.1:42100-42140:42100-42140/udp",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--cap-add",
        "NET_BIND_SERVICE",
        "--security-opt",
        "no-new-privileges:true",
        "--tmpfs",
        "/tmp:rw,mode=1777",
        "-v",
        f"{config}:/etc/turnserver.conf:ro",
        "--entrypoint",
        "/usr/bin/turnserver",
        TURN_IMAGE,
        "-c",
        "/etc/turnserver.conf",
        "--relay-threads=1",
        "--log-file=stdout",
    )
    containers.append(turn_name)
    await asyncio.sleep(0.5)
    tab_id = await page.evaluate("sessionStorage.getItem('selkies_tab_id')")
    conn_id = next(cid for cid, tid in gateway.viewer_tab_ids.items() if tid == tab_id)
    await page.evaluate("""() => {
        window.__rotationPC = window.pc;
        window.__rotationCount = window.__pcs.length;
        window.__rotationTracks = window.pc.getReceivers().map(r => r.track);
        window.__rotationDtls = window.pc.getReceivers().map(r => r.transport);
    }""")
    pair_stats = """async () => {
        const report = await window.__rotationPC.getStats();
        const transport = [...report.values()].find(
            x => x.type === 'transport' && x.selectedCandidatePairId);
        const pair = transport && report.get(transport.selectedCandidatePairId);
        const local = pair && report.get(pair.localCandidateId);
        const remote = pair && report.get(pair.remoteCandidateId);
        return pair ? {localType:local.candidateType, remoteType:remote.candidateType,
            remoteUfrag:remote.usernameFragment, bytesReceived:pair.bytesReceived,
            remotePort:remote.port, localPort:local.port} : null;
    }"""
    generations = []
    try:
        for generation in (2, 3, 4):
            client_user, client_password = credential(secret, "client", generation)
            server_user, server_password = credential(secret, "server", generation)
            assert client_user != server_user and client_password != server_password
            reject = os.environ.get("CBROWSER_STREAM_TURN_REJECT_SIDE")
            if reject == "client":
                client_password = secrets.token_hex(24)
            if reject == "server":
                server_password = secrets.token_hex(24)
            await page.evaluate(
                """cfg => window.__rotationPC.setConfiguration(cfg)""",
                {
                    "iceServers": [
                        {
                            "urls": "turn:127.0.0.1:34861?transport=udp",
                            "username": client_user,
                            "credential": client_password,
                        }
                    ],
                    "iceTransportPolicy": "relay",
                },
            )
            session, ws = gateway.registered_agents[profile_id]
            identity = dict(
                version="v2",
                profile_id=profile_id,
                runtime_instance_id=gateway.agent_instances[profile_id],
                agent_session_id=session,
                conn_id=conn_id,
            )
            marker = len(gateway.control_packets)
            await ws.send_json(
                dict(
                    identity,
                    action="ice_restart",
                    payload={
                        "ice_servers": [
                            {
                                "urls": f"turn:{turn_ip}:3478?transport=udp",
                                "username": server_user,
                                "credential": server_password,
                            }
                        ],
                        "force_relay": True,
                    },
                )
            )
            offer = None
            for _ in range(100):
                offer = next(
                    (
                        packet
                        for packet in gateway.control_packets[marker:]
                        if packet.get("conn_id") == conn_id
                        and packet.get("action") == "ice_restart_offer"
                    ),
                    None,
                )
                if offer:
                    break
                await asyncio.sleep(0.1)
            assert offer, "No fresh ICE restart offer"
            ufrag = next(
                line.split(":", 1)[1]
                for line in offer["payload"]["sdp"].splitlines()
                if line.startswith("a=ice-ufrag:")
            )
            assert ufrag not in {item["ufrag"] for item in generations}
            answer = await page.evaluate(
                """async offer => {
                const pc = window.__rotationPC;
                await pc.setRemoteDescription(offer);
                await pc.setLocalDescription(await pc.createAnswer());
                if (pc.iceGatheringState !== 'complete') {
                    await new Promise(resolve => {
                        const check = () => {
                            if (pc.iceGatheringState === 'complete') {
                                pc.removeEventListener('icegatheringstatechange',check);
                                resolve();
                            }
                        };
                        pc.addEventListener('icegatheringstatechange',check);
                        setTimeout(resolve,3000);
                    });
                }
                return {type:pc.localDescription.type,sdp:pc.localDescription.sdp};
            }""",
                offer["payload"],
            )
            await ws.send_json(
                dict(identity, action="ice_restart_answer", payload=answer)
            )
            fence = (
                f"Generation {generation} officially committed. "
                f"Retired generation {generation - 1} closed and rejected writes."
            )
            for _ in range(100):
                logs = docker("logs", stream_name)
                # Docker logging may use stderr; retain both streams below.
                captured = subprocess.run(
                    ["docker", "logs", stream_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                logs += captured.stderr
                if fence in logs:
                    break
                await asyncio.sleep(0.2)
            assert fence in logs, "New ICE generation did not retire old generation"
            for _ in range(50):
                pair = await page.evaluate(pair_stats)
                if (
                    pair
                    and pair["localType"] == pair["remoteType"] == "relay"
                    and pair["remoteUfrag"] == ufrag
                ):
                    break
                await asyncio.sleep(0.2)
            assert pair and pair["localType"] == pair["remoteType"] == "relay", pair
            assert pair["remoteUfrag"] == ufrag, pair
            before = await page.evaluate(media_stats)
            other_before = await other_page.evaluate(media_stats)
            await asyncio.sleep(2)
            after = await page.evaluate(media_stats)
            other_after = await other_page.evaluate(media_stats)
            pair_after = await page.evaluate(pair_stats)
            for old, new in ((before, after), (other_before, other_after)):
                assert new["video"]["framesDecoded"] > old["video"]["framesDecoded"]
                assert (
                    new["audio"]["totalAudioEnergy"] > old["audio"]["totalAudioEnergy"]
                )
            assert pair_after["remoteUfrag"] == ufrag
            assert pair_after["bytesReceived"] > pair["bytesReceived"]
            invariant = await page.evaluate("""() => ({
                samePC:window.pc === window.__rotationPC,
                sameCount:window.__pcs.length === window.__rotationCount,
                sameTracks:window.pc.getReceivers().every(
                    (r,i) => r.track === window.__rotationTracks[i]),
                sameDtls:window.pc.getReceivers().every(
                    (r,i) => r.transport === window.__rotationDtls[i])
            })""")
            assert all(invariant.values()), invariant
            generations.append(
                dict(
                    generation=generation,
                    ufrag=ufrag,
                    pair=pair_after,
                    before=before,
                    after=after,
                    invariant=invariant,
                )
            )
            (work_dir / "relay_generations.json").write_text(
                json.dumps(generations, indent=2)
            )
    finally:
        for name, filename in (
            (turn_name, "coturn.log"),
            (stream_name, "relay_stream.log"),
        ):
            captured = subprocess.run(
                ["docker", "logs", name], capture_output=True, text=True, timeout=10
            )
            (work_dir / filename).write_text(captured.stdout + captured.stderr)
