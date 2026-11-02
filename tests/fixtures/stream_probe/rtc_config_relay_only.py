"""Real SDK proof that relay_only intent restricts new PC candidates to relay type."""

import asyncio
import json

import selkies.webrtc.rtcpeerconnection as pc_mod
from cbrowser.stream_agent.agent import StreamAgent
from cbrowser.stream_agent.config import StreamAgentConfig
from cbrowser.stream_agent.ice_transport import install_ice_transport, is_relay_only
from cbrowser.stream_agent.protocol import RtcConfigPayload
from selkies.webrtc.rtcconfiguration import RTCConfiguration, RTCIceServer


class ServiceSlot:
    rtc_app = None
    rtc_ready_hook = None


async def main():
    install_ice_transport()

    agent = StreamAgent(
        StreamAgentConfig(
            profile_id="profile_relay_probe",
            runtime_instance_id="inst_relay_probe",
            gateway_url="ws://127.0.0.1:18090",
            agent_token="x" * 32,
            turn_host="10.0.0.5",
            turn_port=3478,
            udp_mux_port=30010,
            config_version=1,
            selkies_version="2.1.0",
        )
    )
    service = ServiceSlot()
    agent.bind_webrtc_service(service)

    # 1. Non-relay-only payload: relay_only=False
    payload_normal = RtcConfigPayload.model_validate(
        {
            "generation": 1,
            "relay_only": False,
            "ice_servers": [{"urls": ["turn:10.0.0.5:3478?transport=udp"]}],
        }
    )
    agent.apply_rtc_config(payload_normal)
    assert not is_relay_only(), "is_relay_only must be False"

    pc_normal = pc_mod.RTCPeerConnection()
    pc_normal.addTransceiver("video")
    await pc_normal.setLocalDescription(await pc_normal.createOffer())
    normal_cands = [
        c.type
        for t in pc_normal._RTCPeerConnection__iceTransports
        for c in t.iceGatherer.getLocalCandidates()
    ]
    await pc_normal.close()
    assert "host" in normal_cands, (
        f"Normal PC should gather host candidates, got {normal_cands}"
    )

    # 2. Relay-only payload: relay_only=True
    payload_relay = RtcConfigPayload.model_validate(
        {
            "generation": 2,
            "relay_only": True,
            "ice_servers": [{"urls": ["turn:10.0.0.5:3478?transport=udp"]}],
        }
    )
    agent.apply_rtc_config(payload_relay)
    assert is_relay_only(), "is_relay_only must be True"

    # In relay-only mode, with an unreachable TURN server, gathering cannot produce
    # relay candidates and must FAIL CLOSED with RuntimeError (no fallback to host)
    bad_turn = RTCIceServer("turn:127.0.0.1:39999?transport=udp", "user", "pass")
    pc_relay = pc_mod.RTCPeerConnection(RTCConfiguration(iceServers=[bad_turn]))
    pc_relay.addTransceiver("video")
    relay_failed_closed = False
    try:
        await pc_relay.setLocalDescription(await pc_relay.createOffer())
    except RuntimeError as e:
        if "Relay candidates unavailable" in str(e):
            relay_failed_closed = True
    finally:
        await pc_relay.close()

    assert relay_failed_closed, (
        "Relay-only PC must fail closed when relay candidates are unavailable"
    )

    # 3. Relay-only mode with simulated relay candidate: ONLY relay candidate is kept
    from selkies.ice.ice import Candidate

    pc_relay_ok = pc_mod.RTCPeerConnection(RTCConfiguration(iceServers=[]))
    pc_relay_ok.addTransceiver("video")
    transport = next(iter(pc_relay_ok._RTCPeerConnection__iceTransports))
    gatherer = transport.iceGatherer

    # Intercept native gather on Connection to inject candidates (one host, one relay)
    orig_gather_candidates = gatherer._connection.gather_candidates

    cand_relay = Candidate(
        foundation="1",
        component=1,
        transport="udp",
        priority=100,
        host="10.0.0.5",
        port=40000,
        type="relay",
        related_address="192.168.1.10",
        related_port=30000,
    )
    cand_host = Candidate(
        foundation="2",
        component=1,
        transport="udp",
        priority=200,
        host="192.168.1.10",
        port=30000,
        type="host",
    )

    async def mock_gather_candidates():
        await orig_gather_candidates()
        gatherer._connection._local_candidates = [cand_host, cand_relay]

    gatherer._connection.gather_candidates = mock_gather_candidates

    await pc_relay_ok.setLocalDescription(await pc_relay_ok.createOffer())
    filtered_cands = [
        c.type
        for t in pc_relay_ok._RTCPeerConnection__iceTransports
        for c in t.iceGatherer.getLocalCandidates()
    ]
    sdp = pc_relay_ok.localDescription.sdp
    await pc_relay_ok.close()

    assert filtered_cands == ["relay"], (
        f"Only relay candidate must remain, got {filtered_cands}"
    )
    assert "typ relay" in sdp, "SDP must contain relay candidate"
    assert "typ host" not in sdp, "SDP must NOT contain host candidate"

    result = {
        "normal_cands": normal_cands,
        "relay_failed_closed": relay_failed_closed,
        "filtered_cands": filtered_cands,
    }
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
