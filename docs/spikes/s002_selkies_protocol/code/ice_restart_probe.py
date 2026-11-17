"""Exercise pinned Selkies ICE on real UDP; report repeated-start behavior."""
import asyncio
import json
import secrets
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("usage: ice_restart_probe.py SELKIES_CHECKOUT")
sys.path.insert(0, str(Path(sys.argv[1]).resolve() / "src"))
from selkies.webrtc.rtcicetransport import (
    RTCIceGatherer,
    RTCIceParameters,
    RTCIceTransport,
)


async def main():
    left_gatherer = RTCIceGatherer(iceServers=[])
    right_gatherer = RTCIceGatherer(iceServers=[])
    left = RTCIceTransport(left_gatherer)
    right = RTCIceTransport(right_gatherer)
    left._connection.ice_controlling = True
    try:
        await asyncio.gather(left_gatherer.gather(), right_gatherer.gather())
        for candidate in right_gatherer.getLocalCandidates():
            await left.addRemoteCandidate(candidate)
        for candidate in left_gatherer.getLocalCandidates():
            await right.addRemoteCandidate(candidate)
        await left.addRemoteCandidate(None)
        await right.addRemoteCandidate(None)
        await asyncio.gather(
            left.start(right_gatherer.getLocalParameters()),
            right.start(left_gatherer.getLocalParameters()),
        )
        if left.state != "completed" or right.state != "completed":
            raise RuntimeError("Real UDP ICE connectivity did not complete")
        await left._send(b"before-restart")
        if await right._recv() != b"before-restart":
            raise RuntimeError("Real UDP payload was not received")
        original = left._connection.remote_username
        replacement = RTCIceParameters(
            usernameFragment="new-remote-generation",
            password=secrets.token_urlsafe(24),
        )
        await left.start(replacement)
        unchanged = left._connection.remote_username == original
        await left._send(b"after-repeated-start")
        old_path_alive = await right._recv() == b"after-repeated-start"
        print(json.dumps({
            "real_udp_before": True,
            "repeated_start_applied_new_credentials": not unchanged,
            "original_path_still_alive": old_path_alive,
            "interpretation": "existing transport start does not perform ICE restart",
        }))
        if not unchanged or not old_path_alive:
            raise RuntimeError("Observation contradicts the expected upstream gap")
    finally:
        await asyncio.gather(left.stop(), right.stop())


asyncio.run(asyncio.wait_for(main(), timeout=20))
