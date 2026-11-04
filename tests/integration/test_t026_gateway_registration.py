"""t026 AC-008: registration protocol convergence against the real Gateway.

Version/payload/identity refusals must come back as structured
rejections (code + build identifiers) that the Supervisor can act on,
and the control-plane registration view must reflect both successful
registrations (with the Agent's build id) and the most recent refusal.
"""

import json

import aiohttp
import pytest
from cbrowser.stream_agent.protocol import (
    AgentRegisterEnvelope,
    AgentRegisterPayload,
    GatewayRegisterResponse,
)
from cbrowser.supervisor.gateway_client import GatewayControlClient

from test_gateway_fixtures import GatewayHarness

PROFILE = "prof_reg"
INSTANCE = "inst_reg"


def _payload(profile_id: str = PROFILE, instance_id: str = INSTANCE, **kw):
    return AgentRegisterPayload(
        hostname="host-1",
        profile_id=profile_id,
        runtime_instance_id=instance_id,
        udp_port=30005,
        selkies_version="2.1.0",
        runtime_state="ready",
        config_version=1,
        **kw,
    )


async def _connect(session, harness, profile_id=PROFILE, instance_id=INSTANCE):
    return await session.ws_connect(
        f"{harness.ws_url}/stream/agent/register?profile_id={profile_id}"
        f"&runtime_instance_id={instance_id}",
        headers={
            "Authorization": "Bearer "
            + harness.agent_credentials.token_for(profile_id, instance_id)
        },
    )


@pytest.mark.asyncio
async def test_successful_registration_reports_build_ids(tmp_path):
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        harness.api_service.set_profile_runtime(PROFILE, INSTANCE)
        async with aiohttp.ClientSession() as session:
            ws = await _connect(session, harness)
            await ws.send_str(
                AgentRegisterEnvelope(
                    profile_id=PROFILE,
                    runtime_instance_id=INSTANCE,
                    payload=_payload(build_id="agent-build-9"),
                ).model_dump_json()
            )
            ack = GatewayRegisterResponse.model_validate_json(
                (await ws.receive()).data
            )
            assert ack.status == "ok"
            assert ack.gateway_build_id == "dev"

            client = GatewayControlClient(harness.base_url, harness.gw_token_file)
            try:
                status = await client.registration_status(PROFILE)
                registered = await client.agent_registered(PROFILE, INSTANCE)
            finally:
                await client.close()
            assert status is not None
            assert status["registered"] is True
            assert status["agent_build_id"] == "agent-build-9"
            assert status["gateway_build_id"] == "dev"
            assert status["rejection"] is None
            assert registered is True
            await ws.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_unsupported_version_gets_structured_rejection(tmp_path):
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        harness.api_service.set_profile_runtime(PROFILE, INSTANCE)
        async with aiohttp.ClientSession() as session:
            ws = await _connect(session, harness)
            raw = json.loads(
                AgentRegisterEnvelope(
                    profile_id=PROFILE,
                    runtime_instance_id=INSTANCE,
                    payload=_payload(build_id="agent-v3"),
                ).model_dump_json()
            )
            raw["version"] = "v3"
            await ws.send_str(json.dumps(raw))
            response = GatewayRegisterResponse.model_validate_json(
                (await ws.receive()).data
            )
            assert response.status == "error"
            assert response.rejection is not None
            assert response.rejection.code == "unsupported_version"
            assert response.rejection.gateway_build_id == "dev"
            assert response.rejection.agent_build_id == "agent-v3"
            await ws.close()

        client = GatewayControlClient(harness.base_url, harness.gw_token_file)
        try:
            status = await client.registration_status(PROFILE)
            registered = await client.agent_registered(PROFILE, INSTANCE)
        finally:
            await client.close()
        assert status is not None
        assert status["registered"] is False
        assert status["rejection"]["code"] == "unsupported_version"
        assert registered is False
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_identity_mismatch_gets_structured_rejection(tmp_path):
    harness = GatewayHarness(tmp_path)
    await harness.start()
    try:
        harness.api_service.set_profile_runtime(PROFILE, INSTANCE)
        async with aiohttp.ClientSession() as session:
            ws = await _connect(session, harness)
            await ws.send_str(
                AgentRegisterEnvelope(
                    profile_id=PROFILE,
                    runtime_instance_id=INSTANCE,
                    payload=_payload(instance_id="inst_other"),
                ).model_dump_json()
            )
            response = GatewayRegisterResponse.model_validate_json(
                (await ws.receive()).data
            )
            assert response.status == "error"
            assert response.rejection is not None
            assert response.rejection.code == "identity_mismatch"
            await ws.close()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_agent_registered_distinguishes_gateway_down(tmp_path):
    harness = GatewayHarness(tmp_path)
    await harness.start()
    await harness.stop()
    client = GatewayControlClient(harness.base_url, harness.gw_token_file)
    try:
        assert await client.agent_registered(PROFILE, INSTANCE) is None
        assert await client.registration_status(PROFILE) is None
    finally:
        await client.close()
