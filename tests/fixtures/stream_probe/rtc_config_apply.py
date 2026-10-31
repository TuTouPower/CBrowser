"""Real SDK proof that Gateway RTC config reaches Selkies for new PeerConnections."""

import asyncio
import json

from cbrowser.stream_agent.agent import StreamAgent
from cbrowser.stream_agent.config import StreamAgentConfig
from cbrowser.stream_agent.protocol import RtcConfigPayload
from selkies.webrtc_engine import RTCApp


class ServiceSlot:
    """Holds the real RTCApp the way WebRTCService does once initialized."""

    rtc_app = None
    rtc_ready_hook = None


def ice_servers(rtc_app):
    return [
        {"urls": s.urls, "username": s.username, "credential": s.credential}
        for s in rtc_app.get_rtc_config().iceServers
    ]


async def main():
    agent = StreamAgent(
        StreamAgentConfig(
            profile_id="profile_rtc_apply",
            runtime_instance_id="inst_rtc_apply",
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
    payload = RtcConfigPayload.model_validate(
        {
            "generation": 2,
            "ice_servers": [
                {
                    "urls": [
                        "turn:10.0.0.5:3478?transport=udp",
                        "turn:10.0.0.5:3478?transport=tcp",
                    ],
                    "username": "1793000000:stream-profile_rtc_apply",
                    "credential": "c3RyZWFtLXNpZGUvY3JlZD0=",
                }
            ],
        }
    )

    # Gateway config may arrive before Selkies created its RTCApp.
    agent.apply_rtc_config(payload)
    # WebRTCService builds it from its own (here empty) startup STUN/TURN lists.
    service.rtc_app = RTCApp(
        async_event_loop=asyncio.get_running_loop(),
        encoder="x264enc",
        stun_servers=[],
        turn_servers=[],
    )
    before_ready = ice_servers(service.rtc_app)
    service.rtc_ready_hook()
    after_ready = ice_servers(service.rtc_app)

    # A later generation replaces the servers used by new PeerConnections.
    rotated = payload.model_copy(
        update={
            "generation": 3,
            "ice_servers": [
                payload.ice_servers[0].model_copy(
                    update={"username": "1793043200:stream-profile_rtc_apply"}
                )
            ],
        }
    )
    agent.apply_rtc_config(rotated)
    after_rotation = ice_servers(service.rtc_app)
    print(
        json.dumps(
            {
                "before_ready": before_ready,
                "after_ready": after_ready,
                "after_rotation": after_rotation,
            }
        ),
        flush=True,
    )


asyncio.run(main())
