import asyncio
import json
import os
import secrets
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

    blackhole = None
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
        before = sockets()
        original_monitor = transport._RTCIceTransport__monitor_task
        blackhole, _ = await asyncio.get_running_loop().create_datagram_endpoint(
            asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0)
        )
        port = blackhole.get_extra_info("sockname")[1]
        before = sockets()
        servers = [
            {
                "urls": f"turn:127.0.0.1:{port}",
                "username": secrets.token_hex(12),
                "credential": secrets.token_hex(24),
            }
        ]
        errors = []
        for _ in range(2):
            operation = asyncio.create_task(transport.prepare_restart(servers, True))
            if "--cancel" in sys.argv:
                await asyncio.sleep(0.05)
                operation.cancel()
            try:
                await operation
            except (RuntimeError, asyncio.CancelledError) as error:
                errors.append(type(error).__name__)
            else:
                raise AssertionError("Unresponsive TURN unexpectedly succeeded")
            await asyncio.sleep(0.1)
        after = sockets()
        channel.send("after-failed-restart")
        await wait(lambda: "after-failed-restart" in received)
        result = {
            "restarts_rejected": len(errors) == 2,
            "socket_count_before": len(before),
            "socket_count_after": len(after),
            "monitor_preserved": transport._RTCIceTransport__monitor_task
            is original_monitor,
            "old_channel_still_delivers": True,
            "mux": mux is not None,
            "cancelled": "--cancel" in sys.argv,
        }
        assert len(after) <= len(before), "TURN allocation cancellation leaked sockets"
        assert result["monitor_preserved"]
        print(json.dumps(result), flush=True)
    finally:
        if blackhole:
            blackhole.close()
        await asyncio.gather(a.close(), b.close(), return_exceptions=True)
        if mux:
            await mux.close()


asyncio.run(main())
