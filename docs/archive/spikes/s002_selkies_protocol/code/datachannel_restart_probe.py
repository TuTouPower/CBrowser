"""Experimental adapter; this does not modify the installed Selkies package."""

import asyncio
import json

from selkies.webrtc import RTCConfiguration, RTCPeerConnection
from selkies.webrtc.rtcconfiguration import RTCBundlePolicy
from selkies.webrtc.rtcicetransport import RTCIceGatherer, RTCIceTransport
import selkies.webrtc.rtcpeerconnection as pc_module


class GenerationIceTransport(RTCIceTransport):
    def __init__(self, gatherer):
        super().__init__(gatherer)
        self.active_connection = self._connection
        self.packets = asyncio.Queue()
        self.pumps = {}
        self.restart_pending = False
        self.restart_lock = asyncio.Lock()
        # Stable callbacks are installed before DTLS / pacer construction.
        self._recv = self.receive_packet
        self._send = self.send_packet

    async def receive_packet(self):
        packet = await self.packets.get()
        if packet is None:
            raise ConnectionError('ICE transport stopped')
        return packet

    async def send_packet(self, packet):
        return await self.active_connection.send(packet)

    async def pump(self, connection):
        try:
            while True:
                self.packets.put_nowait(await connection.recv())
        except ConnectionError:
            return

    def start_pump(self, connection):
        if connection not in self.pumps:
            self.pumps[connection] = asyncio.create_task(self.pump(connection))

    async def prepare_restart(self):
        assert not self.restart_pending
        old = self._connection
        self.previous_remote_credentials = (old.remote_username, old.remote_password)
        gatherer = RTCIceGatherer(iceServers=[])
        gatherer._connection.ice_controlling = old.ice_controlling
        monitor = self._RTCIceTransport__monitor_task
        if monitor:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
        self._RTCIceTransport__monitor_task = None
        self._RTCIceTransport__start = None
        self._RTCIceTransport__iceGatherer = gatherer
        self._connection = gatherer._connection
        self.restart_pending = True
        await gatherer.gather()

    async def start(self, remote_parameters):
        if self.restart_pending and (remote_parameters.usernameFragment, remote_parameters.password) == self.previous_remote_credentials:
            return  # setLocalDescription schedules connect before the new remote answer.
        async with self.restart_lock:
            previous = self.active_connection
            await super().start(remote_parameters)
            if self.state != 'completed':
                raise ConnectionError('ICE generation did not connect')
            self.start_pump(self._connection)
            self.active_connection = self._connection
            if self.restart_pending:
                old_pump = self.pumps.pop(previous, None)
                if old_pump:
                    old_pump.cancel()
                    await asyncio.gather(old_pump, return_exceptions=True)
                await previous.close()
                self.restart_pending = False

    async def stop(self):
        connections = set(self.pumps) | {self.active_connection, self._connection}
        self.packets.put_nowait(None)
        for task in self.pumps.values():
            task.cancel()
        await asyncio.gather(*self.pumps.values(), return_exceptions=True)
        self.pumps.clear()
        await super().stop()
        await asyncio.gather(*(connection.close() for connection in connections if connection is not self._connection))


async def negotiate(a, b):
    await a.setLocalDescription(await a.createOffer())
    await b.setRemoteDescription(a.localDescription)
    await b.setLocalDescription(await b.createAnswer())
    await a.setRemoteDescription(b.localDescription)


async def experiment():
    pc_module.RTCIceTransport = GenerationIceTransport
    config = RTCConfiguration(iceServers=[], bundlePolicy=RTCBundlePolicy.MAX_BUNDLE)
    a, b = RTCPeerConnection(config), RTCPeerConnection(config)
    incoming = asyncio.Queue()
    remote = []
    channel = a.createDataChannel('generation-continuity')
    @b.on('datachannel')
    def on_channel(other):
        remote.append(other)
        other.on('message', incoming.put_nowait)
    async def wait_for(test):
        async with asyncio.timeout(8):
            while not test():
                await asyncio.sleep(.05)
    try:
        await negotiate(a, b)
        await wait_for(lambda: channel.readyState == 'open' and remote)
        channel.send(b'before-generation')
        assert await asyncio.wait_for(incoming.get(), 3) == b'before-generation'
        ice_a, ice_b = a.sctp.transport.transport, b.sctp.transport.transport
        objects = (a, b, a.sctp, b.sctp, a.sctp.transport, b.sctp.transport, ice_a, ice_b, channel, remote[0])
        identity = tuple(map(id, objects))
        for generation in range(3):
            old = (ice_a.active_connection, ice_b.active_connection)
            old_creds = (ice_a.iceGatherer.getLocalParameters(), ice_b.iceGatherer.getLocalParameters())
            await asyncio.gather(ice_a.prepare_restart(), ice_b.prepare_restart())
            await negotiate(a, b)
            await wait_for(lambda: not ice_a.restart_pending and not ice_b.restart_pending)
            await asyncio.sleep(.5)
            for i in range(10):
                packet = f'after-generation-{generation}-{i}'.encode()
                channel.send(packet)
                assert await asyncio.wait_for(incoming.get(),3) == packet
                await asyncio.sleep(.05)
            current = (a, b, a.sctp, b.sctp, a.sctp.transport, b.sctp.transport,
                       a.sctp.transport.transport, b.sctp.transport.transport, channel, remote[0])
            assert identity == tuple(map(id,current))
            new_creds = (ice_a.iceGatherer.getLocalParameters(), ice_b.iceGatherer.getLocalParameters())
            assert all(x.usernameFragment != y.usernameFragment and x.password != y.password for x,y in zip(old_creds,new_creds))
            assert all(x is not y for x,y in zip(old,(ice_a.active_connection,ice_b.active_connection)))
            for old_connection in old:
                try:
                    await old_connection.send(b'retired-generation-must-reject')
                except ConnectionError:
                    pass
                else:
                    raise AssertionError('Retired ICE generation still accepted writes')
        print(json.dumps({'same_pc_sctp_dtls_ice_datachannel_objects':True,
                          'new_ice_credentials_both_ends':True,'old_connections_closed':True,
                          'post_restart_exact_packets':30,'successful_ice_restarts':3,'webrtc_media':'NOT_TESTED'}),flush=True)
    finally:
        await asyncio.gather(a.close(), b.close())


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(experiment(),timeout=30))
