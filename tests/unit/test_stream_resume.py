"""Selkies session resume across viewer signaling reconnects (p008)."""

import asyncio
import json

import aiohttp
import pytest
from aiohttp import WSMsgType, web
from cbrowser.stream_agent.agent import StreamAgent, ViewerWorkerEntry
from cbrowser.stream_agent.config import StreamAgentConfig
from pydantic import SecretStr

HELLO = (
    'HELLO client {"client_tab_id":"tab-1","resume_key":"resume-1"}'
)


async def _wait_for(predicate, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met before timeout")


class FakeSelkies:
    def __init__(self):
        self.app = web.Application()
        self.app.router.add_get("/upstream", self._handle)
        self.sessions: dict[str, web.WebSocketResponse] = {}
        self.sockets: list[web.WebSocketResponse] = []
        self.closed_sockets: list[web.WebSocketResponse] = []
        self.resumed = asyncio.Event()
        self.hello_seen = asyncio.Event()
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self.port = 0

    async def start(self) -> None:
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        self.port = self.site._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        for ws in self.sockets:
            if not ws.closed:
                await ws.close()
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

    async def _handle(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.sockets.append(ws)
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT or not msg.data.startswith(
                    "HELLO client "
                ):
                    continue
                meta = json.loads(msg.data.split(" ", 2)[2])
                key = meta["resume_key"]
                previous = self.sessions.get(key)
                previous_open = previous is not None and not previous.closed
                self.sessions[key] = ws
                self.hello_seen.set()
                if previous_open:
                    self.resumed.set()
                    await ws.send_str("RESUMED peer-1")
                    await previous.close(
                        code=1000, message=b"Resumed on a new connection."
                    )
                else:
                    await ws.send_str("SESSION_OK peer-1")
        finally:
            self.closed_sockets.append(ws)
        return ws


class FakeGateway:
    def __init__(self):
        self.closed = False
        self.sent: list[str] = []

    async def send_str(self, data: str) -> None:
        self.sent.append(data)


def _config() -> StreamAgentConfig:
    return StreamAgentConfig(
        profile_id="p1",
        runtime_instance_id="r1",
        gateway_url="ws://127.0.0.1:1/register",
        agent_token=SecretStr("agent-secret"),
        turn_host="127.0.0.1",
        turn_port=3478,
        controller_token=SecretStr("controller-token"),
    )


async def _start_worker(
    agent: StreamAgent,
    session,
    conn_id: str,
    generation: int,
) -> tuple[FakeGateway, asyncio.Queue]:
    gateway = FakeGateway()
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(
        agent._viewer_upstream_worker(session, gateway, conn_id, queue, generation)
    )
    agent.viewer_workers[conn_id] = ViewerWorkerEntry(
        generation=generation,
        task=task,
        queue=queue,
    )
    await queue.put({"type": "msg", "data": HELLO})
    await _wait_for(
        lambda: agent.viewer_workers[conn_id].resume_key == "resume-1"
    )
    return gateway, queue


@pytest.mark.asyncio
async def test_viewer_close_keeps_selkies_session_for_resume() -> None:
    upstream = FakeSelkies()
    await upstream.start()
    agent = StreamAgent(
        _config(),
        upstream_url=f"ws://127.0.0.1:{upstream.port}/upstream",
        resume_grace_seconds=1.0,
    )
    agent.agent_session_id = "sess_test"
    session = aiohttp.ClientSession()
    try:
        _gateway_one, _ = await _start_worker(agent, session, "conn-1", 1)
        await _wait_for(upstream.hello_seen.is_set)

        await agent._detach_viewer("conn-1")

        assert "conn-1" not in agent.viewer_workers
        assert ("tab-1", "resume-1") in agent._detached_upstreams
        assert upstream.sockets[0].closed is False

        gateway_two, _ = await _start_worker(agent, session, "conn-2", 2)
        await asyncio.wait_for(upstream.resumed.wait(), timeout=3.0)
        await _wait_for(lambda: not agent._detached_upstreams)
        await _wait_for(lambda: any("RESUMED" in item for item in gateway_two.sent))

        assert upstream.sockets[0].closed is True
        await agent.stop()
    finally:
        await session.close()
        await upstream.stop()


@pytest.mark.asyncio
async def test_gateway_disconnect_detaches_and_stop_closes() -> None:
    upstream = FakeSelkies()
    await upstream.start()
    agent = StreamAgent(
        _config(),
        upstream_url=f"ws://127.0.0.1:{upstream.port}/upstream",
        resume_grace_seconds=1.0,
    )
    agent.agent_session_id = "sess_test"
    session = aiohttp.ClientSession()
    try:
        await _start_worker(agent, session, "conn-1", 1)
        await _wait_for(upstream.hello_seen.is_set)

        await agent._cleanup_all_viewers(caller="gateway_disconnect")

        assert agent.viewer_workers == {}
        assert ("tab-1", "resume-1") in agent._detached_upstreams
        assert upstream.sockets[0].closed is False

        await agent.stop()

        assert agent._detached_upstreams == {}
        assert upstream.sockets[0].closed is True
    finally:
        await session.close()
        await upstream.stop()


@pytest.mark.asyncio
async def test_detached_session_expires_after_grace() -> None:
    upstream = FakeSelkies()
    await upstream.start()
    agent = StreamAgent(
        _config(),
        upstream_url=f"ws://127.0.0.1:{upstream.port}/upstream",
        resume_grace_seconds=0.2,
    )
    agent.agent_session_id = "sess_test"
    agent.agent_session_id = "sess_test"
    session = aiohttp.ClientSession()
    try:
        await _start_worker(agent, session, "conn-1", 1)
        await _wait_for(upstream.hello_seen.is_set)

        await agent._detach_viewer("conn-1")
        assert ("tab-1", "resume-1") in agent._detached_upstreams

        await _wait_for(lambda: not agent._detached_upstreams, timeout=3.0)
        await _wait_for(lambda: upstream.closed_sockets, timeout=3.0)
        await agent.stop()
    finally:
        await session.close()
        await upstream.stop()
