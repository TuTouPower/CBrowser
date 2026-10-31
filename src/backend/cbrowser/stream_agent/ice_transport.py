"""Production ICE transport adapter and helper for Selkies 2.1.0 WebRTC.

Implements GenerationIceTransport:
- Patches selkies.webrtc.rtcpeerconnection.RTCIceTransport before RTCPeerConnection
creation
- Decouples DTLS / Pacer from underlying ICE connection instances
- Reusable across renegotiations on the SAME RTCPeerConnection, SAME
RTCDtlsTransport
- Supports custom iceServers and force_relay for strict relay TURN isolation
- Critical race protection during setLocalDescription -> wait for new remote answer
credentials
- True committed generation tracking: ensures new generation takes over, old
connection is retired and closed,
and old connection strictly rejects subsequent writes.
- Preserves profile-assigned UDP mux socket / port range / NAT 1-to-1 IPs across
generations
- Provides diagnostic state without leaking credentials in repr/logs.
- Explicit Selkies 2.1.0 version and private ABI guards; fails closed on unsupported
environments.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import selkies
    import selkies.ice
    import selkies.ice.turn as selkies_turn_mod
    import selkies.webrtc
    import selkies.webrtc.rtcpeerconnection as selkies_pc_mod
    from selkies.ice.ice import Connection, TransportPolicy
    from selkies.webrtc.rtcconfiguration import RTCIceServer
    from selkies.webrtc.rtcicetransport import (
        RTCIceCandidate,
        RTCIceGatherer,
        RTCIceParameters,
        RTCIceTransport,
    )

    _SELKIES_AVAILABLE = True
except ImportError:
    _SELKIES_AVAILABLE = False
    Connection = object
    TransportPolicy = object
    RTCIceServer = object
    RTCIceCandidate = object
    RTCIceGatherer = object
    RTCIceParameters = object
    RTCIceTransport = object

logger = logging.getLogger("cbrowser.stream_agent.ice_transport")

EXPECTED_SELKIES_VERSION = "2.1.0"
EXPECTED_WEBRTC_VERSION = "1.15.0"
EXPECTED_ICE_VERSION = "0.10.2"

_RELAY_ONLY: bool = False


def set_relay_only(enabled: bool) -> None:
    """Set whether new PeerConnections must only gather and use relay candidates."""
    global _RELAY_ONLY
    _RELAY_ONLY = bool(enabled)
    logger.info("ICE transport relay_only policy set to: %s", _RELAY_ONLY)


def is_relay_only() -> bool:
    """Check whether relay_only ICE policy is active."""
    return _RELAY_ONLY


class UnsupportedSelkiesVersionError(RuntimeError):
    """Raised when runtime versions differ from the pinned Selkies ABI."""

    pass


class SelkiesABIGuardError(RuntimeError):
    """Raised when private internal attributes required for generation switching are
    missing.
    """

    pass


def verify_selkies_abi_guard() -> None:
    """Verify that the environment has Selkies 2.1.0 and all required private ABI
    attributes.
    Fails closed immediately if any check does not match.
    """
    if not _SELKIES_AVAILABLE:
        raise UnsupportedSelkiesVersionError(
            "Selkies WebRTC SDK is not installed or importable."
        )

    selkies_ver = getattr(selkies, "__version__", None)
    webrtc_ver = getattr(selkies.webrtc, "__version__", None)
    ice_ver = getattr(selkies.ice, "__version__", None)

    if selkies_ver != EXPECTED_SELKIES_VERSION:
        raise UnsupportedSelkiesVersionError(
            f"Unsupported selkies version: {selkies_ver!r} (expected"
            f" {EXPECTED_SELKIES_VERSION!r})"
        )
    if webrtc_ver != EXPECTED_WEBRTC_VERSION:
        raise UnsupportedSelkiesVersionError(
            f"Unsupported selkies.webrtc version: {webrtc_ver!r} (expected"
            f" {EXPECTED_WEBRTC_VERSION!r})"
        )
    if ice_ver != EXPECTED_ICE_VERSION:
        raise UnsupportedSelkiesVersionError(
            f"Unsupported selkies.ice version: {ice_ver!r} (expected"
            f" {EXPECTED_ICE_VERSION!r})"
        )

    # Check RTCPeerConnection and RTCIceTransport by instantiating minimal objects
    # Note: Private attributes mangled by Python (__name) are initialized on instances
    # in __init__.
    try:
        sample_gatherer = RTCIceGatherer()
        sample_transport = RTCIceTransport(sample_gatherer)
        for attr in (
            "_RTCIceTransport__iceGatherer",
            "_RTCIceTransport__monitor_task",
            "_RTCIceTransport__start",
        ):
            if not hasattr(sample_transport, attr):
                raise SelkiesABIGuardError(
                    f"RTCIceTransport missing expected private attribute {attr!r}"
                )

        sample_pc = selkies_pc_mod.RTCPeerConnection()
        if not hasattr(sample_pc, "_RTCPeerConnection__iceTransports"):
            raise SelkiesABIGuardError(
                "RTCPeerConnection missing private attribute"
                " '_RTCPeerConnection__iceTransports'"
            )
    except (UnsupportedSelkiesVersionError, SelkiesABIGuardError):
        raise
    except Exception as e:
        raise SelkiesABIGuardError(
            f"Failed instantiating sample Selkies objects for ABI guard check: {e}"
        ) from e


def parse_ice_server(server_entry: Union[dict, Any]) -> Any:
    """
    Validate and parse a single ICE server dictionary or RTCIceServer object.
    Fails closed on invalid formats or disallowed types.
    """
    if isinstance(server_entry, RTCIceServer) and _SELKIES_AVAILABLE:
        return server_entry

    if not isinstance(server_entry, dict):
        raise ValueError(
            f"Invalid ice_server entry type: {type(server_entry).__name__}, expected"
            f" dict or RTCIceServer"
        )

    urls = server_entry.get("urls")
    if not urls:
        raise ValueError("Missing 'urls' field in ice_server entry")

    if isinstance(urls, str):
        urls_list = [urls]
    elif isinstance(urls, (list, tuple)):
        urls_list = list(urls)
    else:
        raise ValueError(f"Invalid urls type: {type(urls).__name__}")

    for u in urls_list:
        if not isinstance(u, str):
            raise ValueError(f"URL entry must be string, got {type(u).__name__}")
        if not (
            u.startswith("stun:") or u.startswith("turn:") or u.startswith("turns:")
        ):
            raise ValueError("Unsupported ICE server scheme")

    username = server_entry.get("username")
    credential = server_entry.get("credential")

    if username is not None and not isinstance(username, str):
        raise ValueError("username must be a string if provided")
    if credential is not None and not isinstance(credential, str):
        raise ValueError("credential must be a string if provided")

    if not _SELKIES_AVAILABLE:
        # Return dict representation when SDK is not importable on host
        return {
            "urls": urls_list if len(urls_list) > 1 else urls_list[0],
            "username": username,
            "credential": credential,
        }

    return RTCIceServer(
        urls=urls_list if len(urls_list) > 1 else urls_list[0],
        username=username,
        credential=credential,
    )


def validate_ice_servers(servers: Optional[List[Union[dict, Any]]]) -> List[Any]:
    """Parse and validate a list of ICE servers."""
    if not servers:
        return []
    if not isinstance(servers, (list, tuple)):
        raise ValueError("ice_servers must be a list")
    return [parse_ice_server(s) for s in servers]


class _BaseIceTransport:
    def __init__(self, gatherer: Any):
        self._connection = getattr(gatherer, "_connection", None)
        self._RTCIceTransport__iceGatherer = gatherer
        self._RTCIceTransport__monitor_task = None
        self._RTCIceTransport__start = None


class _CancellationSafeTurnTransport(
    selkies_turn_mod.TurnTransport if _SELKIES_AVAILABLE else object
):
    """Close the fixed SDK's unregistered TURN socket on allocation cancellation."""

    async def _connect(self, protocol: Any) -> None:
        try:
            await super()._connect(protocol)
        except BaseException:
            # Selkies ICE 0.10.2 catches Exception in create_turn_endpoint, which
            # excludes CancelledError. The connection does not own this socket
            # until allocation succeeds, so Connection.close cannot release it.
            self._TurnTransport__inner_protocol.transport.close()
            raise


