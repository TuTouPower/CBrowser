"""Multi-Agent registration budgets on the real Gateway (t028 AC-004).

The integration suite proves the RegistrationThrottle semantics against
the in-process Gateway server (A39).  This entry runs the same budget
contract against the real Gateway container in the topology: in-flight
handshake reservations bound and release, successful registrations
never consume the failure budget, twenty bad-credential handshakes
exhaust it (429 for the next valid attempt), and a Gateway container
restart restores registration for the real Agent.  Target-environment
execution is t032's.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiohttp
import pytest
from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT
from cbrowser.stream_agent.protocol import (
    AgentRegisterEnvelope,
    AgentRegisterPayload,
    GatewayRegisterResponse,
)
from gateway_probe.topology import GatewayTopologyHarness
from wait import poll_until

from cbrowser.supervisor.gateway_client import GatewayControlClient


def _register_payload(profile_id: str, instance_id: str) -> AgentRegisterPayload:
    return AgentRegisterPayload(
        hostname="host-1",
        profile_id=profile_id,
        runtime_instance_id=instance_id,
        udp_port=30005,
        selkies_version="2.1.0",
        runtime_state="ready",
        config_version=1,
    )


@pytest.mark.asyncio
async def test_registration_budgets_and_restart_recovery_on_real_gateway(
    tmp_path: Path,
) -> None:
    harness = GatewayTopologyHarness(tmp_path)
    try:
        await harness.start()
        profile = await harness.create_and_start_profile(
            "registration_budget_profile"
        )
        profile_id = profile["profile_id"]
        instance_id = profile["runtime_instance_id"]

        gw_ports = harness.gateway_container.attrs["NetworkSettings"]["Ports"]
        gw_port = gw_ports[f"{DEFAULT_GATEWAY_PORT}/tcp"][0]["HostPort"]
        gateway_base = f"http://127.0.0.1:{gw_port}"
        register_url = (
            f"{gateway_base}/stream/agent/register"
            f"?profile_id={profile_id}&runtime_instance_id={instance_id}"
        )
        agent_token = harness.keys["agent"]
        control = GatewayControlClient(
            gateway_base, harness.key_files["gateway"]
        )

        async def real_agent_registered() -> bool:
            status = await control.registration_status(profile_id)
            return bool(
                status
                and status.get("registered")
                and status.get("runtime_instance_id") == instance_id
            )

        async def register(session: aiohttp.ClientSession, token: str):
            ws_agent = await session.ws_connect(
                register_url,
                headers={"Authorization": f"Bearer {token}"},
            )
            await ws_agent.send_str(
                AgentRegisterEnvelope(
                    profile_id=profile_id,
                    runtime_instance_id=instance_id,
                    payload=_register_payload(profile_id, instance_id),
                ).model_dump_json()
            )
            ack = GatewayRegisterResponse.model_validate_json(
                (await ws_agent.receive()).data
            )
            assert ack.status == "ok"
            return ws_agent, ack.agent_session_id

        try:
            assert await real_agent_registered()
            async with aiohttp.ClientSession() as session:
                # In-flight budget: four handshakes that never complete
                # hold all reservations; the fifth is refused with 429.
                held = [
                    await session.ws_connect(
                        register_url,
                        headers={"Authorization": f"Bearer {agent_token}"},
                    )
                    for _ in range(4)
                ]
                with pytest.raises(aiohttp.ClientResponseError) as caught:
                    await register(session, agent_token)
                assert caught.value.status == 429
                for ws in held:
                    await ws.close()
                # Reservations release as the gateway observes the
                # cancellations; a registration then succeeds.
                replacement = None

                async def try_register():
                    nonlocal replacement
                    try:
                        replacement = await register(session, agent_token)
                    except aiohttp.ClientResponseError:
                        return False
                    return True

                await poll_until(
                    try_register,
                    lambda ok: ok,
                    timeout=30.0,
                    description="registration after in-flight release",
                )
                await replacement[0].close()

                # Successes never consume the failure budget: repeated
                # register/close cycles keep succeeding.
                for _ in range(25):
                    ws_agent, _ = await register(session, agent_token)
                    await ws_agent.close()

                # Failure budget: twenty bad-credential handshakes are
                # 401 each; the next valid attempt is refused with 429.
                for _ in range(20):
                    with pytest.raises(
                        aiohttp.ClientResponseError
                    ) as caught:
                        await session.ws_connect(
                            register_url,
                            headers={"Authorization": "Bearer <redacted>"},
                        )
                    assert caught.value.status == 401
                with pytest.raises(aiohttp.ClientResponseError) as caught:
                    await register(session, agent_token)
                assert caught.value.status == 429

            # Gateway restart: throttle state is fresh and the real
            # Agent re-registers on its own.
            await asyncio.to_thread(harness.gateway_container.restart)
            await poll_until(
                real_agent_registered,
                lambda ok: ok,
                timeout=90.0,
                description="real agent re-registered after gateway restart",
            )
            async with aiohttp.ClientSession() as session:
                ws_agent, _ = await register(session, agent_token)
                await ws_agent.close()
        finally:
            await control.close()
    finally:
        await harness.cleanup()
