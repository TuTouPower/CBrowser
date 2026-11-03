"""Per-target viewer cleanup on supervisor disconnect (t022 A16 / AC-009)."""

from __future__ import annotations

import pytest
from cbrowser.gateway.registry import RegisteredAgent
from cbrowser.gateway.server import ViewerEntry, close_profile_viewers_and_notify


class _FakeWs:
    def __init__(self, *, fail_close: bool = False, fail_send: bool = False) -> None:
        self.closed = False
        self.close_calls = 0
        self.sent: list[str] = []
        self._fail_close = fail_close
        self._fail_send = fail_send

    async def close(self, code: int = 1000, message: bytes = b"") -> None:
        self.close_calls += 1
        if self._fail_close:
            raise ConnectionError("viewer socket already gone")
        self.closed = True

    async def send_str(self, text: str) -> None:
        if self._fail_send:
            raise ConnectionError("agent socket broken")
        self.sent.append(text)


def _agent(ws: _FakeWs) -> RegisteredAgent:
    return RegisteredAgent(
        profile_id="profile_a",
        instance_id="instance_a",
        agent_session_id="session_a",
        selkies_version="2.1.0",
        runtime_state="ready",
        udp_port=30001,
        config_version=1,
        ws=ws,
        last_heartbeat=0.0,
    )


def _viewers(**named: _FakeWs) -> dict[str, ViewerEntry]:
    return {
        cid: ViewerEntry(
            conn_id=cid, profile_id="profile_a", agent_session_id="session_a", ws=ws
        )
        for cid, ws in named.items()
    }


@pytest.mark.asyncio
async def test_first_viewer_failure_does_not_skip_remaining_targets() -> None:
    """A16: viewer 1's close raising must not prevent viewer 2's cleanup or
    the agent notifications for either target."""
    agent_ws = _FakeWs()
    first = _FakeWs(fail_close=True)
    second = _FakeWs()
    viewers = _viewers(conn_1=first, conn_2=second)

    send_failed = await close_profile_viewers_and_notify(
        viewers, "profile_a", _agent(agent_ws)
    )

    assert send_failed is False
    assert first.close_calls == 1
    assert second.close_calls == 1 and second.closed is True
    assert viewers == {}
    assert len(agent_ws.sent) == 2


@pytest.mark.asyncio
async def test_agent_send_failure_is_reported_after_all_targets() -> None:
    """A16: a broken agent socket marks the operation failed (503 at the
    HTTP layer) but every viewer is still closed first."""
    agent_ws = _FakeWs(fail_send=True)
    first = _FakeWs()
    second = _FakeWs()
    viewers = _viewers(conn_1=first, conn_2=second)

    send_failed = await close_profile_viewers_and_notify(
        viewers, "profile_a", _agent(agent_ws)
    )

    assert send_failed is True
    assert first.closed is True and second.closed is True
    assert viewers == {}


@pytest.mark.asyncio
async def test_quota_delivery_failure_is_reported_not_raised() -> None:
    """A16: a quota send to a broken agent socket returns False (the route
    maps it to an explicit 503) instead of bubbling up as a bare 500."""
    from cbrowser.gateway.server import deliver_supervisor_quota
    from cbrowser.stream_agent.protocol import SupervisorQuotaPayload

    broken = _agent(_FakeWs(fail_send=True))
    assert (
        await deliver_supervisor_quota(broken, SupervisorQuotaPayload(max_fps_cap=12.0))
        is False
    )
    healthy_ws = _FakeWs()
    healthy = _agent(healthy_ws)
    assert (
        await deliver_supervisor_quota(healthy, SupervisorQuotaPayload(max_fps_cap=12.0))
        is True
    )
    assert len(healthy_ws.sent) == 1
