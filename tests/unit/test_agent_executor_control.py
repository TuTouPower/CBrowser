"""t031 executor CLI control: origin derivation, reasons, 4403 mapping."""

from __future__ import annotations

import pytest
from cbrowser.agent_executor.session import ExecutorSession, SessionError


def _session(endpoint: str) -> ExecutorSession:
    return ExecutorSession(
        endpoint=endpoint,
        token="cbat_test",
        profile_id="p1",
        runtime_instance_id="inst-1",
    )


def test_control_api_base_derivation():
    assert (
        _session("ws://127.0.0.1:8080/api/v1/automation/profiles/p1/cdp").control_api_base
        == "http://127.0.0.1:8080"
    )
    assert (
        _session("wss://example.invalid/api/v1/automation/profiles/p1/cdp").control_api_base
        == "https://example.invalid"
    )


@pytest.mark.asyncio
async def test_handoff_rejects_unknown_reason_without_network():
    session = _session("ws://127.0.0.1:9/api/v1/automation/profiles/p1/cdp")
    with pytest.raises(SessionError) as exc:
        await session.control_handoff("human_input")
    assert exc.value.error_code == "invalid_program"


@pytest.mark.asyncio
async def test_handoff_transport_failure_is_control_error():
    # Closed port: no server, fast connection-refused -> control error.
    session = _session("ws://127.0.0.1:9/api/v1/automation/profiles/p1/cdp")
    with pytest.raises(SessionError) as exc:
        await session.control_handoff("cli_handoff")
    assert exc.value.error_code == "control_request_failed"


@pytest.mark.asyncio
async def test_start_maps_4403_to_control_revoked():
    session = _session("ws://127.0.0.1:9/api/v1/automation/profiles/p1/cdp")

    class _Closed:
        code = 4403

    class _Exc(Exception):
        rcvd = _Closed()

    class _FakeClient:
        async def connect(self):
            raise _Exc("closed")

    session._client = _FakeClient()
    with pytest.raises(SessionError) as exc:
        await session.start()
    assert exc.value.error_code == "control_revoked"


@pytest.mark.asyncio
async def test_release_never_raises():
    session = _session("ws://127.0.0.1:9/api/v1/automation/profiles/p1/cdp")
    result = await session.control_release()
    assert result == {"released": False}


@pytest.mark.asyncio
async def test_run_program_stops_after_handoff_without_replay():
    """AC-003/AC-005: after control_handoff, later steps are skipped,
    never executed and never auto-replayed."""
    from cbrowser.agent_executor.cli import run_program

    session = _session("ws://127.0.0.1:9/api/v1/automation/profiles/p1/cdp")

    async def fake_control_post(action: str, payload: dict) -> dict:
        assert action == "handoff"
        return {"owner": "user", "generation": 2}

    session._control_post = fake_control_post
    output, exit_code = await run_program(
        session,
        {
            "version": 1,
            "steps": [
                {"action": "control_handoff", "reason": "permission"},
                # Would raise invalid_program if ever executed.
                {"action": "bogus_action"},
            ],
        },
        program_timeout=10.0,
        token="cbat_test",
    )
    assert exit_code == 0
    assert output["results"][0]["action"] == "control_handoff"
    assert output["results"][1] == {
        "action": "bogus_action",
        "skipped": "control_handed_off",
    }
    assert output.get("error") is None
