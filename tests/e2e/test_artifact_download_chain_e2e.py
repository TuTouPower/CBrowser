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
import hashlib
import json
from pathlib import Path

import docker
import httpx
import pytest
from gateway_probe.browser_oracle import browser_eval
from gateway_probe.evidence import save_evidence
from gateway_probe.topology import GatewayTopologyHarness
from wait import poll_until

PAYLOAD = b"cbrowser-t028-artifact-chain\n" * 512
SERVER_PORT = 18099
SERVER_SCRIPT = """
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer

PAYLOAD = b"cbrowser-t028-artifact-chain\\n" * 512


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/artifact.bin":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header(
            "Content-Disposition", 'attachment; filename="artifact.bin"'
        )
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()
        self.wfile.write(PAYLOAD)

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", 18099), Handler).serve_forever()
"""


@pytest.mark.asyncio
async def test_chrome_download_reaches_api_artifact(tmp_path: Path) -> None:
    harness = GatewayTopologyHarness(tmp_path)
    docker_client = docker.from_env()
    server = None
    try:
        await harness.start()
        profile = await harness.create_and_start_profile("artifact_profile")
        profile_id = profile["profile_id"]
        browser_cname = profile["browser_container"]

        # A file server on the topology edge network serves the file the
        # real Browser container's Chrome will download.
        server = docker_client.containers.run(
            harness.browser_image,
            entrypoint="python3",
            command=["-c", SERVER_SCRIPT],
            name=f"{harness.prefix}-fileserver",
            detach=True,
            network=harness.edge_network.name,
            labels={
                "com.cbrowser.prefix": harness.prefix,
                "com.cbrowser.test": "t028-artifact-chain",
                "com.cbrowser.role": "fileserver",
            },
        )
        server.reload()
        server_ip = server.attrs["NetworkSettings"]["Networks"][
            harness.edge_network.name
        ]["IPAddress"]

        # Trigger a genuine Chrome download inside the Browser container.
        await asyncio.to_thread(
            browser_eval,
            browser_cname,
            f"window.location.href = 'http://{server_ip}:{SERVER_PORT}/artifact.bin'; 'download-started'",
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
                "server_container": server.name,
            },
            tmp_path,
        )
    finally:
        if server is not None:
            server.remove(force=True)
        docker_client.close()
        await harness.cleanup()
        # The payload must never leak into evidence files verbatim.
        proof = tmp_path / "artifact_download_chain.json"
        if proof.exists():
            assert json.loads(proof.read_text(encoding="utf-8"))["sha256"]
