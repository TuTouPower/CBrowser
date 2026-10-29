import asyncio
import gc
import json
import os
import sys

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
        errors = []
        for _ in range(3):
            try:
                await create_restart_offer(a, [], force_relay=True)
            except RuntimeError as exc:
                errors.append(type(exc).__name__)
            else:
                raise AssertionError(
                    "Relay-only restart unexpectedly succeeded without TURN"
                )
            gc.collect()
            await asyncio.sleep(0.05)
        after = sockets()
        channel.send("after-failed-restart")
        await wait(lambda: "after-failed-restart" in received)
        result = {
            "three_restarts_rejected": len(errors) == 3,
            "old_channel_still_delivers": True,
            "socket_count_before": len(before),
            "socket_count_after": len(after),
            "extra_sockets": sorted(set(after) - set(before)),
            "monitor_preserved": transport._RTCIceTransport__monitor_task
            is original_monitor,
            "original_monitor_cancelled": original_monitor.cancelled()
            if original_monitor
            else None,
            "generation": transport.generation,
            "restart_pending": transport.restart_pending,
        }
        assert len(after) <= len(before), "Failed restarts leaked socket resources"
        assert result["monitor_preserved"], (
            "Failed restart cancelled the active generation monitor"
        )
        pc_ref, dtls_ref, channel_ref = a, a.sctp.transport, channel
        remote_transport = b.sctp.transport.transport
        await remote_transport.prepare_restart([])
        offer = await create_restart_offer(a, [])
        await b.setRemoteDescription(offer)
        await b.setLocalDescription(await b.createAnswer())
        await a.setRemoteDescription(b.localDescription)
        await wait(
            lambda: (
                not transport.restart_pending and not remote_transport.restart_pending
            )
        )
        assert a is pc_ref and a.sctp.transport is dtls_ref and channel is channel_ref
        channel.send("healthy-restart-after-failures")
        await wait(lambda: "healthy-restart-after-failures" in received)
        result["healthy_restart_after_failures"] = True
        result["committed_generation"] = transport.committed_generation
        result["mux"] = mux is not None
        print(json.dumps(result), flush=True)
    finally:
        await asyncio.gather(a.close(), b.close(), return_exceptions=True)
        if mux:
            await mux.close()


asyncio.run(main())
