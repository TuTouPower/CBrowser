#!/usr/bin/env python3
"""
Custom Stream Runner for Stage 2 WebRTC Media & ICE Restart.
Patches Selkies RTCIceTransport to Stage2GenerationIceTransport.
Runs an auxiliary HTTP control service on port 18092 to orchestrate server-side ICE restart
and expose detailed diagnostics (without credentials).
"""

import asyncio
import json
import logging
import sys
from aiohttp import web
from typing import Optional

# Setup logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("stage2_stream_runner")

# Insert local probe dir to sys.path
sys.path.insert(0, "/probe")

import selkies.webrtc.rtcpeerconnection as pc_module
from stage2_adapter import Stage2GenerationIceTransport
from selkies.webrtc.rtcconfiguration import RTCIceServer

# Patch RTCIceTransport globally before service initializes
pc_module.RTCIceTransport = Stage2GenerationIceTransport
logger.info("Successfully patched pc_module.RTCIceTransport with Stage2GenerationIceTransport")

# Global reference to live WebRTCService
_LIVE_WEBRTC_SERVICE = None

from selkies.webrtc_mode import WebRTCService
from selkies.stream_server import CentralizedStreamServer
import selkies.__main__ as selkies_main

class ControlledWebRTCService(WebRTCService):
    def __init__(self, supervisor: CentralizedStreamServer):
        super().__init__(supervisor)
        global _LIVE_WEBRTC_SERVICE
        _LIVE_WEBRTC_SERVICE = self
        logger.info("ControlledWebRTCService instance registered to global reference")

# Replace WebRTCService in __main__
selkies_main.WebRTCService = ControlledWebRTCService


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service_ready": _LIVE_WEBRTC_SERVICE is not None})


async def handle_peers(request: web.Request) -> web.Response:
    if not _LIVE_WEBRTC_SERVICE or not _LIVE_WEBRTC_SERVICE.rtc_app:
        return web.json_response({"peers": []})

    peers_info = []
    for pid, peer_data in _LIVE_WEBRTC_SERVICE.rtc_app.peer_connections.items():
        pc = peer_data.get("peer_conn")
        ice_transports = list(pc._RTCPeerConnection__iceTransports) if pc else []
        transport = ice_transports[0] if ice_transports else None
        dtls_transport = pc.sctp.transport if (pc and pc.sctp) else None
        peers_info.append({
            "peer_id": pid,
            "connection_state": pc.connectionState if pc else "unknown",
            "ice_connection_state": pc.iceConnectionState if pc else "unknown",
            "server_pc_id": id(pc) if pc else None,
            "server_dtls_id": id(dtls_transport) if dtls_transport else None,
            "diagnostics": transport.get_diagnostics() if hasattr(transport, "get_diagnostics") else {},
        })
    return web.json_response({"peers": peers_info})


async def handle_restart_ice(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception as e:
        return web.json_response({"error": f"Invalid JSON: {e}"}, status=400)

    client_peer_id = data.get("client_peer_id")
    ice_servers_data = data.get("ice_servers", [])
    force_relay = data.get("force_relay", False)

    if not _LIVE_WEBRTC_SERVICE or not _LIVE_WEBRTC_SERVICE.rtc_app:
        return web.json_response({"error": "WebRTC service not ready"}, status=503)

    peer_obj = _LIVE_WEBRTC_SERVICE.rtc_app.peer_connections.get(client_peer_id)
    if not peer_obj:
        return web.json_response({"error": f"Peer {client_peer_id} not found"}, status=404)

    peer_conn = peer_obj["peer_conn"]
    ice_transports = list(peer_conn._RTCPeerConnection__iceTransports)
    if not ice_transports:
        return web.json_response({"error": "No ICE transports found on peer connection"}, status=500)

    # Convert ice_servers_data to RTCIceServer objects
    ice_servers = []
    for s in ice_servers_data:
        ice_servers.append(RTCIceServer(
            urls=s.get("urls"),
            username=s.get("username"),
            credential=s.get("credential"),
        ))

    main_transport = peer_conn.sctp.transport.transport if (peer_conn.sctp and peer_conn.sctp.transport) else list(peer_conn._RTCPeerConnection__iceTransports)[0]

    logger.info("Executing server-side prepare_restart for client %s on main transport %s...", client_peer_id, main_transport)
    try:
        if isinstance(main_transport, Stage2GenerationIceTransport):
            await main_transport.prepare_restart(ice_servers=ice_servers, force_relay=force_relay)
        peer_conn._RTCPeerConnection__iceTransports = {main_transport}
    except Exception as e:
        logger.error("Failed prepare_restart for client %s: %s", client_peer_id, e)
        return web.json_response({"success": False, "error": str(e)}, status=400)

    # Create new offer on the existing RTCPeerConnection
    logger.info("Creating new SDP Offer on existing RTCPeerConnection for client %s...", client_peer_id)
    new_offer = await peer_conn.createOffer()
    await peer_conn.setLocalDescription(new_offer)

    # Send offer to client via standard Selkies signaling
    logger.info("Sending new SDP Offer to client %s via signaling...", client_peer_id)
    await _LIVE_WEBRTC_SERVICE.signaling_client.send_sdp("offer", new_offer.sdp, client_peer_id)

    return web.json_response({
        "success": True,
        "generation": getattr(main_transport, "generation", None),
        "local_ufrag": getattr(main_transport, "current_local_ufrag", None),
    })


async def start_aux_http_server():
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/peers", handle_peers)
    app.router.add_post("/restart_ice", handle_restart_ice)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 18092)
    await site.start()
    logger.info("Auxiliary HTTP control server listening on 0.0.0.0:18092")


# Patch selkies_main.run to start the auxiliary server concurrently
_orig_run = selkies_main.run
async def run_with_aux_server():
    await start_aux_http_server()
    await _orig_run()

selkies_main.run = run_with_aux_server

if __name__ == "__main__":
    selkies_main.main()
