"""
Stage 2 ICE Restart Adapter for Selkies 2.1.0 WebRTC.
Extends GenerationIceTransport from root probe:
- Decouples DTLS / Pacer from underlying ICE connection instances
- Reusable across renegotiations on the SAME RTCPeerConnection, SAME RTCDtlsTransport
- Supports custom iceServers and force_relay_only for strict relay TURN isolation
- Critical race protection during setLocalDescription -> wait for new remote answer credentials
- True committed generation tracking: ensures new generation takes over, old connection is retired and closed,
  and old connection strictly rejects subsequent writes.
- Provides diagnostic state without leaking credentials.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from selkies.ice.ice import Connection, TransportPolicy
from selkies.webrtc.rtcconfiguration import RTCIceServer
from selkies.webrtc.rtcicetransport import (
    RTCIceCandidate,
    RTCIceGatherer,
    RTCIceParameters,
    RTCIceTransport,
    candidate_from_aioice,
)

logger = logging.getLogger("stage2_adapter")


class Stage2GenerationIceTransport(RTCIceTransport):
    def __init__(self, gatherer: RTCIceGatherer):
        super().__init__(gatherer)
        self.generation: int = 1
        self.active_generation: int = 1
        self.committed_generation: int = 1
        self.active_connection: Connection = self._connection
        self.packets: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self.pumps: dict[Connection, asyncio.Task] = {}
        self.restart_pending: bool = False
        self.restart_lock: asyncio.Lock = asyncio.Lock()
        self.previous_remote_credentials: Optional[Tuple[str, str]] = None
        self.retired_generations: list[Dict[str, Any]] = []

        self.current_local_ufrag: str = self._connection.local_username
        self.current_remote_ufrag: Optional[str] = None
        self.last_error: Optional[str] = None

        # Intercept before DTLS and pacer capture them
        self._recv = self.receive_packet
        self._send = self.send_packet

    async def receive_packet(self) -> bytes:
        packet = await self.packets.get()
        if packet is None:
            raise ConnectionError("ICE transport generation stopped")
        return packet

    async def send_packet(self, packet: bytes) -> None:
        if self.active_connection._closed:
            raise ConnectionError("Active ICE connection is closed")
        await self.active_connection.send(packet)

    async def pump(self, connection: Connection) -> None:
        try:
            while not connection._closed:
                pkt = await connection.recv()
                self.packets.put_nowait(pkt)
        except (ConnectionError, asyncio.CancelledError):
            return
        except Exception as e:
            logger.debug("Pump ended with %s", type(e).__name__)
            return

    def start_pump(self, connection: Connection) -> None:
        if connection not in self.pumps or self.pumps[connection].done():
            self.pumps[connection] = asyncio.create_task(self.pump(connection))

    async def prepare_restart(
        self,
        ice_servers: Optional[List[RTCIceServer]] = None,
        force_relay: bool = False,
    ) -> None:
        async with self.restart_lock:
            assert not self.restart_pending, "Previous restart still pending"
            old = self._connection
            self.previous_remote_credentials = (old.remote_username, old.remote_password)
            next_generation = self.generation + 1
            logger.info("Preparing ICE restart generation %d (force_relay=%s)", next_generation, force_relay)

            servers = ice_servers if ice_servers is not None else []
            # Create fresh gatherer
            gatherer = RTCIceGatherer(iceServers=servers)
            gatherer._connection.ice_controlling = old.ice_controlling

            if force_relay:
                gatherer._connection._transport_policy = TransportPolicy.RELAY

            # Stop old monitor task so it does not interfere
            monitor = self._RTCIceTransport__monitor_task
            if monitor:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)
            self._RTCIceTransport__monitor_task = None
            self._RTCIceTransport__start = None

            # Perform candidate gathering on new generation BEFORE committing pointers
            try:
                await gatherer.gather()
            except Exception as e:
                self.last_error = f"Gather error: {e}"
                logger.error("Failed gathering candidates for generation %d: %s", next_generation, e)
                raise

            if force_relay:
                relay_cands = [c for c in gatherer._connection.local_candidates if c.type == "relay"]
                if not relay_cands:
                    self.last_error = f"Zero relay candidates gathered for generation {next_generation}"
                    logger.error("Zero relay candidates gathered for generation %d! Rejecting restart.", next_generation)
                    raise RuntimeError(f"Zero relay candidates gathered for generation {next_generation}")
                gatherer._connection._local_candidates = relay_cands
                logger.info("Generation %d gathered %d candidates (all relay: True)", next_generation, len(relay_cands))

            # Candidate gathering succeeded; commit generation advancement
            self.generation = next_generation
            self.current_local_ufrag = gatherer.getLocalParameters().usernameFragment
            self._RTCIceTransport__iceGatherer = gatherer
            self._connection = gatherer._connection
            self.restart_pending = True
            logger.info("Generation %d prepared with local_ufrag: %s", self.generation, self.current_local_ufrag)

    async def start(self, remote_parameters: RTCIceParameters) -> None:
        # Critical race fix from root probe:
        # setLocalDescription automatically schedules __connect before new remote Answer arrives.
        # If credentials match previous generation, ignore this preliminary invocation.
        if (
            self.restart_pending
            and self.previous_remote_credentials is not None
            and (remote_parameters.usernameFragment, remote_parameters.password)
            == self.previous_remote_credentials
        ):
            logger.debug("Ignoring preliminary start() with old remote credentials during pending restart")
            return

        async with self.restart_lock:
            previous = self.active_connection
            old_gen = self.active_generation
            logger.info("Starting ICE connection for generation %d (remote_ufrag: %s)",
                        self.generation, remote_parameters.usernameFragment)
            await super().start(remote_parameters)
            if self.state != "completed":
                raise ConnectionError(f"ICE generation {self.generation} did not complete (state={self.state})")

            # Start pump on new active connection
            self.start_pump(self._connection)
            self.active_connection = self._connection
            self.active_generation = self.generation
            self.current_remote_ufrag = remote_parameters.usernameFragment
            logger.info("ICE generation %d successfully active and pumping", self.generation)

            if self.restart_pending:
                # Clean up old generation
                old_pump = self.pumps.pop(previous, None)
                if old_pump:
                    old_pump.cancel()
                    await asyncio.gather(old_pump, return_exceptions=True)

                # Close old connection which tears down old TURN allocation
                await previous.close()

                # Verify old connection strictly rejects subsequent writes
                send_rejected = False
                try:
                    await previous.send(b"retired-generation-must-reject")
                except ConnectionError:
                    send_rejected = True
                except Exception as e:
                    send_rejected = True
                    logger.debug("Old connection rejected send with %s", type(e).__name__)

                assert send_rejected, f"Retired ICE generation {old_gen} still accepted writes!"

                self.retired_generations.append({
                    "generation": old_gen,
                    "closed": True,
                    "send_rejected": send_rejected,
                })
                self.committed_generation = self.generation
                self.restart_pending = False
                logger.info("Generation %d officially committed. Retired generation %d confirmed closed and rejecting writes.",
                            self.committed_generation, old_gen)

    async def stop(self) -> None:
        self.packets.put_nowait(None)
        for task in self.pumps.values():
            task.cancel()
        await asyncio.gather(*self.pumps.values(), return_exceptions=True)
        self.pumps.clear()
        await super().stop()

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "generation": self.generation,
            "active_generation": self.active_generation,
            "committed_generation": self.committed_generation,
            "restart_pending": self.restart_pending,
            "local_ufrag": self.current_local_ufrag,
            "remote_ufrag": self.current_remote_ufrag,
            "retired_generations": list(self.retired_generations),
            "last_error": self.last_error,
        }