class GenerationIceTransport(
    RTCIceTransport if _SELKIES_AVAILABLE else _BaseIceTransport
):
    """
    WebRTC ICE transport with generation-aware continuity on Selkies 2.1.0.
    Decouples DTLS / SCTP / Track lifetimes from underlying ICE connections,
    allowing in-place ICE restarts on the exact same RTCPeerConnection.
    """

    def __init__(self, gatherer: Any):
        verify_selkies_abi_guard()
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

        self.relay_only: bool = _RELAY_ONLY
        if self.relay_only:
            if hasattr(gatherer, "_connection") and gatherer._connection is not None:
                gatherer._connection._transport_policy = TransportPolicy.RELAY
            self._wrap_gatherer_for_relay_only(gatherer)

        # Intercept before DTLS and Pacer capture them
        self._recv = self.receive_packet
        self._send = self.send_packet

    def _wrap_gatherer_for_relay_only(self, gatherer: Any) -> None:
        orig_gather = getattr(gatherer, "gather", None)
        if orig_gather is None:
            return

        async def _relay_gather() -> None:
            await orig_gather()
            conn = getattr(gatherer, "_connection", None)
            if conn is not None:
                relay_cands = [
                    c
                    for c in getattr(conn, "local_candidates", [])
                    if getattr(c, "type", None) == "relay"
                ]
                if not relay_cands:
                    logger.error(
                        "No relay candidates gathered in relay-only mode "
                        "(gathered %d candidates)",
                        len(getattr(conn, "local_candidates", [])),
                    )
                    raise RuntimeError("Relay candidates unavailable")
                conn._local_candidates = relay_cands
                logger.info(
                    "Restricted peer candidates to %d relay candidates",
                    len(relay_cands),
                )

        gatherer.gather = _relay_gather

    def __repr__(self) -> str:
        return (
            f"<GenerationIceTransport gen={self.generation} "
            f"active_gen={self.active_generation}"
            f" committed_gen={self.committed_generation} "
            f"local_ufrag={self.current_local_ufrag!r} pending={self.restart_pending}>"
        )

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
        ice_servers: Optional[List[Any]] = None,
        force_relay: bool = False,
    ) -> None:
        """Prepare a new generation ICE gatherer before SDP renegotiation.
        Preserves existing UDP mux socket, port range, and NAT 1-to-1 IPs.
        Gathers candidates before updating pointers to ensure rollback safety on
        gather failure.
        """
        async with self.restart_lock:
            if self.restart_pending:
                raise RuntimeError("Previous ICE restart is still pending")

            old_conn = self._connection
            next_generation = self.generation + 1
            effective_force_relay = force_relay or self.relay_only or _RELAY_ONLY
            logger.info(
                "Preparing ICE restart generation %d (force_relay=%s)",
                next_generation,
                effective_force_relay,
            )

            parsed_servers = validate_ice_servers(ice_servers)

            # Preserve Profile-assigned socket parameters from old connection
            nat1to1_ips = None
            if hasattr(old_conn, "_nat1to1_ips") and old_conn._nat1to1_ips:
                nat1to1_ips = list(old_conn._nat1to1_ips.values())

            # Construct new gatherer preserving mux, port range, NAT IPs, and lite flag
            new_gatherer = RTCIceGatherer(
                iceServers=parsed_servers,
                ice_host_public_ips=nat1to1_ips,
                ice_port_range=getattr(old_conn, "_port_range", None),
                ice_udp_mux=getattr(old_conn, "_udp_mux", None),
                ice_tcp_mux=getattr(old_conn, "_tcp_mux", None),
                ice_lite=getattr(old_conn, "ice_lite", False),
            )
            new_gatherer._connection.ice_controlling = old_conn.ice_controlling

            if effective_force_relay:
                new_gatherer._connection._transport_policy = TransportPolicy.RELAY

            # Candidate preparation is provisional. On failure or cancellation,
            # release only the new connection and preserve the live generation.
            gather_task = asyncio.create_task(new_gatherer.gather())
            try:
                # Native gather owns provisional endpoints before registering
                # them on Connection. Drain it before disposing after cancellation.
                await asyncio.shield(gather_task)
                if effective_force_relay:
                    relay_cands = [
                        candidate
                        for candidate in new_gatherer._connection.local_candidates
                        if candidate.type == "relay"
                    ]
                    if not relay_cands:
                        raise RuntimeError("Relay candidates unavailable")
                    new_gatherer._connection._local_candidates = relay_cands
            except BaseException as error:
                self.last_error = (
                    f"Candidate preparation failed: {type(error).__name__}"
                )
                await asyncio.gather(gather_task, return_exceptions=True)
                await new_gatherer._connection.close()
                raise

            # Only a successfully gathered generation may reset SDK observation.
            self.previous_remote_credentials = (
                old_conn.remote_username,
                old_conn.remote_password,
            )
            # Stop old monitor task so it does not interfere with the new generation
            monitor = self._RTCIceTransport__monitor_task
            if monitor:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)
            self._RTCIceTransport__monitor_task = None
            self._RTCIceTransport__start = None

            # Candidate gathering succeeded; commit generation advancement
            self.generation = next_generation
            self.current_local_ufrag = (
                new_gatherer.getLocalParameters().usernameFragment
            )
            self._RTCIceTransport__iceGatherer = new_gatherer
            self._connection = new_gatherer._connection
            self.restart_pending = True
            logger.info(
                "Generation %d prepared with local_ufrag: %s",
                self.generation,
                self.current_local_ufrag,
            )

    async def start(self, remote_parameters: RTCIceParameters) -> None:
        """Start connectivity checks for the new generation.
        Fences against race condition where setLocalDescription preliminary triggers
        __connect
        with previous remote credentials.
        Once the new generation completes:
        - Transfers active connection and packet pump to the new generation
        - Retires and closes old connection (tearing down old TURN allocation)
        - Verifies that old connection strictly rejects subsequent writes
        """
        # Critical race fence:
        # setLocalDescription automatically schedules __connect before new remote Answer
        # arrives.
        # If credentials match previous generation, ignore this preliminary invocation.
        if (
            self.restart_pending
            and self.previous_remote_credentials is not None
            and (remote_parameters.usernameFragment, remote_parameters.password)
            == self.previous_remote_credentials
        ):
            logger.debug(
                "Ignoring preliminary start() with old remote credentials during"
                " pending restart"
            )
            return

        async with self.restart_lock:
            previous_conn = self.active_connection
            old_gen = self.active_generation
            logger.info(
                "Starting ICE connection for generation %d (remote_ufrag: %s)",
                self.generation,
                remote_parameters.usernameFragment,
            )
            await super().start(remote_parameters)
            if self.state != "completed":
                raise ConnectionError(
                    f"ICE generation {self.generation} did not complete"
                    f" (state={self.state})"
                )

            # Start pump on new active connection
            self.start_pump(self._connection)
            self.active_connection = self._connection
            self.active_generation = self.generation
            self.current_remote_ufrag = remote_parameters.usernameFragment
            logger.info(
                "ICE generation %d successfully active and pumping", self.generation
            )

            if self.restart_pending:
                # Clean up old pump
                old_pump = self.pumps.pop(previous_conn, None)
                if old_pump:
                    old_pump.cancel()
                    await asyncio.gather(old_pump, return_exceptions=True)

                # Close old connection which tears down old TURN allocation
                await previous_conn.close()

                # Verify old connection strictly rejects subsequent writes
                send_rejected = False
                try:
                    await previous_conn.send(b"retired-generation-must-reject")
                except ConnectionError:
                    send_rejected = True
                except Exception as e:
                    send_rejected = True
                    logger.debug(
                        "Old connection rejected send with %s", type(e).__name__
                    )

                if not send_rejected:
                    raise RuntimeError(
                        f"Retired ICE generation {old_gen} still accepted writes!"
                    )

                self.retired_generations.append(
                    {
                        "generation": old_gen,
                        "closed": True,
                        "send_rejected": True,
                    }
                )
                self.committed_generation = self.generation
                self.restart_pending = False
                logger.info(
                    "Generation %d officially committed. Retired generation %d "
                    "closed and rejected writes.",
                    self.committed_generation,
                    old_gen,
                )

    async def stop(self) -> None:
        """Irreversibly stop the transport and all pumps."""
        self.packets.put_nowait(None)
        for task in list(self.pumps.values()):
            task.cancel()
        if self.pumps:
            await asyncio.gather(*self.pumps.values(), return_exceptions=True)
        self.pumps.clear()
        try:
            await super().stop()
        finally:
            # During negotiation the SDK points at the pending connection while
            # DTLS still uses the old active generation. Both belong to this peer.
            if self.active_connection is not self._connection:
                await self.active_connection.close()

    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Return diagnostic state without leaking credentials or passwords.
        """
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


def install_ice_transport() -> None:
    """
    Patch selkies.webrtc.rtcpeerconnection.RTCIceTransport with GenerationIceTransport.
    Must be called before SDK RTCPeerConnection creation.
    Fails closed if the environment does not match Selkies 2.1.0 pinned ABI.
    """
    verify_selkies_abi_guard()
    selkies_turn_mod.TurnTransport = _CancellationSafeTurnTransport
    selkies_pc_mod.RTCIceTransport = GenerationIceTransport
    logger.info(
        "Installed GenerationIceTransport into selkies.webrtc.rtcpeerconnection"
    )


def _main_transport(peer_connection: Any) -> "GenerationIceTransport":
    """Return the generation-aware ICE transport carrying the peer's bundle."""
    verify_selkies_abi_guard()

    if not hasattr(peer_connection, "_RTCPeerConnection__iceTransports"):
        raise SelkiesABIGuardError(
            "PeerConnection is not a valid Selkies RTCPeerConnection instance"
        )

    ice_transports = list(peer_connection._RTCPeerConnection__iceTransports)
    if not ice_transports:
        raise RuntimeError("No ICE transports found on peer_connection")

    # Locate main transport (associated with SCTP or primary transceiver)
    if (
        hasattr(peer_connection, "sctp")
        and peer_connection.sctp
        and hasattr(peer_connection.sctp, "transport")
    ):
        main_transport = peer_connection.sctp.transport.transport
    else:
        main_transport = ice_transports[0]

    if not isinstance(main_transport, GenerationIceTransport):
        raise TypeError(
            f"Main transport is {type(main_transport).__name__}, not"
            f" GenerationIceTransport. "
            "install_ice_transport() must be called before peer connection creation."
        )
    return main_transport


