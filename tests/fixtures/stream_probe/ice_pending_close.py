import asyncio
import json
import os
import sys

from cbrowser.stream_agent.ice_transport import (
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

    await asyncio.wait_for(loop(), 10)


def sockets():
    found = []
    for name in os.listdir("/proc/self/fd"):
        try:
            link = os.readlink("/proc/self/fd/" + name)
        except FileNotFoundError:
            continue
        if link.startswith("socket:"):
            found.append(link)
    return sorted(found)


async def main():
    install_ice_transport()
    cfg = RTCConfiguration(iceServers=[], bundlePolicy=RTCBundlePolicy.MAX_BUNDLE)
    baseline = len(sockets())
    mux = None
    if "--mux" in sys.argv:
        mux = UdpMux(30028)
        await mux.open(get_host_addresses(use_ipv4=True, use_ipv6=False))
        cfg_a = RTCConfiguration(
            iceServers=[], bundlePolicy=RTCBundlePolicy.MAX_BUNDLE, iceUdpMux=mux
        )
    else:
        cfg_a = cfg
    a, b = RTCPeerConnection(cfg_a), RTCPeerConnection(cfg)
    received = []
    channel = a.createDataChannel("failure-rollback")

    @b.on("datachannel")
    def on_channel(remote):
        remote.on("message", received.append)

    try:
        await a.setLocalDescription(await a.createOffer())
        await b.setRemoteDescription(a.localDescription)
        await b.setLocalDescription(await b.createAnswer())
        await a.setRemoteDescription(b.localDescription)
        await wait(lambda: a.connectionState == b.connectionState == "connected")
        await wait(lambda: channel.readyState == "open")
        channel.send("before-failed-restart")
        await wait(lambda: "before-failed-restart" in received)
        transport = a.sctp.transport.transport
        active = transport.active_connection
        await transport.prepare_restart([])
        pending = transport._connection
        assert active is not pending
        await a.close()
        await b.close()
        assert active._closed, "Closing a pending restart leaked the active generation"
        assert pending._closed, (
            "Closing a pending restart leaked the pending generation"
        )
        assert not transport.pumps, "Closing a pending restart left packet pumps"
        if mux:
            await mux.close()
        await asyncio.sleep(0.05)
        proof = {
            "active_closed": active._closed,
            "pending_closed": pending._closed,
            "socket_count_before": baseline,
            "socket_count_after": len(sockets()),
            "mux": mux is not None,
        }
        assert proof["socket_count_after"] <= baseline, "Peer close leaked sockets"
        print(json.dumps(proof), flush=True)
    finally:
        await asyncio.gather(a.close(), b.close(), return_exceptions=True)
        if mux:
            await mux.close()


asyncio.run(main())
