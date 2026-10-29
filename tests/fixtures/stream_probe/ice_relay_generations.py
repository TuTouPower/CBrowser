import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from cbrowser.stream_agent.ice_transport import (
    create_restart_offer,
    install_ice_transport,
)
from selkies.ice.ice import get_host_addresses
from selkies.ice.mux import UdpMux
from selkies.webrtc import RTCPeerConnection
from selkies.webrtc.rtcconfiguration import RTCBundlePolicy, RTCConfiguration


async def wait(predicate):
    async def loop():
        while not predicate():
            await asyncio.sleep(0.02)

    await asyncio.wait_for(loop(), 12)


def servers(role, generation):
    username = f"{int(time.time()) + 600}:{role}:{generation}:{secrets.token_hex(8)}"
    with open("/turn_secret", "rb") as secret_file:
        secret = secret_file.read().strip()
    credential = base64.b64encode(
        hmac.new(secret, username.encode(), hashlib.sha1).digest()
    ).decode()
    return [
        {
            "urls": "turn:turn:3478?transport=udp",
            "username": username,
            "credential": credential,
        }
    ]


async def main():
    install_ice_transport()
    mux = UdpMux(30028)
    await mux.open(get_host_addresses(use_ipv4=True, use_ipv6=False))
    a = RTCPeerConnection(
        RTCConfiguration(
            iceServers=[], bundlePolicy=RTCBundlePolicy.MAX_BUNDLE, iceUdpMux=mux
        )
    )
    b = RTCPeerConnection(
        RTCConfiguration(iceServers=[], bundlePolicy=RTCBundlePolicy.MAX_BUNDLE)
    )
    dc = a.createDataChannel("relay-generation-proof")
    received = []

    @b.on("datachannel")
    def on_channel(channel):
        channel.on("message", received.append)

    rows = []
    try:
        await a.setLocalDescription(await a.createOffer())
        await b.setRemoteDescription(a.localDescription)
        await b.setLocalDescription(await b.createAnswer())
        await a.setRemoteDescription(b.localDescription)
        await wait(lambda: dc.readyState == "open")
        dtls = a.sctp.transport
        ta, tb = a.sctp.transport.transport, b.sctp.transport.transport
        for generation in [2, 3, 4]:
            olda, oldb = ta.active_connection, tb.active_connection
            server_config, client_config = (
                servers("server", generation),
                servers("client", generation),
            )
            assert server_config[0]["username"] != client_config[0]["username"]
            await tb.prepare_restart(client_config, True)
            offer = await create_restart_offer(a, server_config, True)
            await b.setRemoteDescription(offer)
            await b.setLocalDescription(await b.createAnswer())
            await a.setRemoteDescription(b.localDescription)
            await wait(
                lambda: ta.committed_generation == tb.committed_generation == generation
            )
            assert a.sctp.transport is dtls and a.sctp.transport.transport is ta
            assert ta._connection._udp_mux is mux
            assert dc.readyState == "open"
            marker = "relay-generation-" + str(generation)
            dc.send(marker)
            await wait(lambda: marker in received)
            paira = next(iter(ta.active_connection._nominated.values()))
            pairb = next(iter(tb.active_connection._nominated.values()))
            assert paira.local_candidate.type == paira.remote_candidate.type == "relay"
            assert pairb.local_candidate.type == pairb.remote_candidate.type == "relay"
            for old in [olda, oldb]:
                assert old._closed
                try:
                    await old.send(b"retired-transport-must-reject")
                except ConnectionError:
                    pass
                else:
                    raise AssertionError("Retired transport accepted writes")
            rows.append(
                {
                    "generation": generation,
                    "server_relay_port": paira.local_candidate.port,
                    "client_relay_port": pairb.local_candidate.port,
                    "server_candidate": "relay",
                    "client_candidate": "relay",
                    "old_send_rejected": True,
                    "same_dtls": a.sctp.transport is dtls,
                    "same_datachannel": dc.readyState == "open",
                    "mux_preserved": ta._connection._udp_mux is mux,
                }
            )
        assert len(set(row["server_relay_port"] for row in rows)) == 3
        assert len(set(row["client_relay_port"] for row in rows)) == 3
        print(
            json.dumps(
                {
                    "uid": os.getuid(),
                    "relay_generations": rows,
                    "scope": (
                        "Actual two native Selkies PCs/DataChannel; "
                        "not Chrome video/audio acceptance"
                    ),
                }
            ),
            flush=True,
        )
    finally:
        await asyncio.gather(a.close(), b.close(), return_exceptions=True)
        await mux.close()


asyncio.run(main())
