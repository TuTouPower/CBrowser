"""Real SDK proof that the restart commit wait reports the actual ICE outcome."""

import asyncio
import json
import re

from cbrowser.stream_agent.ice_transport import (
    create_restart_offer,
    install_ice_transport,
    wait_restart_commit,
)
from selkies.webrtc import RTCPeerConnection
from selkies.webrtc.rtcconfiguration import RTCBundlePolicy, RTCConfiguration
from selkies.webrtc.rtcsessiondescription import RTCSessionDescription


async def wait(predicate):
    async def loop():
        while not predicate():
            await asyncio.sleep(0.02)

    await asyncio.wait_for(loop(), 10)


async def main():
    install_ice_transport()
    cfg = RTCConfiguration(iceServers=[], bundlePolicy=RTCBundlePolicy.MAX_BUNDLE)
    a, b = RTCPeerConnection(cfg), RTCPeerConnection(cfg)
    received = []
    channel = a.createDataChannel("commit-outcome")

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
        transport = a.sctp.transport.transport
        remote_transport = b.sctp.transport.transport

        # Healthy restart: the wait returns only once generation 2 took over.
        await remote_transport.prepare_restart([])
        await b.setRemoteDescription(await create_restart_offer(a, []))
        await b.setLocalDescription(await b.createAnswer())
        await a.setRemoteDescription(b.localDescription)
        committed = await wait_restart_commit(a, 10.0)
        channel.send("after-commit")
        await wait(lambda: "after-commit" in received)
        result = {
            "healthy_committed": committed,
            "healthy_pending": transport.restart_pending,
            "healthy_delivers": True,
        }

        # Failed restart: the answer carries a wrong ICE password, so the new
        # generation's connectivity checks fail and it must not be reported as
        # committed (closing b instead would tear down a through SCTP/DTLS).
        await remote_transport.prepare_restart([])
        await b.setRemoteDescription(await create_restart_offer(a, []))
        await b.setLocalDescription(await b.createAnswer())
        wrong_pwd = re.sub(
            r"a=ice-pwd:\S+", "a=ice-pwd:" + "x" * 24, b.localDescription.sdp
        )
        await a.setRemoteDescription(
            RTCSessionDescription(sdp=wrong_pwd, type="answer")
        )
        try:
            await wait_restart_commit(a, 5.0)
        except ConnectionError as exc:
            result["failed_error"] = type(exc).__name__
        else:
            result["failed_error"] = None
        result["failed_committed_generation"] = transport.committed_generation
        result["failed_target_generation"] = transport.generation
        print(json.dumps(result), flush=True)
    finally:
        await asyncio.gather(a.close(), b.close(), return_exceptions=True)


asyncio.run(main())
