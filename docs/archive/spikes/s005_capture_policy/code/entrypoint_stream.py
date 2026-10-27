"""
Custom entrypoint for Selkies Stream Runtime with in-process CapturePolicyAgent injected.
Monkey-patches selkies.__main__.WebRTCService with RealPolicyControlledWebRTCService,
then launches official run() under uvloop/asyncio.
"""
import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("stream_entrypoint")

import selkies.__main__ as selkies_main
from live_policy_agent import RealPolicyControlledWebRTCService, LiveCapturePolicyAgent

def patched_webrtc_service_factory(server):
    service = RealPolicyControlledWebRTCService(server)
    agent = LiveCapturePolicyAgent(service)
    # Schedule agent startup on server event loop
    asyncio.get_event_loop().call_soon(lambda: asyncio.create_task(agent.start()))
    return service

# Monkey-patch selkies.__main__.WebRTCService
selkies_main.WebRTCService = patched_webrtc_service_factory

if __name__ == "__main__":
    logger.info("Starting Selkies Stream Runtime with RealPolicyControlledWebRTCService...")
    # Invoke official selkies.main()
    selkies_main.main()
