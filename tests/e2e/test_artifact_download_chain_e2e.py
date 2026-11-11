"""Artifact download full chain E2E (t028 AC-004).

Real Chrome (Browser container) downloads a file -> Browser Agent
captures it -> the real Supervisor process forwards it -> the API
records an Artifact -> the user downloads it back through the API with
identical bytes and sha256.  Component suites cover the forwarder and
the API separately; this entry is the only one where every link is a
real process in the topology.  Target-environment execution is
t032's.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from gateway_probe.browser_oracle import browser_eval
from gateway_probe.evidence import save_evidence
from gateway_probe.topology import GatewayTopologyHarness
from wait import poll_until

PAYLOAD = b"cbrowser-t028-artifact-chain\n" * 512
DOWNLOAD_SCRIPT = (
    "const b=Uint8Array.from(atob('%s'),c=>c.charCodeAt(0));"
    "const a=document.createElement('a');"
    "a.href=URL.createObjectURL(new Blob([b],{type:'application/octet-stream'}));"
    "a.download='artifact.bin';document.body.appendChild(a);a.click();"
    "'download-started'"
) % base64.b64encode(PAYLOAD).decode("ascii")


@pytest.mark.asyncio
async def test_chrome_download_reaches_api_artifact(tmp_path: Path) -> None:
    harness = GatewayTopologyHarness(tmp_path)
    try:
        await harness.start()
        profile = await harness.create_and_start_profile("artifact_profile")
        profile_id = profile["profile_id"]
        browser_cname = profile["browser_container"]

        # Trigger a genuine Chrome download inside the Browser container.
        # A Blob URL keeps the download independent of the Browser network
        # policy (arbitrary edge-network hosts are denied by design) while
        # still exercising Chrome's real download pipeline and the Agent's
        # completion capture.
        await asyncio.to_thread(
            browser_eval,
            browser_cname,
            DOWNLOAD_SCRIPT,
        )

        auth_headers = await harness.login_api()
        expected_sha = hashlib.sha256(PAYLOAD).hexdigest()

        async def find_artifact(client: httpx.AsyncClient) -> dict | None:
            resp = await client.get(f"/api/v1/profiles/{profile_id}/artifacts")
            assert resp.status_code == 200
            for item in resp.json():
                if (
                    item.get("name") == "artifact.bin"
                    and item.get("kind") == "download"
                    and item.get("state") == "ready"
                ):
                    return item
            return None

        async with httpx.AsyncClient(
            base_url=harness.origin,
            headers=auth_headers,
            verify=False,
            trust_env=False,
            timeout=30.0,
        ) as api:
            artifact = await poll_until(
                lambda: find_artifact(api),
                lambda item: item is not None,
                timeout=120.0,
                interval=2.0,
                description="downloaded artifact recorded by API",
            )
            assert artifact["size"] == len(PAYLOAD)
            assert artifact["sha256"] == expected_sha

            download = await api.get(
                f"/api/v1/profiles/{profile_id}/artifacts/{artifact['id']}"
            )
            assert download.status_code == 200
            assert download.content == PAYLOAD

        save_evidence(
            "artifact_download_chain",
            {
                "artifact_id": artifact["id"],
                "size": artifact["size"],
                "sha256": artifact["sha256"],
                "download_source": "blob-url",
            },
            tmp_path,
        )
    finally:
        await harness.cleanup()
        # The payload must never leak into evidence files verbatim.
        proof = tmp_path / "artifact_download_chain.json"
        if proof.exists():
            assert json.loads(proof.read_text(encoding="utf-8"))["sha256"]

pytestmark = pytest.mark.e2e_images('CBROWSER_API_TEST_IMAGE', 'CBROWSER_CADDY_TEST_IMAGE', 'CBROWSER_GATEWAY_IMAGE', 'CBROWSER_RUNTIME_TEST_IMAGE', 'CBROWSER_STREAM_TEST_IMAGE', 'CBROWSER_SUPERVISOR_TEST_IMAGE')