async def create_restart_offer(
    peer_connection: Any,
    server_ice_servers: Optional[List[Union[dict, Any]]] = None,
    force_relay: bool = False,
) -> Any:
    """Prepares the main existing transport on peer_connection for an ICE restart
    generation,
    creates an SDP offer on the existing RTCPeerConnection, sets localDescription,
    and returns pc.localDescription.
    Does NOT send network RPC (the caller handles forwarding to Gateway/Viewer).
    """
    main_transport = _main_transport(peer_connection)

    # Prepare next generation on the existing transport
    await main_transport.prepare_restart(
        ice_servers=server_ice_servers, force_relay=force_relay
    )

    # Ensure RTCPeerConnection tracks the main transport
    peer_connection._RTCPeerConnection__iceTransports = {main_transport}

    # Create offer on the SAME RTCPeerConnection and set local description
    offer = await peer_connection.createOffer()
    await peer_connection.setLocalDescription(offer)

    return peer_connection.localDescription


async def wait_restart_commit(peer_connection: Any, timeout: float) -> int:
    """Wait until the pending ICE generation on peer_connection is committed.

    Selkies runs connectivity checks for a remote answer in a background task,
    so setRemoteDescription returning does not mean the new generation took
    over. Returns the committed generation; raises ConnectionError when the
    transport fails or the generation is not committed within timeout.
    """
    transport = _main_transport(peer_connection)
    target = transport.generation
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while transport.restart_pending or transport.committed_generation < target:
        if transport.state in ("failed", "closed"):
            raise ConnectionError(
                f"ICE generation {target} failed (state={transport.state})"
            )
        if loop.time() >= deadline:
            raise ConnectionError(
                f"ICE generation {target} not committed within {timeout:.0f}s"
            )
        await asyncio.sleep(0.05)
    return transport.committed_generation


__all__ = [
    "GenerationIceTransport",
    "install_ice_transport",
    "create_restart_offer",
    "wait_restart_commit",
    "verify_selkies_abi_guard",
    "validate_ice_servers",
    "parse_ice_server",
    "set_relay_only",
    "is_relay_only",
    "UnsupportedSelkiesVersionError",
    "SelkiesABIGuardError",
]
